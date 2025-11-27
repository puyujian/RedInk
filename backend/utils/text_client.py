"""Text API 客户端封装"""
import os
import time
import random
import base64
import json
import logging
import requests
from functools import wraps
from typing import List, Optional, Union
from dotenv import load_dotenv
from .image_compressor import compress_image

load_dotenv()

logger = logging.getLogger(__name__)


def retry_on_429(max_retries=3, base_delay=2):
    """429 错误自动重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_str = str(e)
                    if "429" in error_str or "rate" in error_str.lower():
                        if attempt < max_retries - 1:
                            wait_time = (base_delay ** attempt) + random.uniform(0, 1)
                            print(f"[重试] 遇到限流，{wait_time:.1f}秒后重试 (尝试 {attempt + 2}/{max_retries})")
                            time.sleep(wait_time)
                            continue
                    raise
            raise Exception(f"重试 {max_retries} 次后仍失败")
        return wrapper
    return decorator


class TextChatClient:
    """Text API 客户端封装类"""

    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or os.getenv("TEXT_API_KEY") or os.getenv("BLTCY_API_KEY")
        if not self.api_key:
            raise ValueError("TEXT_API_KEY 环境变量未设置")

        self.base_url = base_url or os.getenv("TEXT_API_BASE_URL", "https://api.example.com")
        self.chat_endpoint = f"{self.base_url}/v1/chat/completions"

    def _encode_image_to_base64(self, image_data: bytes) -> str:
        """将图片数据编码为 base64"""
        return base64.b64encode(image_data).decode('utf-8')

    def _build_content_with_images(
        self,
        text: str,
        images: List[Union[bytes, str]] = None
    ) -> Union[str, List[dict]]:
        """
        构建包含图片的 content

        Args:
            text: 文本内容
            images: 图片列表，可以是 bytes（图片数据）或 str（URL）

        Returns:
            如果没有图片，返回纯文本；有图片则返回多模态内容列表
        """
        if not images:
            return text

        content = [{"type": "text", "text": text}]

        for img in images:
            if isinstance(img, bytes):
                # 压缩图片到 200KB 以内
                compressed_img = compress_image(img, max_size_kb=200)
                # 图片数据，转为 base64 data URL
                base64_data = self._encode_image_to_base64(compressed_img)
                image_url = f"data:image/png;base64,{base64_data}"
            else:
                # 已经是 URL
                image_url = img

            content.append({
                "type": "image_url",
                "image_url": {"url": image_url}
            })

        return content

    def _parse_streaming_response(self, response: requests.Response, max_length: int = 100000) -> str:
        """
        解析流式响应（SSE格式）

        处理 OpenAI 兼容的服务器发送事件（SSE）流式响应，累积所有分块内容。

        Args:
            response: requests.Response 对象（stream=True）
            max_length: 最大累计字符数，防止无限流（默认100000字符）

        Returns:
            累积的完整文本内容

        Raises:
            ValueError: 当累积内容超过 max_length 时
        """
        chunks = []
        total_length = 0
        is_complete = False  # 标记是否正常结束（收到 [DONE]）
        buffer = b""  # 字节缓冲区，用于累积不完整的行
        max_buffer_size = max_length * 4  # 缓冲区最大字节数（UTF-8 最多4字节/字符）

        def process_line(line: str) -> bool:
            """
            处理一行 SSE 数据

            Args:
                line: 解码后的文本行

            Returns:
                是否收到 [DONE] 标记（需要结束）
            """
            nonlocal chunks, total_length, is_complete

            # 跳过空行（心跳包）
            if not line:
                return False

            # SSE 格式的数据行以 "data: " 开头
            if line.startswith("data: "):
                data_str = line[6:].strip()  # 移除 "data: " 前缀

                # 检查流结束标记
                if data_str == "[DONE]":
                    logger.debug("[流式响应] 接收到 [DONE] 标记，流正常结束")
                    is_complete = True
                    return True

                try:
                    # 解析 JSON 数据
                    data = json.loads(data_str)

                    # 提取内容（兼容 chat/completions 的 delta.content 和 completions 的 text）
                    if "choices" in data and len(data["choices"]) > 0:
                        choice = data["choices"][0]

                        # 优先使用 delta.content（chat/completions 格式）
                        if "delta" in choice and "content" in choice["delta"]:
                            content = choice["delta"]["content"]
                            if content:
                                chunks.append(content)
                                total_length += len(content)
                        # 回退到 text 字段（completions 格式）
                        elif "text" in choice:
                            text = choice["text"]
                            if text:
                                chunks.append(text)
                                total_length += len(text)
                    elif "choices" in data and len(data["choices"]) == 0:
                        logger.debug("[流式响应] choices 为空，跳过此分块")

                    # 防止无限流：检查累计长度
                    if total_length > max_length:
                        logger.warning(f"[流式响应] 累计长度 {total_length} 超过限制 {max_length}，停止读取")
                        raise ValueError(f"流式响应超过最大长度限制: {max_length}")

                except json.JSONDecodeError as e:
                    logger.warning(f"[流式响应] JSON 解析失败，跳过此分块: {e}, 数据: {data_str[:100]}")
                except KeyError as e:
                    logger.warning(f"[流式响应] 响应格式异常，跳过此分块: {e}, 数据: {data_str[:100]}")

            return False

        try:
            # 使用 iter_content 读取原始字节，避免 iter_lines 的编码问题
            for chunk_bytes in response.iter_content(chunk_size=1024):
                if not chunk_bytes:
                    continue

                # 将新数据添加到缓冲区
                buffer += chunk_bytes

                # 防止缓冲区无限增长
                if len(buffer) > max_buffer_size:
                    logger.warning(f"[流式响应] 缓冲区大小 {len(buffer)} 超过限制 {max_buffer_size}，停止读取")
                    raise ValueError(f"缓冲区超过最大大小限制: {max_buffer_size}")

                # 按换行符分割，处理完整的行（支持 \n 和 \r\n）
                while b'\n' in buffer:
                    line_bytes, buffer = buffer.split(b'\n', 1)

                    # 移除可能的 \r（处理 \r\n 行尾）
                    line_bytes = line_bytes.rstrip(b'\r')

                    # 解码为字符串（UTF-8）
                    try:
                        line = line_bytes.decode('utf-8').strip()
                    except UnicodeDecodeError as e:
                        logger.warning(f"[流式响应] UTF-8 解码失败: {e}, 字节（hex）: {line_bytes[:50].hex()}")
                        continue

                    # 处理这一行
                    if process_line(line):
                        # 收到 [DONE]，结束
                        break

                # 如果收到 [DONE]，跳出外层循环
                if is_complete:
                    break

            # 处理残余的缓冲区（最后一行可能没有换行符）
            if buffer and not is_complete:
                # 移除可能的 \r
                buffer = buffer.rstrip(b'\r')

                try:
                    line = buffer.decode('utf-8').strip()
                    process_line(line)
                except UnicodeDecodeError as e:
                    logger.warning(f"[流式响应] 残余缓冲区 UTF-8 解码失败: {e}, 字节（hex）: {buffer[:50].hex()}")

        except requests.exceptions.Timeout:
            logger.error(f"[流式响应] 读取超时（partial=True），已累积 {len(chunks)} 个分块，总长度: {total_length} 字符")
        except ValueError as e:
            # max_length 或 max_buffer_size 超限
            logger.error(f"[流式响应] 超限错误（partial=True）: {e}，已累积 {len(chunks)} 个分块，总长度: {total_length} 字符")
            raise
        except Exception as e:
            logger.exception(f"[流式响应] 读取异常（partial=True）: {e}，已累积 {len(chunks)} 个分块，总长度: {total_length} 字符")

        # 拼接所有分块
        result = "".join(chunks)

        # 日志记录完成状态
        if is_complete:
            logger.info(f"[流式响应] 正常完成（complete=True），总长度: {len(result)} 字符")
        elif result:
            logger.warning(f"[流式响应] 部分完成（partial=True），总长度: {len(result)} 字符")
        else:
            logger.warning("[流式响应] 没有接收到有效内容（empty response）")

        return result

    @retry_on_429(max_retries=3, base_delay=2)
    def generate_text(
        self,
        prompt: str,
        model: str = "gemini-3-pro-preview",
        temperature: float = 1.0,
        max_output_tokens: int = 65535,
        images: List[Union[bytes, str]] = None,
        system_prompt: str = None,
        stream: bool = False,
        **kwargs
    ) -> str:
        """
        生成文本（支持图片输入和流式传输）

        Args:
            prompt: 提示词
            model: 模型名称
            temperature: 温度
            max_output_tokens: 最大输出 token
            images: 图片列表（可选）
            system_prompt: 系统提示词（可选）
            stream: 是否使用流式传输（默认 False）
                   - False: 非流式，等待完整响应（可能超时）
                   - True: 流式传输，持续接收数据，避免网关超时

        Returns:
            生成的文本

        Notes:
            - 流式模式下，通过持续的数据传输避免中间网关（如 Cloudflare）的 524 超时
            - 流式和非流式模式都返回完整的文本字符串，保持接口一致性
            - 推荐在生成长文本时使用 stream=True
        """
        messages = []

        # 添加系统提示词
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })

        # 构建用户消息内容
        content = self._build_content_with_images(prompt, images)
        messages.append({
            "role": "user",
            "content": content
        })

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_output_tokens,
            "stream": stream  # 根据参数设置是否流式传输
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        # 超时配置：(connect_timeout, read_timeout)
        # - connect_timeout: 连接超时（10秒）
        # - read_timeout: 读取超时（300秒 = 5分钟）
        # 流式模式下，read_timeout 指每次读取分块的超时，而非总超时
        timeout = (10, 300)

        logger.info(f"[文本生成] 开始请求，模型: {model}, 流式: {stream}")

        response = requests.post(
            self.chat_endpoint,
            json=payload,
            headers=headers,
            timeout=timeout,
            stream=stream  # 启用流式响应
        )

        if response.status_code != 200:
            error_msg = f"API 请求失败: {response.status_code} - {response.text}"
            logger.error(f"[文本生成] {error_msg}")
            raise Exception(error_msg)

        # 流式模式：解析 SSE 流
        if stream:
            logger.info("[文本生成] 使用流式模式，开始解析响应流")
            return self._parse_streaming_response(response)

        # 非流式模式：解析完整 JSON 响应
        result = response.json()

        # 提取生成的文本
        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"]
            logger.info(f"[文本生成] 非流式模式完成，长度: {len(content)} 字符")
            return content
        else:
            error_msg = f"API 响应格式异常: {result}"
            logger.error(f"[文本生成] {error_msg}")
            raise Exception(error_msg)


# 全局客户端实例
_client_instance = None


def get_text_chat_client() -> TextChatClient:
    """获取全局 Text Chat 客户端实例"""
    global _client_instance
    if _client_instance is None:
        _client_instance = TextChatClient()
    return _client_instance


# 保留向后兼容的别名
def get_bltcy_chat_client() -> TextChatClient:
    """向后兼容的别名"""
    return get_text_chat_client()
