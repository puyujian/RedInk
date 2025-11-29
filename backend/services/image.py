"""图片生成服务"""
import os
import uuid
import time
import json
import base64
import threading
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, Generator, List, Optional, Tuple
from backend.config import Config
from backend.generators.factory import ImageGeneratorFactory
from backend.generators.image_api import SensitiveWordsError
from backend.utils.image_compressor import compress_image
from backend.task_queue import get_redis_connection

logger = logging.getLogger(__name__)


class ImageTaskStateStore:
    """图片任务状态存储（基于 Redis + JSON）。

    该类专门用于存储图片生成任务的详细状态，与 TaskStore 配合使用：
    - TaskStore: 存储通用任务元信息（status, progress, user_id 等）
    - ImageTaskStateStore: 存储图片任务特有的状态（pages, generated, failed, cover_image 等）

    Key 格式:
        image_task_state:{task_id}

    Value 结构:
        {
            "pages": [...],
            "generated": {"0": "xxx.png", ...},
            "failed": {"1": "错误信息", ...},
            "candidates": {"0": ["a.png", "b.png"], ...},
            "cover_image": "<base64 字符串>",
            "full_outline": "...",
            "user_topic": "...",
            "user_images": ["<base64>", ...]
        }
    """

    # 状态过期时间（秒），默认 48 小时
    DEFAULT_TTL = 48 * 60 * 60

    @staticmethod
    def _make_key(task_id: str) -> str:
        """构造 Redis key。"""
        return f"image_task_state:{task_id}"

    @classmethod
    def init_task(
        cls,
        task_id: str,
        pages: List[Dict[str, Any]],
        full_outline: str = "",
        user_topic: str = "",
        user_images_base64: Optional[List[str]] = None,
        record_id: str = "",
        user_role: Optional[str] = None,
        provider_name: Optional[str] = None,
        ttl: Optional[int] = None,
    ) -> None:
        """初始化图片任务状态。

        Args:
            task_id: 任务 ID
            pages: 页面列表
            full_outline: 完整大纲文本
            user_topic: 用户原始输入
            user_images_base64: 用户参考图片（base64 编码）
            record_id: 关联的历史记录 UUID（用于实时同步）
            user_role: 用户角色（user/pro/admin），用于角色映射
            provider_name: 服务商名称（可选，用于任务恢复）
            ttl: 过期时间（秒）
        """
        state: Dict[str, Any] = {
            "pages": pages,
            "generated": {},
            "failed": {},
            "candidates": {},
            "cover_image": "",
            "full_outline": full_outline or "",
            "user_topic": user_topic or "",
            "user_images": user_images_base64 or [],
            "record_id": record_id or "",
            "user_role": (user_role or "").strip().lower() or "",
            "provider_name": provider_name or "",
        }
        redis_conn = get_redis_connection()
        key = cls._make_key(task_id)
        redis_conn.set(key, json.dumps(state, ensure_ascii=False))

        effective_ttl = ttl if ttl is not None else cls.DEFAULT_TTL
        if effective_ttl > 0:
            redis_conn.expire(key, effective_ttl)

        logger.info(f"图片任务状态已初始化: task_id={task_id}, pages={len(pages)}")

    @classmethod
    def load_state(cls, task_id: str) -> Optional[Dict[str, Any]]:
        """加载任务状态。

        Returns:
            任务状态字典，不存在则返回 None
        """
        redis_conn = get_redis_connection()
        raw = redis_conn.get(cls._make_key(task_id))
        if not raw:
            return None

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")

        try:
            state = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"图片任务状态解析失败: task_id={task_id}")
            return None

        # 补全默认字段，避免 KeyError（包含新增的角色和服务商字段）
        state.setdefault("pages", [])
        state.setdefault("generated", {})
        state.setdefault("failed", {})
        state.setdefault("candidates", {})
        state.setdefault("cover_image", "")
        state.setdefault("full_outline", "")
        state.setdefault("user_topic", "")
        state.setdefault("user_images", [])
        state.setdefault("record_id", "")
        state.setdefault("user_role", "")  # 新增：用户角色
        state.setdefault("provider_name", "")  # 新增：服务商名称
        return state

    @classmethod
    def save_state(cls, task_id: str, state: Dict[str, Any]) -> None:
        """保存任务状态（覆盖写入）。"""
        redis_conn = get_redis_connection()
        redis_conn.set(cls._make_key(task_id), json.dumps(state, ensure_ascii=False))

    @classmethod
    def add_generated(
        cls,
        task_id: str,
        index: int,
        filename: str,
        candidates: Optional[List[str]] = None,
    ) -> None:
        """记录单页生成成功结果。

        Args:
            task_id: 任务 ID
            index: 页面索引
            filename: 生成的主图片文件名
            candidates: 候选图片文件名列表
        """
        state = cls.load_state(task_id)
        if not state:
            logger.warning(f"无法记录生成结果，任务状态不存在: task_id={task_id}")
            return

        key = str(index)
        state["generated"][key] = filename
        if candidates:
            state["candidates"][key] = candidates
        # 如果之前失败过，移除失败记录
        state["failed"].pop(key, None)

        cls.save_state(task_id, state)

    @classmethod
    def add_failed(cls, task_id: str, index: int, error: str, retryable: bool = True) -> None:
        """记录单页生成失败信息。

        Args:
            task_id: 任务 ID
            index: 页面索引
            error: 错误信息
            retryable: 是否可重试（默认 True，敏感词错误为 False）
        """
        state = cls.load_state(task_id)
        if not state:
            logger.warning(f"无法记录失败信息，任务状态不存在: task_id={task_id}")
            return

        # 存储格式: {"message": "错误信息", "retryable": bool}
        state["failed"][str(index)] = {
            "message": error,
            "retryable": retryable,
        }
        cls.save_state(task_id, state)

    @classmethod
    def set_cover_image(cls, task_id: str, image_bytes: bytes) -> None:
        """保存压缩后的封面图（base64 编码）。"""
        if not image_bytes:
            return

        state = cls.load_state(task_id)
        if not state:
            return

        state["cover_image"] = base64.b64encode(image_bytes).decode("utf-8")
        cls.save_state(task_id, state)

    @classmethod
    def get_cover_image(cls, task_id: str) -> Optional[bytes]:
        """获取封面图二进制数据。"""
        state = cls.load_state(task_id)
        if not state:
            return None

        b64 = state.get("cover_image") or ""
        if not b64:
            return None

        try:
            return base64.b64decode(b64)
        except Exception:
            return None

    @classmethod
    def clear(cls, task_id: str) -> None:
        """删除任务状态。"""
        redis_conn = get_redis_connection()
        redis_conn.delete(cls._make_key(task_id))
        logger.info(f"图片任务状态已清理: task_id={task_id}")


