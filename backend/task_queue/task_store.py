"""任务状态存储模块。

使用 Redis Hash 存储任务状态，支持多种任务类型（outline、image 等）。
提供统一的任务生命周期管理接口：创建、更新、查询、清理。

Key 命名规范:
    - task:{type}:{task_id} - 任务状态 Hash
    - task:{type}:{task_id}:events - 任务事件 Pub/Sub 频道

状态字段说明:
    - status: pending / running / finished / failed
    - progress_current: 当前进度
    - progress_total: 总进度
    - result: JSON 序列化的结果数据
    - error: 错误信息
    - user_id: 用户标识（用于多用户隔离）
    - created_at / updated_at: ISO8601 时间戳
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from backend.task_queue import get_redis_connection

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """任务状态枚举。"""
    PENDING = "pending"      # 已创建，等待执行
    RUNNING = "running"      # 正在执行
    FINISHED = "finished"    # 执行完成
    FAILED = "failed"        # 执行失败


class TaskType(str, Enum):
    """任务类型枚举。"""
    OUTLINE = "outline"      # 大纲生成
    IMAGE = "image"          # 图片生成


class TaskStore:
    """基于 Redis Hash 的通用任务状态存储。

    设计原则:
        - 所有字段在 Redis 中以字符串形式存储
        - 复杂类型（dict/list）自动 JSON 序列化
        - 数值类型自动转换
        - 支持增量更新，只更新传入的字段
    """

    # 任务状态过期时间（秒），默认 24 小时
    DEFAULT_TTL = 24 * 60 * 60

    @staticmethod
    def _make_key(task_type: Union[str, TaskType], task_id: str) -> str:
        """构造任务在 Redis 中的 key。

        Args:
            task_type: 任务类型
            task_id: 任务 ID

        Returns:
            Redis key 字符串
        """
        if isinstance(task_type, TaskType):
            task_type = task_type.value
        return f"task:{task_type}:{task_id}"

    @staticmethod
    def _make_event_channel(task_type: Union[str, TaskType], task_id: str) -> str:
        """构造任务事件 Pub/Sub 频道名。"""
        if isinstance(task_type, TaskType):
            task_type = task_type.value
        return f"task:{task_type}:{task_id}:events"

    @staticmethod
    def _utc_now() -> str:
        """获取当前 UTC 时间的 ISO8601 字符串。"""
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _serialize_value(value: Any) -> str:
        """将值序列化为字符串。

        Args:
            value: 任意类型的值

        Returns:
            字符串形式的值
        """
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    @staticmethod
    def _deserialize_value(raw: bytes, field_name: str) -> Any:
        """将 Redis 返回的字节反序列化。

        Args:
            raw: Redis 返回的字节
            field_name: 字段名（用于特殊处理）

        Returns:
            反序列化后的值
        """
        value_str = raw.decode("utf-8")

        # 数值字段转换
        if field_name in ("progress_current", "progress_total"):
            try:
                return int(value_str)
            except (TypeError, ValueError):
                return 0

        return value_str

    @classmethod
    def create_task(
        cls,
        task_type: Union[str, TaskType],
        task_id: Optional[str] = None,
        user_id: Optional[str] = None,
        progress_total: int = 0,
        extra_fields: Optional[Dict[str, Any]] = None,
        ttl: Optional[int] = None,
    ) -> str:
        """创建新任务并写入初始状态。

        Args:
            task_type: 任务类型（outline/image）
            task_id: 任务 ID，不传则自动生成
            user_id: 用户标识
            progress_total: 总进度
            extra_fields: 额外字段
            ttl: 过期时间（秒），None 则使用默认值

        Returns:
            任务 ID
        """
        if not task_id:
            task_id = uuid.uuid4().hex

        now = cls._utc_now()
        mapping: Dict[str, str] = {
            "status": TaskStatus.PENDING.value,
            "progress_current": "0",
            "progress_total": str(progress_total),
            "result": "",
            "error": "",
            "user_id": user_id or "",
            "created_at": now,
            "updated_at": now,
        }

        # 合并额外字段
        if extra_fields:
            for key, value in extra_fields.items():
                mapping[key] = cls._serialize_value(value)

        redis_conn = get_redis_connection()
        key = cls._make_key(task_type, task_id)
        redis_conn.hset(key, mapping=mapping)

        # 设置过期时间
        effective_ttl = ttl if ttl is not None else cls.DEFAULT_TTL
        if effective_ttl > 0:
            redis_conn.expire(key, effective_ttl)

        logger.info(f"任务已创建: {key}, user_id={user_id}")
        return task_id

    @classmethod
    def update_task_status(
        cls,
        task_type: Union[str, TaskType],
        task_id: str,
        status: Optional[Union[str, TaskStatus]] = None,
        progress_current: Optional[int] = None,
        progress_total: Optional[int] = None,
        result: Optional[Any] = None,
        error: Optional[str] = None,
        extra_fields: Optional[Dict[str, Any]] = None,
    ) -> None:
        """更新任务状态。

        只更新传入的非 None 字段，自动更新 updated_at。

        Args:
            task_type: 任务类型
            task_id: 任务 ID
            status: 新状态
            progress_current: 当前进度
            progress_total: 总进度
            result: 结果数据
            error: 错误信息
            extra_fields: 额外字段
        """
        mapping: Dict[str, str] = {
            "updated_at": cls._utc_now(),
        }

        if status is not None:
            if isinstance(status, TaskStatus):
                status = status.value
            mapping["status"] = status

        if progress_current is not None:
            mapping["progress_current"] = str(progress_current)

        if progress_total is not None:
            mapping["progress_total"] = str(progress_total)

        if result is not None:
            mapping["result"] = cls._serialize_value(result)

        if error is not None:
            mapping["error"] = error

        if extra_fields:
            for key, value in extra_fields.items():
                mapping[key] = cls._serialize_value(value)

        redis_conn = get_redis_connection()
        key = cls._make_key(task_type, task_id)
        redis_conn.hset(key, mapping=mapping)

        logger.debug(f"任务已更新: {key}, fields={list(mapping.keys())}")

    @classmethod
    def set_task_field(
        cls,
        task_type: Union[str, TaskType],
        task_id: str,
        field: str,
        value: Any,
    ) -> None:
        """设置单个任务字段。

        Args:
            task_type: 任务类型
            task_id: 任务 ID
            field: 字段名
            value: 字段值
        """
        redis_conn = get_redis_connection()
        key = cls._make_key(task_type, task_id)
        mapping = {
            field: cls._serialize_value(value),
            "updated_at": cls._utc_now(),
        }
        redis_conn.hset(key, mapping=mapping)

    @classmethod
    def get_task(
        cls,
        task_type: Union[str, TaskType],
        task_id: str,
    ) -> Optional[Dict[str, Any]]:
        """获取任务完整状态。

        Args:
            task_type: 任务类型
            task_id: 任务 ID

        Returns:
            任务状态字典，不存在则返回 None
        """
        redis_conn = get_redis_connection()
        key = cls._make_key(task_type, task_id)
        raw_data = redis_conn.hgetall(key)

        if not raw_data:
            return None

        result: Dict[str, Any] = {"task_id": task_id}
        for key_bytes, value_bytes in raw_data.items():
            field_name = key_bytes.decode("utf-8")
            result[field_name] = cls._deserialize_value(value_bytes, field_name)

        return result

    @classmethod
    def get_task_field(
        cls,
        task_type: Union[str, TaskType],
        task_id: str,
        field: str,
    ) -> Optional[str]:
        """获取任务单个字段值。

        Args:
            task_type: 任务类型
            task_id: 任务 ID
            field: 字段名

        Returns:
            字段值（字符串），不存在则返回 None
        """
        redis_conn = get_redis_connection()
        key = cls._make_key(task_type, task_id)
        raw = redis_conn.hget(key, field)
        if raw is None:
            return None
        return raw.decode("utf-8")

    @classmethod
    def task_exists(
        cls,
        task_type: Union[str, TaskType],
        task_id: str,
    ) -> bool:
        """检查任务是否存在。"""
        redis_conn = get_redis_connection()
        key = cls._make_key(task_type, task_id)
        return redis_conn.exists(key) > 0

    @classmethod
    def delete_task(
        cls,
        task_type: Union[str, TaskType],
        task_id: str,
    ) -> bool:
        """删除任务。

        Returns:
            是否成功删除
        """
        redis_conn = get_redis_connection()
        key = cls._make_key(task_type, task_id)
        deleted = redis_conn.delete(key)
        if deleted:
            logger.info(f"任务已删除: {key}")
        return deleted > 0

    @classmethod
    def publish_event(
        cls,
        task_type: Union[str, TaskType],
        task_id: str,
        event_type: str,
        event_data: Dict[str, Any],
    ) -> None:
        """发布任务事件（用于 SSE 推送）。

        Args:
            task_type: 任务类型
            task_id: 任务 ID
            event_type: 事件类型（progress/complete/error/finish）
            event_data: 事件数据
        """
        redis_conn = get_redis_connection()
        channel = cls._make_event_channel(task_type, task_id)
        message = json.dumps({
            "event": event_type,
            "data": event_data,
        }, ensure_ascii=False)
        redis_conn.publish(channel, message)

    @classmethod
    def subscribe_events(
        cls,
        task_type: Union[str, TaskType],
        task_id: str,
    ):
        """订阅任务事件（返回 PubSub 对象）。

        Returns:
            Redis PubSub 对象
        """
        redis_conn = get_redis_connection()
        pubsub = redis_conn.pubsub()
        channel = cls._make_event_channel(task_type, task_id)
        pubsub.subscribe(channel)
        return pubsub

    @classmethod
    def list_tasks_by_user(
        cls,
        task_type: Union[str, TaskType],
        user_id: str,
        status: Optional[Union[str, TaskStatus]] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """列出用户的任务。

        注意：此方法使用 SCAN 遍历，大量任务时可能较慢。

        Args:
            task_type: 任务类型
            user_id: 用户 ID
            status: 可选的状态过滤
            limit: 最大返回数量

        Returns:
            任务列表
        """
        if isinstance(task_type, TaskType):
            task_type = task_type.value
        if isinstance(status, TaskStatus):
            status = status.value

        redis_conn = get_redis_connection()
        pattern = f"task:{task_type}:*"
        tasks = []

        for key in redis_conn.scan_iter(match=pattern, count=100):
            if len(tasks) >= limit:
                break

            raw_data = redis_conn.hgetall(key)
            if not raw_data:
                continue

            task_user_id = raw_data.get(b"user_id", b"").decode("utf-8")
            if task_user_id != user_id:
                continue

            if status:
                task_status = raw_data.get(b"status", b"").decode("utf-8")
                if task_status != status:
                    continue

            # 从 key 中提取 task_id
            key_str = key.decode("utf-8")
            task_id = key_str.split(":")[-1]

            task_data = {"task_id": task_id}
            for field_bytes, value_bytes in raw_data.items():
                field_name = field_bytes.decode("utf-8")
                task_data[field_name] = cls._deserialize_value(value_bytes, field_name)

            tasks.append(task_data)

        return tasks


__all__ = ["TaskStore", "TaskStatus", "TaskType"]
