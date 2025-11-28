import os
import yaml
import logging
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Config:
    DEBUG = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    HOST = os.getenv('FLASK_HOST', '0.0.0.0')
    PORT = int(os.getenv('FLASK_PORT', 5000))
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', 'http://localhost:5173,http://localhost:3000').split(',')
    GOOGLE_CLOUD_API_KEY = os.getenv('GOOGLE_CLOUD_API_KEY')
    OUTPUT_DIR = os.getenv('OUTPUT_DIR', 'output')

    # Flask 请求体大小限制（50MB，用于支持大图片上传）
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB

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

    # Worker 并发配置
    WORKER_CONCURRENCY = int(os.getenv('WORKER_CONCURRENCY', 8))  # 并发 Worker 进程数

    # JWT 认证配置
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'CHANGE_ME_IN_PRODUCTION_PLEASE')
    JWT_ACCESS_EXPIRES = int(os.getenv('JWT_ACCESS_EXPIRES', 900))  # access token 有效期 15 分钟
    JWT_REFRESH_EXPIRES = int(os.getenv('JWT_REFRESH_EXPIRES', 604800))  # refresh token 有效期 7 天

    # CORS 允许的请求头
    CORS_ALLOW_HEADERS = os.getenv(
        'CORS_ALLOW_HEADERS',
        'Content-Type,Authorization,X-User-Id'
    ).split(',')

    # ============================================================================
    # 初始管理员自动创建配置
    # ============================================================================
    # 是否在系统启动时自动创建初始管理员（生产环境推荐开启）
    ADMIN_BOOTSTRAP_ON_START = os.getenv('ADMIN_BOOTSTRAP_ON_START', 'true').lower() == 'true'

    # 初始管理员凭证（仅在无管理员且开启自动创建时使用）
    INITIAL_ADMIN_USERNAME = os.getenv('INITIAL_ADMIN_USERNAME', 'admin')
    INITIAL_ADMIN_PASSWORD = os.getenv('INITIAL_ADMIN_PASSWORD')  # 必须通过环境变量设置
    INITIAL_ADMIN_EMAIL = os.getenv('INITIAL_ADMIN_EMAIL', 'admin@example.com')

    _image_providers_config = None

    @classmethod
    def load_image_providers_config(cls):
        if cls._image_providers_config is not None:
            return cls._image_providers_config

        config_path = Path(__file__).parent.parent / 'image_providers.yaml'

        if not config_path.exists():
            cls._image_providers_config = {
                'active_provider': 'google_genai',
                'role_mapping': {
                    'user': 'google_genai',
                    'pro': 'google_genai',
                    'admin': 'google_genai',
                },
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
    def get_image_provider_by_role(
        cls,
        role: Optional[str],
        default_provider: Optional[str] = None,
    ) -> str:
        """根据用户角色选择图片服务商，带安全回退机制。

        Args:
            role: 用户角色（user/pro/admin），会自动规范化为小写
            default_provider: 默认服务商（当角色映射失败时使用）

        Returns:
            服务商名称

        Raises:
            ValueError: 当没有找到任何可用的服务商配置时
        """
        config = cls.load_image_providers_config()
        providers = config.get('providers', {}) or {}

        def _is_valid_provider(name: Optional[str]) -> bool:
            """检查服务商是否存在且可用"""
            return bool(name) and name in providers

        # 规范化角色名称（小写、去空格）
        normalized_role = (role or '').strip().lower()

        # 尝试从角色映射中获取服务商
        role_mapping = config.get('role_mapping') or {}
        mapped_provider = role_mapping.get(normalized_role)

        if _is_valid_provider(mapped_provider):
            logger.info(
                f"[Config] 根据角色选择服务商: role={normalized_role}, "
                f"provider={mapped_provider}"
            )
            return mapped_provider

        # 如果映射的服务商不存在，记录警告
        if mapped_provider and not _is_valid_provider(mapped_provider):
            logger.warning(
                f"[Config] 角色映射的服务商不存在: role={normalized_role}, "
                f"provider={mapped_provider}, 将使用回退策略"
            )

        # 回退策略1: 使用环境变量指定的服务商
        env_provider = os.getenv('IMAGE_PROVIDER')
        if _is_valid_provider(env_provider):
            logger.info(
                f"[Config] 使用环境变量指定的服务商: {env_provider} "
                f"(注意：环境变量会覆盖角色映射)"
            )
            return env_provider

        # 回退策略2: 使用调用方指定的默认服务商
        if _is_valid_provider(default_provider):
            logger.info(f"[Config] 使用调用方指定的默认服务商: {default_provider}")
            return default_provider

        # 回退策略3: 使用配置文件中的 active_provider
        active_provider = config.get('active_provider')
        if _is_valid_provider(active_provider):
            logger.info(f"[Config] 使用配置文件的 active_provider: {active_provider}")
            return active_provider

        # 回退策略4: 使用第一个可用的服务商
        if providers:
            fallback = next(iter(providers.keys()))
            logger.warning(
                f"[Config] 未找到匹配的服务商，使用第一个可用服务商: {fallback}"
            )
            return fallback

        # 所有策略都失败，抛出异常
        raise ValueError("未找到任何可用的图片服务商配置")

    @classmethod
    def get_image_provider_config(cls, provider_name: str = None, role: Optional[str] = None):
        """获取图片服务商配置。

        Args:
            provider_name: 服务商名称（优先级最高）
            role: 用户角色（当 provider_name 为 None 时使用）

        Returns:
            服务商配置字典
        """
        config = cls.load_image_providers_config()

        # 优先级1: 使用明确指定的 provider_name
        if provider_name is None:
            # 优先级2: 使用环境变量
            env_provider = os.getenv('IMAGE_PROVIDER')
            provider_name = env_provider if env_provider else None

        # 优先级3: 根据角色选择服务商
        if provider_name is None:
            provider_name = cls.get_image_provider_by_role(
                role,
                default_provider=cls.get_active_image_provider(),
            )

        if provider_name not in config.get('providers', {}):
            raise ValueError(f"未找到服务商配置: {provider_name}")

        provider_config = config['providers'][provider_name].copy()

        api_key_env = provider_config.get('api_key_env')
        if api_key_env:
            provider_config['api_key'] = os.getenv(api_key_env)

        return provider_config
