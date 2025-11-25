"""大纲生成异步任务。

该模块定义了大纲生成的 RQ 任务函数，由 worker 进程执行。
任务通过 TaskStore 管理状态，支持进度追踪和错误处理。
"""

from __future__ import annotations

import base64
import json
import logging
import traceback
from typing import List, Optional

from backend.task_queue.task_store import TaskStore, TaskStatus, TaskType
from backend.services.outline import get_outline_service

logger = logging.getLogger(__name__)


def _decode_images_from_base64(images_base64: Optional[List[str]]) -> Optional[List[bytes]]:
    """将 base64 编码的图片列表解码为字节数据。

    支持两种格式:
        - 纯 base64 字符串
        - data URL 格式 (data:image/xxx;base64,...)

    Args:
        images_base64: base64 编码的图片字符串列表

    Returns:
        解码后的字节数据列表，空列表返回 None
    """
    if not images_base64:
        return None

    decoded_images: List[bytes] = []
    for idx, img_b64 in enumerate(images_base64):
        if not img_b64:
            continue

        try:
            # 处理 data URL 格式
            if "," in img_b64:
                img_b64 = img_b64.split(",", 1)[1]

            decoded_images.append(base64.b64decode(img_b64))
        except Exception as e:
            logger.warning(f"图片 {idx} 解码失败: {e}")
            continue

    return decoded_images if decoded_images else None


def generate_outline_task(
    task_id: str,
    topic: str,
    images_base64: Optional[List[str]] = None,
) -> None:
    """RQ 异步任务：生成大纲。

    该任务由 RQ worker 执行，不应直接调用。
    任务状态通过 TaskStore 管理，支持前端轮询查询。

    Args:
        task_id: 任务 ID，需提前在 TaskStore 中创建
        topic: 用户输入的主题
        images_base64: 可选的参考图片（base64 编码）

    Side Effects:
        - 更新 TaskStore 中的任务状态
        - 成功时将结果写入 result 字段
        - 失败时将错误信息写入 error 字段
    """
    task_type = TaskType.OUTLINE

    logger.info(f"[大纲任务] 开始执行: task_id={task_id}, topic={topic[:50]}...")

    # 参数校验
    if not topic or not topic.strip():
        logger.error(f"[大纲任务] 参数错误: topic 为空")
        TaskStore.update_task_status(
            task_type=task_type,
            task_id=task_id,
            status=TaskStatus.FAILED,
            error="主题不能为空",
        )
        return

    # 标记任务开始执行
    TaskStore.update_task_status(
        task_type=task_type,
        task_id=task_id,
        status=TaskStatus.RUNNING,
        progress_current=0,
        progress_total=1,
    )

    try:
        # 解码参考图片
        images_bytes = _decode_images_from_base64(images_base64)
        image_count = len(images_bytes) if images_bytes else 0
        logger.info(f"[大纲任务] 参考图片数量: {image_count}")

        # 调用大纲生成服务
        outline_service = get_outline_service()
        result = outline_service.generate_outline(
            topic=topic.strip(),
            images=images_bytes,
        )

        # 处理结果
        if result.get("success"):
            logger.info(f"[大纲任务] 生成成功: task_id={task_id}")
            TaskStore.update_task_status(
                task_type=task_type,
                task_id=task_id,
                status=TaskStatus.FINISHED,
                progress_current=1,
                result=result,  # TaskStore 会自动 JSON 序列化
            )
        else:
            error_msg = result.get("error") or "大纲生成失败，请重试"
            logger.warning(f"[大纲任务] 生成失败: task_id={task_id}, error={error_msg}")
            TaskStore.update_task_status(
                task_type=task_type,
                task_id=task_id,
                status=TaskStatus.FAILED,
                error=error_msg,
            )

    except Exception as e:
        # 捕获所有未处理异常
        error_msg = f"大纲生成异常: {str(e)}"
        logger.error(
            f"[大纲任务] 执行异常: task_id={task_id}\n"
            f"{traceback.format_exc()}"
        )
        TaskStore.update_task_status(
            task_type=task_type,
            task_id=task_id,
            status=TaskStatus.FAILED,
            error=error_msg,
        )


__all__ = ["generate_outline_task"]
