import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    DEBUG = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    HOST = os.getenv('FLASK_HOST', '0.0.0.0')
    PORT = int(os.getenv('FLASK_PORT', 5000))
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', 'http://localhost:5173,http://localhost:3000').split(',')
    GOOGLE_CLOUD_API_KEY = os.getenv('GOOGLE_CLOUD_API_KEY')
    OUTPUT_DIR = os.getenv('OUTPUT_DIR', 'output')

    # 数据库配置（默认使用 SQLite，支持 MySQL）
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///redink.db')

    # Redis 连接配置
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

    # RQ 任务队列配置
    OUTLINE_QUEUE_NAME = os.getenv('OUTLINE_QUEUE_NAME', 'outline_queue')
    IMAGE_QUEUE_NAME = os.getenv('IMAGE_QUEUE_NAME', 'image_queue')

    # 任务超时配置（秒）
    OUTLINE_TASK_TIMEOUT = int(os.getenv('OUTLINE_TASK_TIMEOUT', 300))  # 大纲生成超时 5 分钟
    IMAGE_TASK_TIMEOUT = int(os.getenv('IMAGE_TASK_TIMEOUT', 1800))  # 图片生成超时 30 分钟

    # JWT 认证配置
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'CHANGE_ME_IN_PRODUCTION_PLEASE')
    JWT_ACCESS_EXPIRES = int(os.getenv('JWT_ACCESS_EXPIRES', 900))  # access token 有效期 15 分钟
    JWT_REFRESH_EXPIRES = int(os.getenv('JWT_REFRESH_EXPIRES', 604800))  # refresh token 有效期 7 天

    # CORS 允许的请求头
    CORS_ALLOW_HEADERS = os.getenv(
        'CORS_ALLOW_HEADERS',
        'Content-Type,Authorization,X-User-Id'
    ).split(',')

    _image_providers_config = None

    @classmethod
    def load_image_providers_config(cls):
        if cls._image_providers_config is not None:
            return cls._image_providers_config

        config_path = Path(__file__).parent.parent / 'image_providers.yaml'

        if not config_path.exists():
            cls._image_providers_config = {
                'active_provider': 'google_genai',
                'providers': {
                    'google_genai': {
                        'type': 'google_genai',
                        'api_key_env': 'GOOGLE_CLOUD_API_KEY',
                        'model': 'gemini-3-pro-image-preview',
                        'default_aspect_ratio': '3:4'
                    }
                }
            }
            return cls._image_providers_config

        with open(config_path, 'r', encoding='utf-8') as f:
            cls._image_providers_config = yaml.safe_load(f)

        return cls._image_providers_config

    @classmethod
    def get_active_image_provider(cls):
        config = cls.load_image_providers_config()
        # 允许通过环境变量覆盖
        return os.getenv('IMAGE_PROVIDER', config.get('active_provider', 'google_genai'))

    @classmethod
    def get_image_provider_config(cls, provider_name: str = None):
        config = cls.load_image_providers_config()

        if provider_name is None:
            provider_name = cls.get_active_image_provider()

        if provider_name not in config.get('providers', {}):
            raise ValueError(f"未找到服务商配置: {provider_name}")

        provider_config = config['providers'][provider_name].copy()

        api_key_env = provider_config.get('api_key_env')
        if api_key_env:
            provider_config['api_key'] = os.getenv(api_key_env)

        return provider_config
