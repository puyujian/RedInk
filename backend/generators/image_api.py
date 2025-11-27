"""Image API 图片生成器"""
import time
import random
import base64
import requests
from typing import Dict, Any, Optional, List
from .base import ImageGeneratorBase
from ..utils.image_compressor import compress_image


class SensitiveWordsError(Exception):
    """敏感词检测异常，不可重试。

    当图片生成接口检测到敏感词时抛出此异常，该异常会跳过所有重试机制，
    直接返回错误信息到前端，提示用户重新生成大纲。
    """

    def __init__(self, message: str = "文案中有敏感词，请重新生成大纲！"):
        super().__init__(message)
        self.retryable = False


def retry_on_error(max_retries: int = 3, base_delay: float = 2):
    """错误重试装饰器

    对于大部分异常会进行重试，但对于 SensitiveWordsError 会直接抛出，不进行重试。
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    # 敏感词错误不可重试，直接抛出
                    if isinstance(e, SensitiveWordsError):
                        raise
                    last_error = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                        print(f"[重试] 请求失败，{delay:.1f}秒后重试 (尝试 {attempt + 2}/{max_retries})")
                        time.sleep(delay)
            raise last_error
        return wrapper
    return decorator


class ImageApiGenerator(ImageGeneratorBase):
    """Image API 生成器"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = config.get('base_url', 'https://api.example.com')
        self.model = config.get('model', 'default-model')
        self.default_aspect_ratio = config.get('default_aspect_ratio', '3:4')
        self.image_size = config.get('image_size', '4K')

    def validate_config(self) -> bool:
        """验证配置是否有效"""
        if not self.api_key:
            raise ValueError("API key 未配置")
        return True

    def get_supported_sizes(self) -> List[str]:
        """获取支持的图片尺寸"""
        return ["1K", "2K", "4K"]

    def get_supported_aspect_ratios(self) -> List[str]:
        """获取支持的宽高比"""
        return ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]

    def _check_sensitive_words_error(self, response: requests.Response) -> None:
        """检测响应中是否包含敏感词错误。

        检测策略：
        1. 解析响应 JSON 中的 error.type / error.code 字段
        2. 检查 error.message 是否包含关键字
        3. 兜底：检查整个响应文本是否包含关键字

        注意：所有比较均使用小写以避免大小写不一致问题。

        Args:
            response: HTTP 响应对象

        Raises:
            SensitiveWordsError: 当检测到敏感词错误时抛出
        """
        sensitive_keyword = "sensitive_words_detected"

        try:
            body = response.json()
        except ValueError:
            # JSON 解析失败，检查原始文本（大小写不敏感）
            if sensitive_keyword in response.text.lower():
                raise SensitiveWordsError()
            return

        # 检查 error 字段
        error_info = body.get("error") if isinstance(body, dict) else None
        if isinstance(error_info, dict):
            error_type = error_info.get("type") or error_info.get("code") or ""
            if str(error_type).lower() == sensitive_keyword:
                raise SensitiveWordsError()

            error_message = error_info.get("message", "")
            if sensitive_keyword in str(error_message).lower():
                raise SensitiveWordsError()

        # 兜底：检查整个响应体（大小写不敏感）
        if sensitive_keyword in str(body).lower():
            raise SensitiveWordsError()

    @retry_on_error(max_retries=3, base_delay=2)
    def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = None,
        temperature: float = 1.0,
        model: str = None,
        reference_image: Optional[bytes] = None,
        reference_images: Optional[List[bytes]] = None,
        **kwargs
    ) -> bytes:
        """
        生成图片（使用 /v1/images/generations）

        Args:
            prompt: 图片描述
            aspect_ratio: 宽高比
            temperature: 创意度（未使用，保留接口兼容）
            model: 模型名称
            reference_image: 单张参考图片数据（向后兼容）
            reference_images: 多张参考图片数据列表

        Returns:
            生成的图片二进制数据
        """
        self.validate_config()

        if aspect_ratio is None:
            aspect_ratio = self.default_aspect_ratio

        if model is None:
            model = self.model

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # 构建请求体（使用 /v1/images/generations 格式）
        payload = {
            "model": model,
            "prompt": prompt,
            "response_format": "b64_json",  # 关键！获取 base64 数据而不是 URL
            "aspect_ratio": aspect_ratio,
            "image_size": self.image_size  # 4K 参数（nano-banana-2 专属）
        }

        # 收集所有参考图片
        all_reference_images = []

        # 优先使用 reference_images 列表
        if reference_images and len(reference_images) > 0:
            all_reference_images.extend(reference_images)

        # 向后兼容：如果有单张 reference_image，添加到列表
        if reference_image and reference_image not in all_reference_images:
            all_reference_images.append(reference_image)

        # 如果有参考图片，添加到 image 数组（Data URI 格式）
        if all_reference_images:
            image_uris = []
            for img_data in all_reference_images:
                # 压缩图片到 200KB 以内
                compressed_img = compress_image(img_data, max_size_kb=200)
                base64_image = base64.b64encode(compressed_img).decode('utf-8')
                data_uri = f"data:image/png;base64,{base64_image}"
                image_uris.append(data_uri)

            payload["image"] = image_uris  # images/generations 端点使用 image 数组

            # 增强提示词以利用参考图
            ref_count = len(all_reference_images)
            enhanced_prompt = f"""参考提供的 {ref_count} 张图片的风格（色彩、光影、构图、氛围），生成一张新图片。

新图片内容：{prompt}

要求：
1. 保持相似的色调和氛围
2. 使用相似的光影处理
3. 保持一致的画面质感
4. 如果参考图中有人物或产品，可以适当融入"""
            payload["prompt"] = enhanced_prompt

        # 发送请求
        response = requests.post(
            f"{self.base_url}/v1/images/generations",
            headers=headers,
            json=payload,
            timeout=300
        )

        # 检测敏感词错误（优先处理，不可重试）
        self._check_sensitive_words_error(response)

        if response.status_code != 200:
            raise Exception(f"API 错误 {response.status_code}: {response.text[:500]}")

        result = response.json()

        # 提取 b64_json 数据
        if "data" in result and len(result["data"]) > 0:
            item = result["data"][0]

            if "b64_json" in item:
                b64_data_uri = item["b64_json"]

                # 去掉 Data URI 前缀（data:image/png;base64,）
                if b64_data_uri.startswith('data:'):
                    b64_string = b64_data_uri.split(',', 1)[1]
                else:
                    b64_string = b64_data_uri

                # 解码 base64
                image_data = base64.b64decode(b64_string)
                return image_data

        raise Exception(f"未找到 b64_json 数据。响应: {str(result)[:500]}")
