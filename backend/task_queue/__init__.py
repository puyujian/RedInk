"""队列与 Redis 连接封装模块。

该模块提供统一的 Redis 连接和 RQ 队列实例，采用懒加载模式避免在模块导入时建立连接。
支持连接池复用，确保多进程/多线程环境下的安全性。
"""

from __future__ import annotations

import logging
from typing import Optional

from redis import Redis
from rq import Queue

from backend.config import Config

logger = logging.getLogger(__name__)

# 模块级别的连接缓存（进程内复用）
_redis_connection: Optional[Redis] = None
_outline_queue: Optional[Queue] = None
_image_queue: Optional[Queue] = None


def get_redis_connection() -> Redis:
    """获取全局 Redis 连接实例。

    采用懒加载模式，首次调用时建立连接，后续复用同一实例。
    线程安全：Redis 客户端内部使用连接池，支持多线程并发访问。

    Returns:
        Redis: Redis 客户端实例

    Raises:
        redis.ConnectionError: 无法连接到 Redis 服务器时抛出
    """
    global _redis_connection
    if _redis_connection is None:
        redis_url = Config.REDIS_URL
        logger.info(f"正在建立 Redis 连接: {redis_url.split('@')[-1]}")  # 隐藏密码
        _redis_connection = Redis.from_url(
            redis_url,
            decode_responses=False,  # 保持二进制模式以兼容 RQ
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        # 测试连接
        _redis_connection.ping()
        logger.info("Redis 连接成功")
    return _redis_connection


def get_outline_queue() -> Queue:
    """获取大纲生成任务队列。

    Returns:
        Queue: RQ 队列实例，用于处理大纲生成任务
    """
    global _outline_queue
    if _outline_queue is None:
        _outline_queue = Queue(
            name=Config.OUTLINE_QUEUE_NAME,
            connection=get_redis_connection(),
            default_timeout=Config.OUTLINE_TASK_TIMEOUT,
        )
        logger.info(f"大纲队列已初始化: {Config.OUTLINE_QUEUE_NAME}")
    return _outline_queue


def get_image_queue() -> Queue:
    """获取图片生成任务队列。

    Returns:
        Queue: RQ 队列实例，用于处理图片生成任务
    """
    global _image_queue
    if _image_queue is None:
        _image_queue = Queue(
            name=Config.IMAGE_QUEUE_NAME,
            connection=get_redis_connection(),
            default_timeout=Config.IMAGE_TASK_TIMEOUT,
        )
        logger.info(f"图片队列已初始化: {Config.IMAGE_QUEUE_NAME}")
    return _image_queue


def reset_connections() -> None:
    """重置所有连接（主要用于测试或错误恢复）。

    调用后，下次获取连接/队列时会重新建立。
    """
    global _redis_connection, _outline_queue, _image_queue
    if _redis_connection is not None:
        try:
            _redis_connection.close()
        except Exception:
            pass
    _redis_connection = None
    _outline_queue = None
    _image_queue = None
    logger.info("Redis 连接已重置")


__all__ = [
    "get_redis_connection",
    "get_outline_queue",
    "get_image_queue",
    "reset_connections",
]