class ImageService:
    """图片生成服务类"""

    # 并发配置
    MAX_CONCURRENT = 15  # 最大并发数
    AUTO_RETRY_COUNT = 3  # 自动重试次数

    def __init__(self, provider_name: str = None, user_role: Optional[str] = None):
        """
        初始化图片生成服务

        Args:
            provider_name: 服务商名称，如果为None则根据用户角色选择
            user_role: 用户角色（user/pro/admin），用于角色映射选择服务商
        """
        # 保存用户角色（规范化为小写）
        self.user_role = (user_role or "").strip().lower() or None

        # 根据角色和传入参数解析最终使用的服务商
        provider_name = self._resolve_provider(provider_name)

        # 获取服务商配置
        provider_config = Config.get_image_provider_config(provider_name, role=self.user_role)

        # 创建生成器实例
        provider_type = provider_config.get('type', provider_name)
        self.generator = ImageGeneratorFactory.create(provider_type, provider_config)

        # 保存配置信息
        self.provider_name = provider_name
        self.provider_config = provider_config

        # 加载提示词模板
        self.prompt_template = self._load_prompt_template()

        # 输出目录
        self.output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "output"
        )
        os.makedirs(self.output_dir, exist_ok=True)

        # 存储任务状态（用于重试）
        self._task_states: Dict[str, Dict] = {}

    def _resolve_provider(self, provider_name: Optional[str]) -> str:
        """
        根据角色/配置解析最终使用的服务商，带安全回退机制。

        Args:
            provider_name: 明确指定的服务商名称（优先级最高）

        Returns:
            最终使用的服务商名称

        Raises:
            ValueError: 当没有找到任何可用的服务商时
        """
        config = Config.load_image_providers_config()
        providers = config.get('providers', {}) or {}

        # 如果明确指定了服务商且存在，直接使用
        if provider_name and provider_name in providers:
            logger.info(
                f"[ImageService] 使用明确指定的服务商: provider={provider_name}, "
                f"role={self.user_role or 'N/A'}"
            )
            return provider_name

        # 如果指定的服务商不存在，记录警告
        if provider_name and provider_name not in providers:
            logger.warning(
                f"[ImageService] 指定的服务商不存在: provider={provider_name}, "
                f"role={self.user_role}, 将根据角色映射选择服务商"
            )

        # 根据用户角色选择服务商
        try:
            selected_provider = Config.get_image_provider_by_role(
                self.user_role,
                default_provider=config.get('active_provider'),
            )
            logger.info(
                f"[ImageService] 根据角色选择服务商: role={self.user_role or 'N/A'}, "
                f"provider={selected_provider}"
            )
            return selected_provider
        except Exception as exc:
            logger.warning(
                f"[ImageService] 角色映射服务商失败: role={self.user_role}, error={exc}, "
                f"将使用任意可用服务商"
            )
            # 最后的回退：使用第一个可用的服务商
            if providers:
                fallback = next(iter(providers.keys()))
                logger.warning(f"[ImageService] 使用回退服务商: {fallback}")
                return fallback
            raise

    def _load_prompt_template(self) -> str:
        """加载 Prompt 模板"""
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "prompts",
            "image_prompt.txt"
        )
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()

    def _save_image(self, image_data: bytes, filename: str) -> str:
        """
        保存图片到本地

        Args:
            image_data: 图片二进制数据
            filename: 文件名

        Returns:
            保存的文件路径
        """
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "wb") as f:
            f.write(image_data)
        return filepath

    def _save_candidate_images(
        self,
        candidates: List[bytes],
        task_id: str,
        index: int
    ) -> List[str]:
        """
        保存所有候选图片到本地

        Args:
            candidates: 候选图片数据列表
            task_id: 任务ID
            index: 页面索引

        Returns:
            候选图片文件名列表
        """
        filenames = []
        for i, image_data in enumerate(candidates):
            # 主图片: task_id_index.png, 候选图片: task_id_index_c1.png, task_id_index_c2.png, ...
            if i == 0:
                filename = f"{task_id}_{index}.png"
            else:
                filename = f"{task_id}_{index}_c{i}.png"
            self._save_image(image_data, filename)
            filenames.append(filename)
        return filenames

    def _generate_single_image(
        self,
        page: Dict,
        task_id: str,
        reference_image: Optional[bytes] = None,
        retry_count: int = 0,
        full_outline: str = "",
        user_images: Optional[List[bytes]] = None,
        user_topic: str = ""
    ) -> Tuple[int, bool, Optional[str], Optional[str], Optional[List[str]], bool]:
        """
        生成单张图片（带自动重试），支持多图候选

        Args:
            page: 页面数据
            task_id: 任务ID
            reference_image: 参考图片（封面图）
            retry_count: 当前重试次数
            full_outline: 完整的大纲文本
            user_images: 用户上传的参考图片列表
            user_topic: 用户原始输入

        Returns:
            (index, success, filename, error_message, candidate_filenames, retryable)
            - candidate_filenames: 所有候选图片的文件名列表（包含主图片）
            - retryable: 失败时是否可重试（敏感词错误不可重试）
        """
        index = page["index"]
        page_type = page["type"]
        page_content = page["content"]

        max_retries = self.AUTO_RETRY_COUNT

        for attempt in range(max_retries):
            try:
                # 构造图片生成 Prompt（包含完整大纲上下文和用户原始需求）
                prompt = self.prompt_template.format(
                    page_content=page_content,
                    page_type=page_type,
                    full_outline=full_outline,
                    user_topic=user_topic if user_topic else "未提供"
                )

                # 调用生成器生成图片
                if self.provider_config.get('type') == 'google_genai':
                    image_data = self.generator.generate_image(
                        prompt=prompt,
                        aspect_ratio=self.provider_config.get('default_aspect_ratio', '3:4'),
                        temperature=self.provider_config.get('temperature', 1.0),
                        model=self.provider_config.get('model', 'gemini-3-pro-image-preview'),
                        reference_image=reference_image,
                    )
                    # 保存单张图片
                    filename = f"{task_id}_{index}.png"
                    self._save_image(image_data, filename)
                    return (index, True, filename, None, [filename], True)

                elif self.provider_config.get('type') == 'image_api':
                    # Image API 支持多张参考图片
                    reference_images = []
                    if user_images:
                        reference_images.extend(user_images)
                    if reference_image:
                        reference_images.append(reference_image)

                    image_data = self.generator.generate_image(
                        prompt=prompt,
                        aspect_ratio=self.provider_config.get('default_aspect_ratio', '3:4'),
                        temperature=self.provider_config.get('temperature', 1.0),
                        model=self.provider_config.get('model', 'nano-banana-2'),
                        reference_images=reference_images if reference_images else None,
                    )
                    # 保存单张图片
                    filename = f"{task_id}_{index}.png"
                    self._save_image(image_data, filename)
                    return (index, True, filename, None, [filename], True)

                else:
                    # OpenAI 兼容接口 - 支持多图候选与参考图
                    reference_images = []
                    if user_images:
                        reference_images.extend(user_images)
                    if reference_image:
                        reference_images.append(reference_image)

                    if hasattr(self.generator, 'generate_image_with_candidates'):
                        result = self.generator.generate_image_with_candidates(
                            prompt=prompt,
                            size=self.provider_config.get('default_size', '1024x1024'),
                            model=self.provider_config.get('model'),
                            quality=self.provider_config.get('quality', 'standard'),
                            reference_images=reference_images if reference_images else None,
                        )
                        # 保存所有候选图片
                        candidate_filenames = self._save_candidate_images(
                            result["candidates"], task_id, index
                        )
                        return (index, True, candidate_filenames[0], None, candidate_filenames, True)
                    else:
                        # 回退到单图方法
                        image_data = self.generator.generate_image(
                            prompt=prompt,
                            size=self.provider_config.get('default_size', '1024x1024'),
                            model=self.provider_config.get('model'),
                            quality=self.provider_config.get('quality', 'standard'),
                            reference_images=reference_images if reference_images else None,
                        )
                        filename = f"{task_id}_{index}.png"
                        self._save_image(image_data, filename)
                        return (index, True, filename, None, [filename], True)

            except Exception as e:
                error_msg = str(e)
                # 敏感词错误不可重试，立即返回
                is_sensitive_error = isinstance(e, SensitiveWordsError)
                print(f"[生成失败] 第 {index + 1} 页, 尝试 {attempt + 1}/{max_retries}: {error_msg[:100]}")

                if is_sensitive_error:
                    return (index, False, None, error_msg, None, False)

                if attempt < max_retries - 1:
                    # 等待后重试
                    time.sleep(2 ** attempt)
                    continue

                return (index, False, None, error_msg, None, True)

        return (index, False, None, "超过最大重试次数", None, True)

    def generate_images(
        self,
        pages: list,
        task_id: str = None,
        full_outline: str = "",
        user_images: Optional[List[bytes]] = None,
        user_topic: str = ""
    ) -> Generator[Dict[str, Any], None, None]:
        """
        生成图片（生成器，支持 SSE 流式返回）
        优化版本：先生成封面，然后并发生成其他页面

        Args:
            pages: 页面列表
            task_id: 任务 ID（可选）
            full_outline: 完整的大纲文本（用于保持风格一致）
            user_images: 用户上传的参考图片列表（可选）
            user_topic: 用户原始输入（用于保持意图一致）

        Yields:
            进度事件字典
        """
        if task_id is None:
            task_id = f"task_{uuid.uuid4().hex[:8]}"

        total = len(pages)
        generated_images = []
        failed_pages = []
        cover_image_data = None

        # 压缩用户上传的参考图到200KB以内（减少内存和传输开销）
        compressed_user_images = None
        if user_images:
            compressed_user_images = [compress_image(img, max_size_kb=200) for img in user_images]

        # 初始化任务状态
        self._task_states[task_id] = {
            "pages": pages,
            "generated": {},
            "failed": {},
            "cover_image": None,
            "full_outline": full_outline,
            "user_images": compressed_user_images  # 保存压缩后的用户上传图片
        }

        # ==================== 第一阶段：生成封面 ====================
        cover_page = None
        other_pages = []

        for page in pages:
            if page["type"] == "cover":
                cover_page = page
            else:
                other_pages.append(page)

        # 如果没有封面，使用第一页作为封面
        if cover_page is None and len(pages) > 0:
            cover_page = pages[0]
            other_pages = pages[1:]

        if cover_page:
            # 发送封面生成进度
            yield {
                "event": "progress",
                "data": {
                    "index": cover_page["index"],
                    "status": "generating",
                    "message": "正在生成封面...",
                    "current": 1,
                    "total": total,
                    "phase": "cover"
                }
            }

            # 生成封面（使用用户上传的图片作为参考）
            index, success, filename, error, candidates, retryable = self._generate_single_image(
                cover_page, task_id, reference_image=None, full_outline=full_outline,
                user_images=compressed_user_images, user_topic=user_topic
            )

            if success:
                generated_images.append(filename)
                self._task_states[task_id]["generated"][index] = filename
                # 保存候选图片信息
                if candidates and len(candidates) > 1:
                    self._task_states[task_id].setdefault("candidates", {})[index] = candidates

                # 读取封面图片作为参考，并立即压缩到200KB以内
                cover_path = os.path.join(self.output_dir, filename)
                with open(cover_path, "rb") as f:
                    cover_image_data = f.read()

                # 压缩封面图（减少内存占用和后续传输开销）
                cover_image_data = compress_image(cover_image_data, max_size_kb=200)
                self._task_states[task_id]["cover_image"] = cover_image_data

                # 构建候选图片URL列表
                candidate_urls = [f"/api/images/{f}" for f in (candidates or [filename])]

                yield {
                    "event": "complete",
                    "data": {
                        "index": index,
                        "status": "done",
                        "image_url": f"/api/images/{filename}",
                        "candidates": candidate_urls,
                        "phase": "cover"
                    }
                }
            else:
                failed_pages.append(cover_page)
                self._task_states[task_id]["failed"][index] = {
                    "message": error,
                    "retryable": retryable,
                }

                yield {
                    "event": "error",
                    "data": {
                        "index": index,
                        "status": "error",
                        "message": error,
                        "retryable": retryable,
                        "phase": "cover"
                    }
                }

        # ==================== 第二阶段：并发生成其他页面 ====================
        if other_pages:
            yield {
                "event": "progress",
                "data": {
                    "status": "batch_start",
                    "message": f"开始并发生成 {len(other_pages)} 页内容...",
                    "current": len(generated_images),
                    "total": total,
                    "phase": "content"
                }
            }

            # 使用线程池并发生成
            with ThreadPoolExecutor(max_workers=self.MAX_CONCURRENT) as executor:
                # 提交所有任务
                future_to_page = {
                    executor.submit(
                        self._generate_single_image,
                        page,
                        task_id,
                        cover_image_data,  # 使用封面作为参考
                        0,  # retry_count
                        full_outline,  # 传入完整大纲
                        compressed_user_images,  # 用户上传的参考图片（已压缩）
                        user_topic  # 用户原始输入
                    ): page
                    for page in other_pages
                }

                # 发送每个页面的进度
                for page in other_pages:
                    yield {
                        "event": "progress",
                        "data": {
                            "index": page["index"],
                            "status": "generating",
                            "current": len(generated_images) + 1,
                            "total": total,
                            "phase": "content"
                        }
                    }

                # 收集结果
                for future in as_completed(future_to_page):
                    page = future_to_page[future]
                    try:
                        index, success, filename, error, candidates, retryable = future.result()

                        if success:
                            generated_images.append(filename)
                            self._task_states[task_id]["generated"][index] = filename
                            # 保存候选图片信息
                            if candidates and len(candidates) > 1:
                                self._task_states[task_id].setdefault("candidates", {})[index] = candidates

                            # 构建候选图片URL列表
                            candidate_urls = [f"/api/images/{f}" for f in (candidates or [filename])]

                            yield {
                                "event": "complete",
                                "data": {
                                    "index": index,
                                    "status": "done",
                                    "image_url": f"/api/images/{filename}",
                                    "candidates": candidate_urls,
                                    "phase": "content"
                                }
                            }
                        else:
                            failed_pages.append(page)
                            self._task_states[task_id]["failed"][index] = {
                                "message": error,
                                "retryable": retryable,
                            }

                            yield {
                                "event": "error",
                                "data": {
                                    "index": index,
                                    "status": "error",
                                    "message": error,
                                    "retryable": retryable,
                                    "phase": "content"
                                }
                            }

                    except Exception as e:
                        failed_pages.append(page)
                        error_msg = str(e)
                        self._task_states[task_id]["failed"][page["index"]] = {
                            "message": error_msg,
                            "retryable": True,
                        }

                        yield {
                            "event": "error",
                            "data": {
                                "index": page["index"],
                                "status": "error",
                                "message": error_msg,
                                "retryable": True,
                                "phase": "content"
                            }
                        }

        # ==================== 完成 ====================
        yield {
            "event": "finish",
            "data": {
                "success": len(failed_pages) == 0,
                "task_id": task_id,
                "images": generated_images,
                "total": total,
                "completed": len(generated_images),
                "failed": len(failed_pages),
                "failed_indices": [p["index"] for p in failed_pages]
            }
        }

    def retry_single_image(
        self,
        task_id: str,
        page: Dict,
        use_reference: bool = True
    ) -> Dict[str, Any]:
        """
        重试生成单张图片

        Args:
            task_id: 任务ID
            page: 页面数据
            use_reference: 是否使用封面作为参考

        Returns:
            生成结果
        """
        # 获取参考图
        reference_image = None
        if use_reference and task_id in self._task_states:
            reference_image = self._task_states[task_id].get("cover_image")

        # 生成图片
        index, success, filename, error, _, retryable = self._generate_single_image(
            page, task_id, reference_image
        )

        if success:
            # 更新任务状态
            if task_id in self._task_states:
                self._task_states[task_id]["generated"][index] = filename
                if index in self._task_states[task_id]["failed"]:
                    del self._task_states[task_id]["failed"][index]

            return {
                "success": True,
                "index": index,
                "image_url": f"/api/images/{filename}"
            }
        else:
            return {
                "success": False,
                "index": index,
                "error": error,
                "retryable": retryable
            }

    def retry_failed_images(
        self,
        task_id: str,
        pages: List[Dict]
    ) -> Generator[Dict[str, Any], None, None]:
        """
        批量重试失败的图片

        Args:
            task_id: 任务ID
            pages: 需要重试的页面列表

        Yields:
            进度事件
        """
        # 获取参考图
        reference_image = None
        if task_id in self._task_states:
            reference_image = self._task_states[task_id].get("cover_image")

        total = len(pages)
        success_count = 0
        failed_count = 0

        yield {
            "event": "retry_start",
            "data": {
                "total": total,
                "message": f"开始重试 {total} 张失败的图片"
            }
        }

        # 并发重试
        # 从任务状态中获取完整大纲
        full_outline = ""
        if task_id in self._task_states:
            full_outline = self._task_states[task_id].get("full_outline", "")

        with ThreadPoolExecutor(max_workers=self.MAX_CONCURRENT) as executor:
            future_to_page = {
                executor.submit(
                    self._generate_single_image,
                    page,
                    task_id,
                    reference_image,
                    0,  # retry_count
                    full_outline  # 传入完整大纲
                ): page
                for page in pages
            }

            for future in as_completed(future_to_page):
                page = future_to_page[future]
                try:
                    index, success, filename, error, _, retryable = future.result()

                    if success:
                        success_count += 1
                        if task_id in self._task_states:
                            self._task_states[task_id]["generated"][index] = filename
                            if index in self._task_states[task_id]["failed"]:
                                del self._task_states[task_id]["failed"][index]

                        yield {
                            "event": "complete",
                            "data": {
                                "index": index,
                                "status": "done",
                                "image_url": f"/api/images/{filename}"
                            }
                        }
                    else:
                        failed_count += 1
                        yield {
                            "event": "error",
                            "data": {
                                "index": index,
                                "status": "error",
                                "message": error,
                                "retryable": retryable
                            }
                        }

                except Exception as e:
                    failed_count += 1
                    yield {
                        "event": "error",
                        "data": {
                            "index": page["index"],
                            "status": "error",
                            "message": str(e),
                            "retryable": True
                        }
                    }

        yield {
            "event": "retry_finish",
            "data": {
                "success": failed_count == 0,
                "total": total,
                "completed": success_count,
                "failed": failed_count
            }
        }

    def _decode_user_images(self, images_base64: Optional[List[str]]) -> List[bytes]:
        """解码用户上传的参考图并压缩

        Args:
            images_base64: base64编码的图片列表

        Returns:
            压缩后的图片字节列表
        """
        result: List[bytes] = []
        for idx, img_b64 in enumerate(images_base64 or []):
            if not img_b64:
                continue
            try:
                # 移除 data:image/xxx;base64, 前缀
                if "," in img_b64:
                    img_b64 = img_b64.split(",", 1)[1]
                decoded = base64.b64decode(img_b64)
                result.append(compress_image(decoded, max_size_kb=200))
            except Exception as e:
                logger.warning(f"[重新生成] 用户参考图解码失败 index={idx}: {e}")
        return result

    def regenerate_image(
        self,
        task_id: str,
        page: Dict,
        use_reference: bool = True,
        user_images: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        重新生成图片（用户手动触发，即使成功的也可以重新生成）

        Args:
            task_id: 任务ID
            page: 页面数据
            use_reference: 是否使用封面作为参考
            user_images: 用户上传的参考图片（base64 列表，可选）

        Returns:
            生成结果，包含候选图片列表
        """
        # 从持久化存储加载任务状态
        state = ImageTaskStateStore.load_state(task_id)

        # 校验任务状态是否存在
        if not state:
            logger.error(f"[重新生成] 任务状态不存在或已过期: task_id={task_id}")
            return {
                "success": False,
                "index": page.get("index", -1),
                "error": "任务状态不存在或已过期，请重新生成整个任务",
                "retryable": False
            }

        state_generated = state.get("generated") or {}
        state_candidates = state.get("candidates") or {}
        full_outline = state.get("full_outline", "")
        user_topic = state.get("user_topic", "")

        # 获取参考图（优先使用持久化存储）
        reference_image = None
        if use_reference:
            reference_image = ImageTaskStateStore.get_cover_image(task_id)
            if reference_image is None and task_id in self._task_states:
                reference_image = self._task_states[task_id].get("cover_image")

        # 准备用户参考图
        user_images_bytes: Optional[List[bytes]] = None
        if task_id in self._task_states:
            user_images_bytes = self._task_states[task_id].get("user_images")
        if not user_images_bytes:
            # 优先使用传入的user_images，否则从状态中获取
            base64_list = user_images if user_images is not None else state.get("user_images")
            if base64_list:
                user_images_bytes = self._decode_user_images(base64_list)

        # 生成新图片
        index, success, filename, error, candidates, retryable = self._generate_single_image(
            page,
            task_id,
            reference_image,
            0,
            full_outline,
            user_images_bytes or None,
            user_topic,
        )

        if success:
            key = str(index)

            # 合并候选图片列表：原图 + 已有候选 + 新生成的图
            merged_candidates: List[str] = []

            # 1. 添加原图（如果存在）
            previous_main = state_generated.get(key)
            if previous_main:
                merged_candidates.append(previous_main)

            # 2. 添加已有候选图
            merged_candidates.extend(state_candidates.get(key) or [])

            # 3. 添加新生成的图
            if candidates:
                merged_candidates.extend(candidates)
            elif filename:
                merged_candidates.append(filename)

            # 去重保持顺序
            seen = set()
            unique_candidates: List[str] = []
            for f in merged_candidates:
                if not f or f in seen:
                    continue
                seen.add(f)
                unique_candidates.append(f)

            # 更新持久化状态
            if state:
                ImageTaskStateStore.add_generated(task_id, index, filename, unique_candidates)

            # 更新内存状态
            if task_id in self._task_states:
                self._task_states[task_id].setdefault("generated", {})[index] = filename
                self._task_states[task_id].setdefault("candidates", {})[index] = unique_candidates

            return {
                "success": True,
                "index": index,
                "image_url": f"/api/images/{filename}",
                "candidates": [f"/api/images/{f}" for f in unique_candidates],
                "candidate_files": unique_candidates,
            }
        else:
            return {
                "success": False,
                "index": index,
                "error": error,
                "retryable": retryable
            }

    def get_image_path(self, filename: str) -> str:
        """
        获取图片完整路径

        Args:
            filename: 文件名

        Returns:
            完整路径
        """
        return os.path.join(self.output_dir, filename)

    def get_task_state(self, task_id: str) -> Optional[Dict]:
        """获取任务状态"""
        return self._task_states.get(task_id)

    def cleanup_task(self, task_id: str):
        """清理任务状态（释放内存）"""
        if task_id in self._task_states:
            del self._task_states[task_id]


# 全局服务实例
_service_instance = None

def get_image_service() -> ImageService:
    """获取全局图片生成服务实例（不带角色信息）"""
    global _service_instance
    if _service_instance is None:
        _service_instance = ImageService()
    return _service_instance


def get_scoped_image_service(
    provider_name: Optional[str] = None,
    user_role: Optional[str] = None
) -> ImageService:
    """创建带有特定角色/服务商的图片生成服务实例（不缓存）。

    该函数用于需要根据用户角色动态选择服务商的场景，
    每次调用都会创建新的实例，避免污染全局缓存。

    Args:
        provider_name: 服务商名称（可选）
        user_role: 用户角色（user/pro/admin）

    Returns:
        ImageService 实例

    Example:
        # 为 PRO 用户创建服务实例
        service = get_scoped_image_service(user_role='pro')

        # 为特定服务商创建实例
        service = get_scoped_image_service(provider_name='google_genai')
    """
    return ImageService(provider_name=provider_name, user_role=user_role)
