"""OpenAI 兼容接口图片生成器"""
import time
import random
import base64
import re
import logging
from functools import wraps
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from .base import ImageGeneratorBase
from ..utils.image_compressor import compress_image

# 配置日志
logger = logging.getLogger(__name__)


# 常量定义
DEFAULT_IMAGE_INDEX = 0
DEFAULT_REQUEST_TIMEOUT = 180
DEFAULT_DOWNLOAD_TIMEOUT = 60
MARKDOWN_IMAGE_PATTERN = r'!\[[^\]]*\]\(([^)\s]+)[^)]*\)'
SENSITIVE_ERROR_KEYWORD = "sensitive_words_detected"


def retry_on_error(max_retries=5, base_delay=3):
    """
    错误自动重试装饰器

    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟时间（秒）

    Returns:
        装饰后的函数
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    # 对于参数错误/业务错误（如提示词过长），无需重试，直接抛出
                    if isinstance(e, ValueError):
                        raise

                    error_str = str(e)
                    # 敏感词错误不可重试，立即抛出
                    if SENSITIVE_ERROR_KEYWORD in error_str:
                        logger.warning("检测到敏感词错误，跳过所有重试")
                        raise

                    # 检查是否是速率限制错误
                    if "429" in error_str or "rate" in error_str.lower():
                        if attempt < max_retries - 1:
                            wait_time = (base_delay ** attempt) + random.uniform(0, 1)
                            logger.warning(
                                f"遇到速率限制，{wait_time:.1f}秒后重试 "
                                f"(尝试 {attempt + 2}/{max_retries})"
                            )
                            time.sleep(wait_time)
                            continue
                    # 其他错误或重试耗尽
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        logger.warning(
                            f"请求失败: {error_str[:100]}，{wait_time}秒后重试"
                        )
                        time.sleep(wait_time)
                        continue
                    raise
            raise Exception(f"重试 {max_retries} 次后仍失败")
        return wrapper
    return decorator


class OpenAICompatibleGenerator(ImageGeneratorBase):
    """
    OpenAI 兼容接口图片生成器

    支持两种API端点类型：
    1. /v1/images/generations - 标准图片生成接口
    2. /v1/chat/completions - 聊天接口（某些服务商使用此方式返回图片）

    对于chat接口，支持以下返回格式：
    - base64 data URL: data:image/png;base64,...
    - Markdown图片链接: ![alt](url)（支持多图片返回）
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        if not self.api_key:
            raise ValueError("API Key 未配置")

        if not self.base_url:
            raise ValueError("Base URL 未配置")

        # 默认模型
        self.default_model = config.get('model', 'dall-e-3')

        # API 端点类型: 'images' 或 'chat'
        self.endpoint_type = config.get('endpoint_type', 'images')

        # 默认图片索引（用于多图返回场景）
        self.image_index = self._parse_image_index(
            config.get('image_index', DEFAULT_IMAGE_INDEX)
        )

        # 流式配置（仅用于 chat 端点）
        self.chat_stream_enabled = config.get('chat_stream_enabled', False)
        self.chat_stream_idle_timeout = config.get('chat_stream_idle_timeout', 300)

        # SSE 流式解析防护配置
        self.sse_max_content_bytes = config.get('sse_max_content_bytes', 10 * 1024 * 1024)  # 10MB
        self.sse_max_events = config.get('sse_max_events', 10000)
        self.sse_heartbeat_timeout = config.get('sse_heartbeat_timeout', 60)

        # 下载安全配置
        self.download_max_bytes = config.get('download_max_bytes', 20 * 1024 * 1024)  # 20MB
        self.download_allowed_content_types = config.get(
            'download_allowed_content_types',
            ['image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/gif']
        )
        self.download_chunk_size = config.get('download_chunk_size', 8192)  # 8KB chunks

        # 调试日志：输出关键配置
        logger.info(
            f"[CONFIG] OpenAI Compatible Generator 初始化: "
            f"endpoint_type={self.endpoint_type}, "
            f"chat_stream_enabled={self.chat_stream_enabled}, "
            f"model={self.default_model}, "
            f"sse_max_content_bytes={self.sse_max_content_bytes}, "
            f"download_max_bytes={self.download_max_bytes}"
        )

    def validate_config(self) -> bool:
        """验证配置"""
        return bool(self.api_key and self.base_url)

    def _parse_image_index(self, value: Any) -> int:
        """
        解析图片索引配置值

        Args:
            value: 配置值（可能是int、str或其他类型）

        Returns:
            有效的图片索引（非负整数）
        """
        try:
            index = int(value)
            if index < 0:
                logger.warning(
                    f"image_index 配置为负数 {index}，已回退为 {DEFAULT_IMAGE_INDEX}"
                )
                return DEFAULT_IMAGE_INDEX
            return index
        except (TypeError, ValueError):
            logger.warning(
                f"image_index 配置无效: {value!r}，已回退为 {DEFAULT_IMAGE_INDEX}"
            )
            return DEFAULT_IMAGE_INDEX

    def _collect_reference_images(
        self,
        reference_image: Optional[bytes],
        reference_images: Optional[List[bytes]]
    ) -> List[bytes]:
        """
        收集所有参考图片

        Args:
            reference_image: 单张参考图片数据（向后兼容）
            reference_images: 多张参考图片数据列表

        Returns:
            合并后的参考图片列表
        """
        all_images = []

        # 优先使用 reference_images 列表
        if reference_images and len(reference_images) > 0:
            all_images.extend(reference_images)

        # 向后兼容：如果有单张 reference_image，添加到列表
        if reference_image and reference_image not in all_images:
            all_images.append(reference_image)

        return all_images

    def _build_chat_messages_with_images(
        self,
        prompt: str,
        reference_images: List[bytes]
    ) -> List[Dict[str, Any]]:
        """
        构建包含参考图片的 chat messages

        对于 chat/completions 端点，使用 OpenAI Vision API 格式：
        content 为数组，包含 text 和 image_url 类型的元素

        Args:
            prompt: 原始提示词
            reference_images: 参考图片数据列表

        Returns:
            构建好的 messages 列表
        """
        if not reference_images:
            # 无参考图片时，使用简单的文本消息格式
            return [
                {
                    "role": "user",
                    "content": prompt
                }
            ]

        # 有参考图片时，构建多模态消息
        content_parts = []

        # 添加参考图片（压缩后转为 base64 Data URI）
        for idx, img_data in enumerate(reference_images):
            try:
                # 压缩图片到 200KB 以内
                compressed_img = compress_image(img_data, max_size_kb=200)
                base64_image = base64.b64encode(compressed_img).decode('utf-8')
                data_uri = f"data:image/png;base64,{base64_image}"

                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": data_uri
                    }
                })
                logger.debug(f"添加参考图片 {idx + 1}/{len(reference_images)}")
            except Exception as e:
                logger.warning(f"处理参考图片 {idx + 1} 失败: {e}")
                continue

        # 增强提示词以利用参考图
        ref_count = len(reference_images)
        enhanced_prompt = f"""参考提供的 {ref_count} 张图片的风格（色彩、光影、构图、氛围），生成一张新图片。

新图片内容：{prompt}

要求：
1. 保持相似的色调和氛围
2. 使用相似的光影处理
3. 保持一致的画面质感
4. 如果参考图中有人物或产品，可以适当融入"""

        # 添加文本部分
        content_parts.append({
            "type": "text",
            "text": enhanced_prompt
        })

        return [
            {
                "role": "user",
                "content": content_parts
            }
        ]

    def _build_chat_request(
        self,
        model: str,
        size: str,
        prompt: str,
        reference_images: Optional[List[bytes]] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        统一构造 chat API 请求所需的 url/headers/payload

        Args:
            model: 模型名称
            size: 图片尺寸
            prompt: 已预处理的提示词
            reference_images: 参考图片数据列表
            stream: 是否启用流式模式

        Returns:
            包含 url, headers, payload 的字典
        """
        url = f"{self.base_url.rstrip('/')}/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        messages = self._build_chat_messages_with_images(prompt, reference_images or [])

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 1.0,
            "size": size
        }

        if stream:
            payload["stream"] = True

        return {
            "url": url,
            "headers": headers,
            "payload": payload
        }

    def _validate_and_extract_content(self, content: str, prompt: str) -> str:
        """
        统一进行错误检测并返回验证后的内容

        Args:
            content: API 返回的原始内容
            prompt: 原始提示词（用于错误信息）

        Returns:
            验证通过的内容

        Raises:
            ValueError: 内容为空或检测到错误
        """
        if not content:
            raise ValueError("API 响应内容为空")

        # 优先检查明显的错误提示
        self._raise_if_chat_content_is_error(content, prompt)

        # 检测其他错误消息
        error_message = self._detect_api_error_message(content)
        if error_message:
            raise ValueError(f"图片生成 API 返回错误: {error_message}")

        return content

    def _process_chat_content(
        self,
        content: str,
        image_index: Optional[int] = None,
        return_candidates: bool = False
    ):
        """
        统一处理 chat content，支持单图或候选图模式

        Args:
            content: 已验证的 API 响应内容
            image_index: 指定返回第几张图片（None 表示使用配置的默认值）
            return_candidates: 是否返回所有候选图片

        Returns:
            bytes: 单图模式，返回图片二进制数据
            Dict: 候选模式，返回 {primary, candidates, count}

        Raises:
            ValueError: 无法识别的内容格式
        """
        # 情况一：base64 data URL
        if content.startswith("data:image"):
            image_data = self._decode_base64_image(content)
            if return_candidates:
                return {
                    "primary": image_data,
                    "candidates": [image_data],
                    "count": 1
                }
            return image_data

        # 情况二：Markdown 图片链接
        image_urls = self._extract_image_urls_from_markdown(content)
        if image_urls:
            logger.info(f"从响应中提取到 {len(image_urls)} 个图片 URL")
            if return_candidates:
                return self._download_all_images_from_urls(image_urls)
            return self._download_image_from_urls(image_urls, image_index)

        # 无法识别的格式
        preview = content[:200].replace("\n", "\\n")
        raise ValueError(
            f"chat API 响应中未找到可识别的图片数据格式，content 预览: {preview}"
        )

    def _stream_download_image(self, url: str) -> bytes:
        """
        流式下载图片，带大小和 Content-Type 校验

        Args:
            url: 图片 URL

        Returns:
            图片二进制数据

        Raises:
            ValueError: 内容类型不允许或大小超限
            requests.RequestException: 网络请求失败
        """
        logger.debug(f"开始流式下载图片: {url[:100]}")

        try:
            # 使用上下文管理器确保连接正确关闭
            with requests.get(
                url,
                timeout=DEFAULT_DOWNLOAD_TIMEOUT,
                stream=True
            ) as response:
                response.raise_for_status()

                # 校验 Content-Type
                content_type = response.headers.get("Content-Type", "").lower()
                if self.download_allowed_content_types:
                    if not any(content_type.startswith(t) for t in self.download_allowed_content_types):
                        raise ValueError(
                            f"不允许的 Content-Type: {content_type}, "
                            f"仅允许: {', '.join(self.download_allowed_content_types)}"
                        )

                # 检查 Content-Length（如果提供）
                max_bytes = self.download_max_bytes
                content_length = response.headers.get("Content-Length")
                if content_length:
                    try:
                        size = int(content_length)
                        if size > max_bytes:
                            raise ValueError(
                                f"图片大小超过限制: {size} bytes > {max_bytes} bytes"
                            )
                    except (ValueError, TypeError):
                        logger.warning(f"无法解析 Content-Length: {content_length}")

                # 流式读取并检查累计大小
                data = bytearray()
                for chunk in response.iter_content(chunk_size=self.download_chunk_size):
                    if not chunk:
                        continue
                    data.extend(chunk)
                    if len(data) > max_bytes:
                        raise ValueError(
                            f"图片累计大小超过限制: {len(data)} bytes > {max_bytes} bytes"
                        )

                if not data:
                    raise ValueError("图片内容为空")

                logger.debug(f"成功下载图片，大小: {len(data)} bytes")
                return bytes(data)

        except requests.RequestException as e:
            raise ValueError(f"下载图片请求失败: {e}") from e

    @retry_on_error(max_retries=5, base_delay=3)
    def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        model: str = None,
        quality: str = "standard",
        reference_image: Optional[bytes] = None,
        reference_images: Optional[List[bytes]] = None,
        **kwargs
    ) -> bytes:
        """
        生成图片

        Args:
            prompt: 提示词
            size: 图片尺寸 (如 "1024x1024", "2048x2048", "4096x4096")
            model: 模型名称
            quality: 质量 ("standard" 或 "hd")
            reference_image: 单张参考图片数据（向后兼容）
            reference_images: 多张参考图片数据列表
            **kwargs: 其他参数
                - image_index: 指定返回第几张图片（用于多图返回场景）

        Returns:
            图片二进制数据
        """
        if model is None:
            model = self.default_model

        # 支持通过 kwargs 覆盖图片索引
        image_index = kwargs.get("image_index")

        # 收集所有参考图片
        all_reference_images = self._collect_reference_images(
            reference_image, reference_images
        )

        logger.info(
            f"[GENERATE] 开始生成图片: endpoint_type={self.endpoint_type}, "
            f"chat_stream_enabled={self.chat_stream_enabled}, "
            f"reference_images_count={len(all_reference_images)}"
        )

        if self.endpoint_type == 'images':
            logger.info("[GENERATE] 选择路径: images API")
            return self._generate_via_images_api(prompt, size, model, quality)
        elif self.endpoint_type == 'chat':
            # 根据配置选择流式或非流式模式
            if self.chat_stream_enabled:
                logger.info("[GENERATE] 选择路径: chat API (流式)")
                return self._generate_via_chat_api_streaming(
                    prompt, size, model,
                    image_index=image_index,
                    reference_images=all_reference_images
                )
            else:
                logger.info("[GENERATE] 选择路径: chat API (非流式)")
                return self._generate_via_chat_api(
                    prompt, size, model,
                    image_index=image_index,
                    reference_images=all_reference_images
                )
        else:
            raise ValueError(f"不支持的端点类型: {self.endpoint_type}")

    @retry_on_error(max_retries=5, base_delay=3)
    def generate_image_with_candidates(
        self,
        prompt: str,
        size: str = "1024x1024",
        model: str = None,
        quality: str = "standard",
        reference_image: Optional[bytes] = None,
        reference_images: Optional[List[bytes]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        生成图片并返回所有候选图片

        当API返回多张图片时，全部下载并返回，支持前端进行选择。

        Args:
            prompt: 提示词
            size: 图片尺寸
            model: 模型名称
            quality: 质量
            reference_image: 单张参考图片数据（向后兼容）
            reference_images: 多张参考图片数据列表
            **kwargs: 其他参数

        Returns:
            {
                "primary": bytes,           # 主图片（第一张）
                "candidates": [bytes, ...], # 所有候选图片（包含主图片）
                "count": int                # 候选图片总数
            }
        """
        if model is None:
            model = self.default_model

        # 收集所有参考图片
        all_reference_images = self._collect_reference_images(
            reference_image, reference_images
        )

        if self.endpoint_type == 'images':
            # images API 通常只返回一张图片
            image_data = self._generate_via_images_api(prompt, size, model, quality)
            return {
                "primary": image_data,
                "candidates": [image_data],
                "count": 1
            }
        elif self.endpoint_type == 'chat':
            return self._generate_via_chat_api_with_candidates(
                prompt,
                size,
                model,
                reference_images=all_reference_images
            )
        else:
            raise ValueError(f"不支持的端点类型: {self.endpoint_type}")

    def _generate_via_images_api(
        self,
        prompt: str,
        size: str,
        model: str,
        quality: str
    ) -> bytes:
        """通过 /v1/images/generations 端点生成"""
        url = f"{self.base_url.rstrip('/')}/v1/images/generations"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": size,
            "response_format": "b64_json"  # 使用base64格式更可靠
        }

        # 如果模型支持quality参数
        if quality and model.startswith('dall-e'):
            payload["quality"] = quality

        response = requests.post(url, headers=headers, json=payload, timeout=180)

        if response.status_code != 200:
            raise Exception(f"API请求失败: {response.status_code} - {response.text}")

        result = response.json()

        if "data" not in result or len(result["data"]) == 0:
            raise ValueError("API未返回图片数据")

        image_data = result["data"][0]

        # 处理base64格式
        if "b64_json" in image_data:
            return base64.b64decode(image_data["b64_json"])

        # 处理URL格式
        elif "url" in image_data:
            img_response = requests.get(image_data["url"], timeout=60)
            if img_response.status_code == 200:
                return img_response.content
            else:
                raise Exception(f"下载图片失败: {img_response.status_code}")

        else:
            raise ValueError("未找到图片数据")

    def _parse_sse_stream(self, response) -> str:
        """
        解析SSE流式响应，累积所有content并返回最终完整内容

        包含多重安全防护：
        - 最大内容字节数限制
        - 最大事件数限制
        - 心跳超时检测

        Args:
            response: requests的Response对象（stream=True）

        Returns:
            累积的完整content字符串

        Raises:
            ValueError: SSE格式错误、超过限制或解析失败
            TimeoutError: 心跳超时
            Exception: 流式读取连接错误
        """
        import json

        accumulated_content = []

        # 防护限制
        max_bytes = self.sse_max_content_bytes
        max_events = self.sse_max_events
        heartbeat_timeout = self.sse_heartbeat_timeout

        # 状态追踪
        last_event_time = time.time()
        total_bytes = 0
        event_count = 0

        logger.debug(
            f"开始解析 SSE 流，限制: max_bytes={max_bytes}, "
            f"max_events={max_events}, heartbeat_timeout={heartbeat_timeout}s"
        )

        try:
            for line in response.iter_lines(decode_unicode=True):
                # 更新心跳时间（无论行内容如何）
                current_time = time.time()
                elapsed = current_time - last_event_time
                last_event_time = current_time

                # 检查心跳超时
                if elapsed > heartbeat_timeout:
                    raise TimeoutError(
                        f"SSE 心跳超时: {elapsed:.1f}s > {heartbeat_timeout}s，"
                        f"已接收 {event_count} 个事件"
                    )

                # 空行：跳过
                if not line:
                    continue

                line = line.strip()

                # 跳过注释行（不计入事件数）
                if line.startswith(':'):
                    continue

                # 计入事件数（仅非空行且非注释行）
                event_count += 1

                # 检查事件数限制
                if event_count > max_events:
                    raise ValueError(
                        f"SSE 事件数超过限制: {event_count} > {max_events}"
                    )

                # 处理 data: 开头的行
                if line.startswith('data:'):
                    data_str = line[5:].strip()

                    # 检查是否为结束标记
                    if data_str == '[DONE]':
                        logger.info(f"SSE 流结束标记 [DONE]，共 {event_count} 个事件")
                        break

                    try:
                        # 解析JSON数据
                        data = json.loads(data_str)

                        # 提取content（支持OpenAI格式）
                        if 'choices' in data and len(data['choices']) > 0:
                            choice = data['choices'][0]
                            delta = choice.get('delta', {})
                            content = delta.get('content', '')

                            if content:
                                accumulated_content.append(content)

                                # 检查累计字节数
                                content_bytes = len(content.encode('utf-8', errors='ignore'))
                                total_bytes += content_bytes

                                if total_bytes > max_bytes:
                                    raise ValueError(
                                        f"SSE 内容累计超过限制: {total_bytes} bytes > {max_bytes} bytes"
                                    )

                                logger.debug(f"SSE 接收内容片段: {content[:50]}...")

                    except json.JSONDecodeError:
                        # 如果不是JSON，可能是纯文本格式（如模型的思考过程）
                        logger.debug(f"SSE 数据非 JSON 格式: {data_str[:100]}")

                        # 纯文本也计入累计字节数
                        text_bytes = len(data_str.encode('utf-8', errors='ignore'))
                        total_bytes += text_bytes

                        if total_bytes > max_bytes:
                            raise ValueError(
                                f"SSE 内容累计超过限制: {total_bytes} bytes > {max_bytes} bytes"
                            )

                        accumulated_content.append(data_str)

        except (TimeoutError, ValueError) as e:
            # 预期的限制类错误，直接抛出
            logger.error(f"SSE 流解析失败: {e}")
            raise
        except Exception as e:
            # 其他异常，包装后抛出
            logger.error(f"SSE 流解析异常: {e}")
            raise Exception(f"SSE 流解析异常: {e}") from e

        final_content = ''.join(accumulated_content)
        logger.info(
            f"SSE 流解析完成: 长度={len(final_content)}, "
            f"事件数={event_count}, 字节数={total_bytes}"
        )

        return final_content

    @retry_on_error(max_retries=5, base_delay=3)
    def _generate_via_chat_api_streaming(
        self,
        prompt: str,
        size: str,
        model: str,
        image_index: Optional[int] = None,
        reference_images: Optional[List[bytes]] = None
    ) -> bytes:
        """
        通过 /v1/chat/completions 端点使用流式模式生成图片

        使用SSE流式响应，避免因图片生成耗时导致的524超时错误。
        服务端会在生成过程中持续发送装饰性"思考过程"消息保持连接活跃，
        最终返回包含图片URL的Markdown文本。

        Args:
            prompt: 提示词
            size: 图片尺寸
            model: 模型名称
            image_index: 指定返回第几张图片（None表示使用配置的默认值）
            reference_images: 参考图片数据列表

        Returns:
            图片二进制数据

        Raises:
            ValueError: 响应格式不符合预期或无法提取图片数据
            Exception: API请求失败或图片下载失败
        """
        logger.info("[STREAMING] 使用流式模式生成图片")

        # 预处理提示词
        safe_prompt = self._prepare_chat_prompt(prompt)

        # 构造请求
        request = self._build_chat_request(
            model=model,
            size=size,
            prompt=safe_prompt,
            reference_images=reference_images or [],
            stream=True
        )

        ref_count = len(reference_images) if reference_images else 0
        logger.info(
            f"[STREAMING] Chat API 流式请求: model={model}, size={size}, "
            f"stream={request['payload'].get('stream')}, prompt_length={len(safe_prompt)}, "
            f"reference_images={ref_count}"
        )

        # 发送流式请求
        response = requests.post(
            request["url"],
            headers=request["headers"],
            json=request["payload"],
            stream=True,
            timeout=(10, self.chat_stream_idle_timeout)
        )

        if response.status_code != 200:
            raise Exception(
                f"API请求失败: {response.status_code} - {response.text[:500]}"
            )

        # 解析SSE流
        content = self._parse_sse_stream(response)

        # 关闭连接
        response.close()

        if not content:
            raise ValueError("SSE流中未返回任何内容")

        # 验证并处理内容
        content = self._validate_and_extract_content(content, prompt)
        return self._process_chat_content(content, image_index=image_index, return_candidates=False)

    def _generate_via_chat_api(
        self,
        prompt: str,
        size: str,
        model: str,
        image_index: Optional[int] = None,
        reference_images: Optional[List[bytes]] = None
    ) -> bytes:
        """
        通过 /v1/chat/completions 端点生成图片

        某些服务商（如Nano-Banana-Pro）使用chat接口返回图片，
        支持以下返回格式：
        1. base64 data URL: data:image/png;base64,...
        2. Markdown图片链接: ![alt](url)（可能返回多张图片）

        Args:
            prompt: 提示词
            size: 图片尺寸
            model: 模型名称
            image_index: 指定返回第几张图片（None表示使用配置的默认值）
            reference_images: 参考图片数据列表

        Returns:
            图片二进制数据

        Raises:
            ValueError: 响应格式不符合预期或无法提取图片数据
            Exception: API请求失败或图片下载失败
        """
        logger.info("[NON-STREAMING] 使用非流式模式生成图片")

        # 预处理提示词
        safe_prompt = self._prepare_chat_prompt(prompt)

        # 构造请求
        request = self._build_chat_request(
            model=model,
            size=size,
            prompt=safe_prompt,
            reference_images=reference_images or [],
            stream=False
        )

        ref_count = len(reference_images) if reference_images else 0
        logger.info(
            f"[NON-STREAMING] Chat API 请求: model={model}, size={size}, "
            f"prompt_length={len(safe_prompt)}, reference_images={ref_count}"
        )

        response = requests.post(
            request["url"],
            headers=request["headers"],
            json=request["payload"],
            timeout=DEFAULT_REQUEST_TIMEOUT
        )

        if response.status_code != 200:
            raise Exception(f"API请求失败: {response.status_code} - {response.text}")

        result = response.json()

        # 验证响应结构
        if "choices" not in result or len(result["choices"]) == 0:
            raise ValueError("chat API 响应缺少 choices 字段或为空")

        choice = result["choices"][0]
        if "message" not in choice:
            raise ValueError("chat API 响应缺少 message 字段")

        message = choice["message"]
        content = self._extract_content_from_message(message)

        # 验证并处理内容
        content = self._validate_and_extract_content(content, prompt)
        return self._process_chat_content(content, image_index=image_index, return_candidates=False)

    def _generate_via_chat_api_with_candidates(
        self,
        prompt: str,
        size: str,
        model: str,
        reference_images: Optional[List[bytes]] = None
    ) -> Dict[str, Any]:
        """
        通过 chat API 生成图片，并返回所有候选图片

        根据 chat_stream_enabled 配置自动选择流式或非流式模式

        Args:
            prompt: 提示词
            size: 图片尺寸
            model: 模型名称
            reference_images: 参考图片数据列表

        Returns:
            {
                "primary": bytes,
                "candidates": [bytes, ...],
                "count": int
            }
        """
        # 根据配置选择流式或非流式模式
        if self.chat_stream_enabled:
            return self._generate_via_chat_api_streaming_with_candidates(
                prompt, size, model, reference_images=reference_images
            )
        else:
            return self._generate_via_chat_api_non_streaming_with_candidates(
                prompt, size, model, reference_images=reference_images
            )

    def _generate_via_chat_api_non_streaming_with_candidates(
        self,
        prompt: str,
        size: str,
        model: str,
        reference_images: Optional[List[bytes]] = None
    ) -> Dict[str, Any]:
        """
        通过 chat API 非流式模式生成图片，并返回所有候选图片

        Args:
            prompt: 提示词
            size: 图片尺寸
            model: 模型名称
            reference_images: 参考图片数据列表

        Returns:
            {
                "primary": bytes,
                "candidates": [bytes, ...],
                "count": int
            }
        """
        # 预处理提示词
        safe_prompt = self._prepare_chat_prompt(prompt)

        # 构造请求
        request = self._build_chat_request(
            model=model,
            size=size,
            prompt=safe_prompt,
            reference_images=reference_images or [],
            stream=False
        )

        ref_count = len(reference_images) if reference_images else 0
        logger.info(
            f"[NON-STREAMING] Chat API 请求 (候选模式): model={model}, size={size}, "
            f"prompt_length={len(safe_prompt)}, reference_images={ref_count}"
        )

        response = requests.post(
            request["url"],
            headers=request["headers"],
            json=request["payload"],
            timeout=DEFAULT_REQUEST_TIMEOUT
        )

        if response.status_code != 200:
            raise Exception(f"API请求失败: {response.status_code} - {response.text}")

        result = response.json()

        # 验证响应结构
        if "choices" not in result or len(result["choices"]) == 0:
            raise ValueError("chat API 响应缺少 choices 字段或为空")

        choice = result["choices"][0]
        if "message" not in choice:
            raise ValueError("chat API 响应缺少 message 字段")

        message = choice["message"]
        content = self._extract_content_from_message(message)

        # 验证并处理内容（候选模式）
        content = self._validate_and_extract_content(content, prompt)
        return self._process_chat_content(content, return_candidates=True)

    def _generate_via_chat_api_streaming_with_candidates(
        self,
        prompt: str,
        size: str,
        model: str,
        reference_images: Optional[List[bytes]] = None
    ) -> Dict[str, Any]:
        """
        通过 chat API 流式模式生成图片，并返回所有候选图片

        Args:
            prompt: 提示词
            size: 图片尺寸
            model: 模型名称
            reference_images: 参考图片数据列表

        Returns:
            {
                "primary": bytes,
                "candidates": [bytes, ...],
                "count": int
            }
        """
        logger.info("[STREAMING] 使用流式模式生成候选图片")

        # 预处理提示词
        safe_prompt = self._prepare_chat_prompt(prompt)

        # 构造请求
        request = self._build_chat_request(
            model=model,
            size=size,
            prompt=safe_prompt,
            reference_images=reference_images or [],
            stream=True
        )

        logger.info(
            f"[STREAMING] Chat API 请求 (候选模式): model={model}, size={size}, "
            f"stream={request['payload'].get('stream')}, prompt_length={len(safe_prompt)}"
        )

        # 使用流式请求，设置合理的超时时间
        response = requests.post(
            request["url"],
            headers=request["headers"],
            json=request["payload"],
            stream=True,
            timeout=(10, self.chat_stream_idle_timeout)
        )

        if response.status_code != 200:
            raise Exception(
                f"API请求失败: {response.status_code} - {response.text[:500]}"
            )

        # 解析SSE流，累积所有content
        content = self._parse_sse_stream(response)

        # 关闭连接
        response.close()

        if not content:
            raise ValueError("SSE流中未返回任何内容")

        # 验证并处理内容（候选模式）
        content = self._validate_and_extract_content(content, prompt)
        return self._process_chat_content(content, return_candidates=True)

    def _download_all_images_from_urls(self, urls: List[str]) -> Dict[str, Any]:
        """
        并发下载所有候选图片

        Args:
            urls: 图片URL列表

        Returns:
            {
                "primary": bytes,           # 第一张成功下载的图片
                "candidates": [bytes, ...], # 所有成功下载的图片
                "count": int                # 成功下载的图片数量
            }

        Raises:
            Exception: 所有图片下载均失败
        """
        if not urls:
            raise ValueError("图片URL列表为空")

        def download_single_image(idx: int, url: str) -> tuple:
            """
            下载或解码单张图片（支持 HTTP URL 和 base64 data URL）

            Args:
                idx: 图片索引
                url: 图片URL（可以是 http(s):// 或 data:image/...）

            Returns:
                (idx, image_data, error) 元组
            """
            try:
                logger.info(f"处理候选图片 {idx + 1}/{len(urls)}: {url[:100]}")
                img_data = self._download_or_decode_image(url)
                logger.info(f"成功获取候选图片 {idx + 1}")
                return (idx, img_data, None)

            except Exception as e:
                logger.warning(f"候选图片 {idx + 1} 处理异常: {e}")
                return (idx, None, str(e))

        # 使用线程池并发下载，最多10个线程
        max_workers = min(len(urls), 10)
        results = [None] * len(urls)  # 保持顺序
        errors = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有下载任务
            future_to_idx = {
                executor.submit(download_single_image, idx, url): idx
                for idx, url in enumerate(urls)
            }

            # 收集结果
            for future in as_completed(future_to_idx):
                idx, image_data, error = future.result()
                if image_data:
                    results[idx] = image_data
                else:
                    errors.append(error)

        # 过滤掉 None 值，保持原始顺序
        candidates = [img for img in results if img is not None]

        if not candidates:
            raise Exception(
                f"所有 {len(urls)} 张候选图片下载失败: {'; '.join(errors[:3])}"
            )

        logger.info(f"候选图片下载完成: 成功 {len(candidates)}/{len(urls)}")

        return {
            "primary": candidates[0],
            "candidates": candidates,
            "count": len(candidates)
        }

    def _strip_markdown_code_block(self, text: str) -> str:
        """
        移除 Markdown 代码块标记

        Args:
            text: 可能包含代码块标记的文本

        Returns:
            清理后的文本
        """
        text = text.strip()
        if not text.startswith("```"):
            return text

        lines = text.split("\n")
        if len(lines) < 2:
            return text

        # 去掉首行的 ``` 和末行的 ```
        inner_lines = []
        for line in lines[1:]:
            if line.strip() == "```":
                break
            inner_lines.append(line)

        return "\n".join(inner_lines).strip()

    def _prepare_chat_prompt(self, prompt: str) -> str:
        """
        对 chat 接口的提示词进行预处理（长度检查和截断）

        不同服务商可能有不同的长度限制，通过配置控制：
        - chat_prompt_max_chars: 允许的最大字符数（可选）
        - chat_prompt_strategy: 超出限制时的处理策略（可选，默认 "truncate"）
          - "truncate": 记录警告日志并截断提示词后继续请求
          - "error": 抛出 ValueError，提示用户缩短提示词

        Args:
            prompt: 原始提示词

        Returns:
            处理后的提示词（可能被截断）

        Raises:
            ValueError: 当策略为 "error" 且提示词超长时
        """
        max_chars = self.config.get("chat_prompt_max_chars")
        if not isinstance(max_chars, int) or max_chars <= 0:
            # 未配置长度限制时直接返回原始提示词
            return prompt

        if len(prompt) <= max_chars:
            return prompt

        strategy = self.config.get("chat_prompt_strategy", "truncate")
        if strategy == "error":
            raise ValueError(
                f"提示词长度为 {len(prompt)} 字符，超过当前服务商配置的上限 "
                f"{max_chars} 字符，请精简提示词后重试。"
            )

        # 默认策略：截断并给出日志提示
        logger.warning(
            f"提示词长度超过当前服务商配置的上限，已自动截断: "
            f"original_len={len(prompt)}, max_chars={max_chars}"
        )
        return prompt[:max_chars]

    def _raise_if_chat_content_is_error(self, content: str, prompt: str) -> None:
        """
        检查 chat 接口返回的内容是否为明显的错误提示

        专门识别长度限制类错误，提供更友好的错误信息。

        Args:
            content: API 返回的内容
            prompt: 原始提示词（用于计算长度）

        Raises:
            ValueError: 当检测到错误提示时
        """
        if not content:
            return

        # 清理内容（去除markdown代码块格式）
        text = self._strip_markdown_code_block(content)

        # 提示词长度超限相关的关键字（区分纯文本和正则）
        plain_keywords = [
            "不能超过",
            "不得超过",
            "超出最大长度",
            "too long",
        ]

        regex_patterns = [
            r"超过.*字符",
            r"exceeds.*maximum.*length",
            r"maximum.*length.*exceeded",
        ]

        # 检查是否包含长度限制相关的关键字
        has_length_error = (
            any(keyword in text for keyword in plain_keywords) or
            any(re.search(pattern, text, re.IGNORECASE) for pattern in regex_patterns)
        )

        if has_length_error:
            # 尝试从提示中解析具体上限，例如："不能超过 1600 个字符"
            match = re.search(r"(\d+)\s*个?字符", text)
            if match:
                limit = match.group(1)
                raise ValueError(
                    f"图片生成失败：提示词长度超过服务商限制。"
                    f"当前长度为 {len(prompt)} 字符，建议控制在 {limit} 字符以内。"
                )

            # 未能解析出具体上限时，直接附带原始服务端提示
            raise ValueError(
                f"图片生成失败：提示词长度可能超过服务商限制。"
                f"当前长度为 {len(prompt)} 字符，服务端返回: {text[:200]}"
            )

    def _extract_content_from_message(self, message: Dict[str, Any]) -> str:
        """
        从message中提取content字符串

        支持两种格式：
        1. 字符串: {"content": "text"}
        2. 分段内容: {"content": [{"type": "text", "text": "..."}]}

        Args:
            message: API响应中的message对象

        Returns:
            提取的文本内容

        Raises:
            ValueError: content字段缺失或类型不支持
        """
        content = message.get("content")

        # 处理分段内容格式
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
            return "\n".join(text_parts)

        # 处理字符串格式
        if isinstance(content, str):
            return content

        raise ValueError(
            f"chat API 响应中的 content 类型不受支持: {type(content)}"
        )

    def _detect_api_error_message(self, content: str) -> Optional[str]:
        """
        检测API响应中的错误消息

        某些图片生成API在出错时会在content中返回错误文本，
        而非标准的HTTP错误码。此方法识别这些场景。

        Args:
            content: 从API响应中提取的content字符串

        Returns:
            如果检测到错误消息，返回错误内容；否则返回None
        """
        if not content or not isinstance(content, str):
            return None

        # 清理内容（去除markdown代码块格式）
        cleaned = self._strip_markdown_code_block(content)

        # 错误模式列表：(模式, 是否为正则表达式)
        error_patterns = [
            # 字符/长度限制相关
            (r"不能超过\s*\d+\s*个字符", True),
            (r"超过.*字符限制", True),
            (r"prompt.*too long", True),
            (r"exceeds.*limit", True),
            (r"maximum.*length", True),
            # 内容审核相关
            ("内容违规", False),
            ("content policy", False),
            ("违反.*政策", True),
            # 配额/限制相关
            ("配额不足", False),
            ("quota exceeded", False),
            ("rate limit", False),
            # 参数错误相关
            ("参数错误", False),
            ("invalid parameter", False),
            ("参数无效", False),
        ]

        content_lower = cleaned.lower()

        for pattern, is_regex in error_patterns:
            if is_regex:
                if re.search(pattern, cleaned, re.IGNORECASE):
                    return cleaned
            else:
                if pattern.lower() in content_lower:
                    return cleaned

        # 额外检查：如果content很短且不包含图片相关内容，可能是错误
        if len(cleaned) < 500:
            # 检查是否完全不包含图片相关的内容
            has_image_indicator = (
                cleaned.startswith("data:image") or
                "![" in cleaned or
                re.search(r'https?://.*\.(png|jpg|jpeg|gif|webp)', cleaned, re.I)
            )
            if not has_image_indicator:
                # 检查是否像是纯文本错误消息（无URL、无markdown图片语法）
                if not re.search(r'https?://', cleaned):
                    # 可能是错误消息，但不确定，记录日志但不阻断
                    logger.warning(
                        f"API响应可能为错误消息（短文本无图片指示）: {cleaned[:100]}"
                    )

        return None

    def _decode_base64_image(self, data_url: str) -> bytes:
        """
        解码base64格式的图片数据

        Args:
            data_url: data URL格式的字符串 (data:image/png;base64,...)

        Returns:
            图片二进制数据

        Raises:
            ValueError: data URL格式不正确
        """
        try:
            # 分割并提取base64部分
            if "," not in data_url:
                raise ValueError("data URL 缺少逗号分隔符")
            base64_data = data_url.split(",", 1)[1]
            return base64.b64decode(base64_data)
        except (IndexError, base64.binascii.Error) as e:
            raise ValueError(
                f"chat API 响应中的 base64 图片数据格式不正确: {str(e)}"
            ) from e

    def _extract_image_urls_from_markdown(self, content: str) -> List[str]:
        """
        从Markdown文本中提取所有图片URL（包括 base64 data URL）

        支持以下格式：
        1. ![alt](http://example.com/image.jpg)
        2. ![alt](data:image/jpeg;base64,...)

        Args:
            content: Markdown格式的文本

        Returns:
            图片URL列表（可能为空，包含 http(s) URL 和 data URL）
        """
        if not content:
            return []

        try:
            # 使用正则表达式提取所有 ![...](url) 格式的URL
            urls = re.findall(MARKDOWN_IMAGE_PATTERN, content)
            # 过滤掉空字符串和无效URL
            valid_urls = [
                url.strip() for url in urls
                if isinstance(url, str) and url.strip()
            ]
            return valid_urls
        except re.error as e:
            logger.warning(f"Markdown 图片 URL 正则解析异常: {e}")
            return []

    def _download_or_decode_image(self, url: str) -> bytes:
        """
        下载或解码图片（支持 HTTP URL 和 base64 data URL）

        Args:
            url: 图片 URL（可以是 http(s):// 或 data:image/...）

        Returns:
            图片二进制数据

        Raises:
            ValueError: URL 格式不支持或解码失败
        """
        # 情况1: base64 data URL
        if url.startswith("data:image"):
            logger.info("检测到 base64 data URL，直接解码")
            return self._decode_base64_image(url)

        # 情况2: HTTP(S) URL
        if url.startswith(("http://", "https://")):
            return self._stream_download_image(url)

        # 不支持的格式
        raise ValueError(f"不支持的 URL 格式: {url[:100]}")

    def _download_image_from_urls(
        self,
        urls: List[str],
        image_index: Optional[int] = None
    ) -> bytes:
        """
        从URL列表中下载图片（支持 HTTP URL 和 base64 data URL）

        支持fallback机制：如果指定索引的图片下载失败，会尝试其他图片

        Args:
            urls: 图片URL列表（可包含 http(s):// 或 data:image/... 格式）
            image_index: 指定下载第几张图片（None表示使用配置的默认值）

        Returns:
            图片二进制数据

        Raises:
            Exception: 所有图片下载均失败
        """
        if not urls:
            raise ValueError("图片URL列表为空")

        # 确定要使用的索引
        target_index = self._determine_image_index(image_index, len(urls))

        # 构造下载顺序：优先尝试指定索引，其次依次尝试其他索引作为fallback
        indices_to_try = [target_index] + [
            i for i in range(len(urls)) if i != target_index
        ]

        last_error = None
        for idx in indices_to_try:
            url = urls[idx]
            try:
                logger.info(f"尝试处理第 {idx} 张图片: {url[:100]}")
                image_data = self._download_or_decode_image(url)
                logger.info(f"成功获取第 {idx} 张图片")
                return image_data

            except Exception as e:
                logger.warning(f"处理图片异常 (索引={idx}): {e}")
                last_error = e

        # 所有尝试都失败
        error_msg = f"所有图片链接处理失败，共 {len(urls)} 个"
        if last_error:
            raise Exception(error_msg) from last_error
        else:
            raise Exception(error_msg)

    def _determine_image_index(
        self,
        requested_index: Optional[int],
        total_images: int
    ) -> int:
        """
        确定最终使用的图片索引

        Args:
            requested_index: 请求的索引（None表示使用配置的默认值）
            total_images: 总图片数量

        Returns:
            有效的图片索引（0 到 total_images-1）
        """
        # 优先使用请求的索引，否则使用配置的默认索引
        if requested_index is not None:
            index = self._parse_image_index(requested_index)
        else:
            index = self.image_index

        # 边界检查
        if index >= total_images:
            logger.warning(
                f"image_index 超出范围: {index}，"
                f"总图片数: {total_images}，已回退为 0"
            )
            return 0

        return index

    def get_supported_sizes(self) -> list:
        """获取支持的图片尺寸"""
        # 默认OpenAI支持的尺寸
        return self.config.get('supported_sizes', [
            "1024x1024",
            "1792x1024",
            "1024x1792",
            "2048x2048",
            "4096x4096"
        ])
