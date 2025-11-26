"""OpenAI 兼容接口图片生成器"""
import time
import random
import base64
import re
import logging
from functools import wraps
from typing import Dict, Any, List, Optional
import requests
from .base import ImageGeneratorBase

# 配置日志
logger = logging.getLogger(__name__)


# 常量定义
DEFAULT_IMAGE_INDEX = 0
DEFAULT_REQUEST_TIMEOUT = 180
DEFAULT_DOWNLOAD_TIMEOUT = 60
MARKDOWN_IMAGE_PATTERN = r'!\[[^\]]*\]\(([^)\s]+)[^)]*\)'


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

    @retry_on_error(max_retries=5, base_delay=3)
    def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        model: str = None,
        quality: str = "standard",
        **kwargs
    ) -> bytes:
        """
        生成图片

        Args:
            prompt: 提示词
            size: 图片尺寸 (如 "1024x1024", "2048x2048", "4096x4096")
            model: 模型名称
            quality: 质量 ("standard" 或 "hd")
            **kwargs: 其他参数
                - image_index: 指定返回第几张图片（用于多图返回场景）

        Returns:
            图片二进制数据
        """
        if model is None:
            model = self.default_model

        # 支持通过 kwargs 覆盖图片索引
        image_index = kwargs.get("image_index")

        if self.endpoint_type == 'images':
            return self._generate_via_images_api(prompt, size, model, quality)
        elif self.endpoint_type == 'chat':
            # 根据配置选择流式或非流式模式
            if self.chat_stream_enabled:
                return self._generate_via_chat_api_streaming(
                    prompt, size, model, image_index=image_index
                )
            else:
                return self._generate_via_chat_api(
                    prompt, size, model, image_index=image_index
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

        if self.endpoint_type == 'images':
            # images API 通常只返回一张图片
            image_data = self._generate_via_images_api(prompt, size, model, quality)
            return {
                "primary": image_data,
                "candidates": [image_data],
                "count": 1
            }
        elif self.endpoint_type == 'chat':
            return self._generate_via_chat_api_with_candidates(prompt, size, model)
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

        Args:
            response: requests的Response对象（stream=True）

        Returns:
            累积的完整content字符串

        Raises:
            ValueError: SSE格式错误或解析失败
            Exception: 流式读取超时或连接错误
        """
        import json

        accumulated_content = []

        try:
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue

                line = line.strip()

                # 跳过注释行
                if line.startswith(':'):
                    continue

                # 处理 data: 开头的行
                if line.startswith('data:'):
                    data_str = line[5:].strip()

                    # 检查是否为结束标记
                    if data_str == '[DONE]':
                        logger.info("SSE流结束标记 [DONE]")
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
                                logger.debug(f"SSE接收内容片段: {content[:50]}")

                    except json.JSONDecodeError:
                        # 如果不是JSON，可能是纯文本格式
                        logger.warning(f"SSE数据非JSON格式: {data_str[:100]}")
                        accumulated_content.append(data_str)

        except Exception as e:
            logger.error(f"SSE流解析异常: {e}")
            raise

        final_content = ''.join(accumulated_content)
        logger.info(f"SSE流累积内容长度: {len(final_content)}")

        return final_content

    @retry_on_error(max_retries=5, base_delay=3)
    def _generate_via_chat_api_streaming(
        self,
        prompt: str,
        size: str,
        model: str,
        image_index: Optional[int] = None
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

        Returns:
            图片二进制数据

        Raises:
            ValueError: 响应格式不符合预期或无法提取图片数据
            Exception: API请求失败或图片下载失败
        """
        logger.info("🔄 使用流式模式生成图片")

        # 在发送请求前对提示词进行长度检查和预处理
        safe_prompt = self._prepare_chat_prompt(prompt)

        url = f"{self.base_url.rstrip('/')}/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": safe_prompt
                }
            ],
            "temperature": 1.0,
            "size": size,
            "stream": True  # 启用流式模式
        }

        logger.info(
            f"Chat API 流式请求: model={model}, size={size}, stream={payload['stream']}"
        )

        # 使用流式请求，设置合理的超时时间
        response = requests.post(
            url,
            headers=headers,
            json=payload,
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

        # 优先检查是否为明显的错误提示
        self._raise_if_chat_content_is_error(content, prompt)

        # 检测API返回的其他错误消息
        error_message = self._detect_api_error_message(content)
        if error_message:
            raise ValueError(f"图片生成API返回错误: {error_message}")

        # 情况一：base64 data URL（向后兼容）
        if content.startswith("data:image"):
            return self._decode_base64_image(content)

        # 情况二：Markdown图片链接（主要处理场景）
        image_urls = self._extract_image_urls_from_markdown(content)
        if image_urls:
            logger.info(f"从流式响应中提取到 {len(image_urls)} 个图片URL")
            return self._download_image_from_urls(image_urls, image_index)

        # 无法识别的格式
        preview = content[:200].replace("\n", "\\n")
        raise ValueError(
            f"SSE流式响应中未找到可识别的图片数据格式，content 预览: {preview}"
        )

    def _generate_via_chat_api(
        self,
        prompt: str,
        size: str,
        model: str,
        image_index: Optional[int] = None
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

        Returns:
            图片二进制数据

        Raises:
            ValueError: 响应格式不符合预期或无法提取图片数据
            Exception: API请求失败或图片下载失败
        """
        logger.info("📡 使用非流式模式生成图片")

        # 在发送请求前对提示词进行长度检查和预处理
        safe_prompt = self._prepare_chat_prompt(prompt)

        url = f"{self.base_url.rstrip('/')}/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": safe_prompt
                }
            ],
            "temperature": 1.0,
            "size": size
        }

        logger.info(f"Chat API 请求 payload: model={model}, size={size}")

        response = requests.post(
            url, headers=headers, json=payload, timeout=DEFAULT_REQUEST_TIMEOUT
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

        # 优先检查是否为明显的错误提示（如长度限制错误）
        self._raise_if_chat_content_is_error(content, prompt)

        # 检测API返回的其他错误消息
        error_message = self._detect_api_error_message(content)
        if error_message:
            raise ValueError(f"图片生成API返回错误: {error_message}")

        # 情况一：base64 data URL（向后兼容）
        if content.startswith("data:image"):
            return self._decode_base64_image(content)

        # 情况二：Markdown图片链接（支持多图）
        image_urls = self._extract_image_urls_from_markdown(content)
        if image_urls:
            return self._download_image_from_urls(image_urls, image_index)

        # 无法识别的格式
        preview = content[:200].replace("\n", "\\n")
        raise ValueError(
            f"chat API 响应中未找到可识别的图片数据格式，content 预览: {preview}"
        )

    def _generate_via_chat_api_with_candidates(
        self,
        prompt: str,
        size: str,
        model: str
    ) -> Dict[str, Any]:
        """
        通过 chat API 生成图片，并返回所有候选图片

        Args:
            prompt: 提示词
            size: 图片尺寸
            model: 模型名称

        Returns:
            {
                "primary": bytes,
                "candidates": [bytes, ...],
                "count": int
            }
        """
        # 在发送请求前对提示词进行长度检查和预处理
        safe_prompt = self._prepare_chat_prompt(prompt)

        url = f"{self.base_url.rstrip('/')}/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": safe_prompt
                }
            ],
            "temperature": 1.0,
            "size": size
        }

        logger.info(f"Chat API 请求 payload: model={model}, size={size}")

        response = requests.post(
            url, headers=headers, json=payload, timeout=DEFAULT_REQUEST_TIMEOUT
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

        # 优先检查是否为明显的错误提示
        self._raise_if_chat_content_is_error(content, prompt)

        # 检测API返回的其他错误消息
        error_message = self._detect_api_error_message(content)
        if error_message:
            raise ValueError(f"图片生成API返回错误: {error_message}")

        # 情况一：base64 data URL
        if content.startswith("data:image"):
            image_data = self._decode_base64_image(content)
            return {
                "primary": image_data,
                "candidates": [image_data],
                "count": 1
            }

        # 情况二：Markdown图片链接（下载所有候选图片）
        image_urls = self._extract_image_urls_from_markdown(content)
        if image_urls:
            return self._download_all_images_from_urls(image_urls)

        # 无法识别的格式
        preview = content[:200].replace("\n", "\\n")
        raise ValueError(
            f"chat API 响应中未找到可识别的图片数据格式，content 预览: {preview}"
        )

    def _download_all_images_from_urls(self, urls: List[str]) -> Dict[str, Any]:
        """
        下载所有候选图片

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

        candidates = []
        errors = []

        for idx, url in enumerate(urls):
            try:
                logger.info(f"下载候选图片 {idx + 1}/{len(urls)}: {url[:100]}")
                img_response = requests.get(url, timeout=DEFAULT_DOWNLOAD_TIMEOUT)

                if img_response.status_code == 200 and img_response.content:
                    candidates.append(img_response.content)
                    logger.info(f"成功下载候选图片 {idx + 1}")
                else:
                    error_msg = f"下载失败: status={img_response.status_code}"
                    logger.warning(f"候选图片 {idx + 1} {error_msg}")
                    errors.append(error_msg)

            except Exception as e:
                logger.warning(f"候选图片 {idx + 1} 下载异常: {e}")
                errors.append(str(e))

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
        从Markdown文本中提取所有图片URL

        Args:
            content: Markdown格式的文本

        Returns:
            图片URL列表（可能为空）
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

    def _download_image_from_urls(
        self,
        urls: List[str],
        image_index: Optional[int] = None
    ) -> bytes:
        """
        从URL列表中下载图片

        支持fallback机制：如果指定索引的图片下载失败，会尝试其他图片

        Args:
            urls: 图片URL列表
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
                logger.info(f"尝试下载第 {idx} 张图片: {url}")
                img_response = requests.get(url, timeout=DEFAULT_DOWNLOAD_TIMEOUT)

                if img_response.status_code == 200 and img_response.content:
                    logger.info(f"成功下载第 {idx} 张图片")
                    return img_response.content
                else:
                    error_msg = (
                        f"下载图片失败: status={img_response.status_code}, "
                        f"索引={idx}"
                    )
                    logger.warning(error_msg)
                    last_error = Exception(error_msg)

            except Exception as e:
                logger.warning(f"下载图片异常(索引={idx}): {e}")
                last_error = e

        # 所有尝试都失败
        error_msg = f"所有图片链接下载失败，共 {len(urls)} 个"
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
