"""图片生成异步任务。

该模块定义了图片生成的 RQ 任务函数，负责执行两阶段生成策略：
    1. 先生成封面（单线程，作为后续的参考图）
    2. 再并发生成其他页面（ThreadPoolExecutor）

任务状态通过 TaskStore 管理，进度事件通过 Redis Pub/Sub 发布，
由 API 层的 SSE 接口转发给前端。

历史记录同步：每张图片生成成功后自动同步到数据库，
确保用户中途退出时已生成的图片不会丢失。
"""

from __future__ import annotations

import base64
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.task_queue.task_store import TaskStore, TaskStatus, TaskType
from backend.services.image import ImageService, ImageTaskStateStore, get_scoped_image_service
from backend.services.history import get_history_service
from backend.utils.image_compressor import compress_image
from backend.db import db_session
from backend.models import ImageFile, HistoryRecord

logger = logging.getLogger(__name__)


def _build_images_payload(task_id: str) -> Dict[str, Any]:
    """从任务状态构建 images_json 数据结构。

    Args:
        task_id: 任务 ID

    Returns:
        符合 HistoryRecord.images_json 格式的字典
    """
    state = ImageTaskStateStore.load_state(task_id)
    if not state:
        return {"task_id": task_id, "generated": []}

    generated_map = state.get("generated") or {}
    candidates_map = state.get("candidates") or {}

    # 按索引排序，构建有序列表
    sorted_keys = sorted(generated_map.keys(), key=lambda k: int(k) if k.isdigit() else 0)
    generated_list = [generated_map[k] for k in sorted_keys if generated_map.get(k)]

    payload: Dict[str, Any] = {
        "task_id": task_id,
        "generated": generated_list,
    }

    # 如果有候选图片，也一并保存
    if candidates_map:
        payload["candidates_map"] = {str(k): v for k, v in candidates_map.items() if v}

    return payload


def _sync_history_record(
    task_id: str,
    record_id: str,
    user_id: Optional[int],
    status: Optional[str] = None,
    sync_images: bool = True,
) -> None:
    """同步图片生成状态到历史记录。

    该函数在图片生成过程中被调用，实时将已生成的图片同步到数据库，
    确保用户中途退出时数据不会丢失。

    Args:
        task_id: 任务 ID
        record_id: 历史记录 UUID
        user_id: 用户 ID（整数）
        status: 可选的状态更新（generating/completed/partial）
        sync_images: 是否同步图片数据
    """
    if not record_id or not user_id:
        return

    try:
        images_payload = _build_images_payload(task_id) if sync_images else None
        history_service = get_history_service()
        history_service.update_record(
            user_id=user_id,
            record_id=record_id,
            images=images_payload,
            status=status,
        )
        logger.debug(
            f"[图片任务] 历史记录已同步: task_id={task_id}, "
            f"record_id={record_id}, status={status}"
        )
    except Exception as e:
        # 同步失败不影响主流程，仅记录警告
        logger.warning(
            f"[图片任务] 历史记录同步失败: task_id={task_id}, "
            f"record_id={record_id}, error={e}"
        )


def _decode_base64_images(images_base64: Optional[List[str]]) -> List[bytes]:
    """将 base64 / data URL 格式图片列表解码为 bytes 列表。

    Args:
        images_base64: base64 编码的图片字符串列表

    Returns:
        解码后的字节数据列表
    """
    if not images_base64:
        return []

    result: List[bytes] = []
    for idx, img_b64 in enumerate(images_base64):
        if not img_b64:
            continue
        try:
            # 处理 data URL 格式
            if "," in img_b64:
                img_b64 = img_b64.split(",", 1)[1]
            result.append(base64.b64decode(img_b64))
        except Exception as e:
            logger.warning(f"[图片任务] 用户图片解码失败 index={idx}: {e}")
    return result


def _create_image_file(
    task_id: str,
    user_id: Optional[int],
    record_uuid: str,
    filename: str,
    file_path: Path,
) -> None:
    """创建图片文件记录，便于后台管理统计。

    Args:
        task_id: 任务 ID
        user_id: 用户 ID
        record_uuid: 历史记录 UUID
        filename: 图片文件名
        file_path: 图片文件路径
    """
    if not user_id or not filename:
        return

    file_size = None
    try:
        file_size = file_path.stat().st_size
    except Exception as e:
        logger.warning(f"[图片任务] 读取文件大小失败: path={file_path}, error={e}")

    try:
        with db_session() as db:
            # 根据 record_uuid 查询对应的数据库记录 ID
            record = (
                db.query(HistoryRecord)
                .filter(HistoryRecord.record_uuid == record_uuid)
                .first()
                if record_uuid
                else None
            )
            image_file = ImageFile(
                user_id=user_id,
                record_id=record.id if record else None,
                task_id=task_id,
                filename=filename,
                file_size=file_size,
            )
            db.add(image_file)
    except Exception as e:
        logger.warning(
            f"[图片任务] 创建 ImageFile 记录失败: task_id={task_id}, filename={filename}, error={e}"
        )


def _publish_event(task_id: str, event_type: str, data: Dict[str, Any]) -> None:
    """发布任务事件到 Redis Pub/Sub。

    Args:
        task_id: 任务 ID
        event_type: 事件类型（progress/complete/error/finish）
        data: 事件数据
    """
    TaskStore.publish_event(
        task_type=TaskType.IMAGE,
        task_id=task_id,
        event_type=event_type,
        event_data=data,
    )


def generate_images_task(task_id: str) -> None:
    """RQ 异步任务：生成图片（两阶段策略）。

    该任务由 RQ worker 执行，不应直接调用。

    执行流程：
        1. 从 ImageTaskStateStore 加载任务参数
        2. 生成封面图（单线程）
        3. 并发生成其他页面（ThreadPoolExecutor）
        4. 通过 Redis Pub/Sub 发送进度事件
        5. 更新 TaskStore 任务状态

    Args:
        task_id: 任务 ID，需提前通过以下方式初始化：
            - TaskStore.create_task() 创建任务元信息
            - ImageTaskStateStore.init_task() 初始化详细状态

    Note:
        前端通过 GET /api/generate/stream/<task_id> 订阅 SSE 事件
    """
    task_type = TaskType.IMAGE

    logger.info(f"[图片任务] 开始执行: task_id={task_id}")

    # 加载任务状态
    state = ImageTaskStateStore.load_state(task_id)
    if not state:
        logger.error(f"[图片任务] 任务状态不存在: task_id={task_id}")
        TaskStore.update_task_status(
            task_type=task_type,
            task_id=task_id,
            status=TaskStatus.FAILED,
            error="图片任务状态不存在，请重试",
        )
        return

    # 提取任务参数
    pages: List[Dict[str, Any]] = state.get("pages") or []
    full_outline: str = state.get("full_outline") or ""
    user_topic: str = state.get("user_topic") or ""
    user_images_base64: List[str] = state.get("user_images") or []
    record_id: str = state.get("record_id") or ""
    provider_name: Optional[str] = state.get("provider_name") or None
    user_role: Optional[str] = (state.get("user_role") or "").strip().lower() or None

    # 获取用户 ID（用于同步历史记录）
    task_meta = TaskStore.get_task(task_type, task_id)
    user_id: Optional[int] = None
    if task_meta:
        try:
            user_id = int(task_meta.get("user_id", 0)) or None
        except (TypeError, ValueError):
            pass

    total = len(pages)
    if total <= 0:
        logger.warning(f"[图片任务] pages 为空: task_id={task_id}")
        TaskStore.update_task_status(
            task_type=task_type,
            task_id=task_id,
            status=TaskStatus.FAILED,
            error="pages 参数不能为空",
        )
        return

    # 标记任务开始执行
    TaskStore.update_task_status(
        task_type=task_type,
        task_id=task_id,
        status=TaskStatus.RUNNING,
        progress_current=0,
        progress_total=total,
    )

    # 同步历史记录状态为"生成中"
    _sync_history_record(task_id, record_id, user_id, status="generating", sync_images=False)

    # 解码用户参考图片，并压缩以减少内存占用
    user_images_bytes = _decode_base64_images(user_images_base64)
    if user_images_bytes:
        user_images_bytes = [compress_image(img, max_size_kb=200) for img in user_images_bytes]
        logger.info(f"[图片任务] 用户参考图片数量: {len(user_images_bytes)}")

    # 创建图片生成服务实例（根据用户角色选择服务商）
    image_service = get_scoped_image_service(provider_name=provider_name, user_role=user_role)
    logger.info(
        f"[图片任务] 服务实例已创建: task_id={task_id}, "
        f"user_role={user_role}, provider={image_service.provider_name}"
    )

    generated_images: List[str] = []
    failed_pages: List[Dict[str, Any]] = []
    cover_image_data: Optional[bytes] = None

    try:
        # ==================== 第一阶段：生成封面 ====================
        cover_page: Optional[Dict[str, Any]] = None
        other_pages: List[Dict[str, Any]] = []

        for page in pages:
            if page.get("type") == "cover" and cover_page is None:
                cover_page = page
            else:
                other_pages.append(page)

        # 如果没有封面类型，使用第一页作为封面
        if cover_page is None and pages:
            cover_page = pages[0]
            other_pages = pages[1:]

        if cover_page:
            cover_index = cover_page.get("index", 0)
            logger.info(f"[图片任务] 开始生成封面: task_id={task_id}, index={cover_index}")

            # 发送封面生成进度事件
            _publish_event(task_id, "progress", {
                "index": cover_index,
                "status": "generating",
                "message": "正在生成封面...",
                "current": 1,
                "total": total,
                "phase": "cover",
            })

            # 调用底层单图生成函数
            index, success, filename, error, candidates, retryable = image_service._generate_single_image(
                cover_page,
                task_id,
                reference_image=None,
                full_outline=full_outline,
                user_images=user_images_bytes or None,
                user_topic=user_topic,
            )

            if success and filename:
                generated_images.append(filename)
                ImageTaskStateStore.add_generated(task_id, index, filename, candidates)

                # 读取封面图并压缩，用于后续作为参考图
                cover_path = image_service.get_image_path(filename)
                try:
                    with open(cover_path, "rb") as f:
                        cover_image_data = f.read()
                    cover_image_data = compress_image(cover_image_data, max_size_kb=200)
                    ImageTaskStateStore.set_cover_image(task_id, cover_image_data)
                except Exception as e:
                    logger.warning(f"[图片任务] 读取封面图失败: task_id={task_id}, error={e}")

                # 创建图片文件记录
                _create_image_file(task_id, user_id, record_id, filename, Path(cover_path))

                # 构建候选图片 URL 列表
                candidate_files = candidates or [filename]
                candidate_urls = [f"/api/images/{f}" for f in candidate_files]

                _publish_event(task_id, "complete", {
                    "index": index,
                    "status": "done",
                    "image_url": f"/api/images/{filename}",
                    "candidates": candidate_urls,
                    "phase": "cover",
                })

                # 更新任务进度
                TaskStore.update_task_status(
                    task_type=task_type,
                    task_id=task_id,
                    progress_current=len(generated_images),
                )

                # 实时同步到历史记录
                _sync_history_record(task_id, record_id, user_id)

                logger.info(f"[图片任务] 封面生成成功: task_id={task_id}, filename={filename}")
            else:
                failed_pages.append(cover_page)
                ImageTaskStateStore.add_failed(task_id, cover_index, error or "封面生成失败", retryable)

                _publish_event(task_id, "error", {
                    "index": cover_index,
                    "status": "error",
                    "message": error or "封面生成失败",
                    "retryable": retryable,
                    "phase": "cover",
                })

                logger.warning(f"[图片任务] 封面生成失败: task_id={task_id}, error={error}")

        # ==================== 第二阶段：并发生成其他页面 ====================
        if other_pages:
            logger.info(f"[图片任务] 开始并发生成内容页: task_id={task_id}, count={len(other_pages)}")

            _publish_event(task_id, "progress", {
                "status": "batch_start",
                "message": f"开始并发生成 {len(other_pages)} 页内容...",
                "current": len(generated_images),
                "total": total,
                "phase": "content",
            })

            with ThreadPoolExecutor(max_workers=image_service.MAX_CONCURRENT) as executor:
                future_to_page = {
                    executor.submit(
                        image_service._generate_single_image,
                        page,
                        task_id,
                        cover_image_data,  # 使用封面作为参考
                        0,  # retry_count
                        full_outline,
                        user_images_bytes or None,
                        user_topic,
                    ): page
                    for page in other_pages
                }

                # 发送每个页面的"开始生成"进度事件
                for page in other_pages:
                    _publish_event(task_id, "progress", {
                        "index": page.get("index"),
                        "status": "generating",
                        "current": len(generated_images) + 1,
                        "total": total,
                        "phase": "content",
                    })

                # 收集执行结果
                for future in as_completed(future_to_page):
                    page = future_to_page[future]
                    page_index = page.get("index")

                    try:
                        index, success, filename, error, candidates, retryable = future.result()

                        if success and filename:
                            generated_images.append(filename)
                            ImageTaskStateStore.add_generated(task_id, index, filename, candidates)

                            # 创建图片文件记录
                            image_path = image_service.get_image_path(filename)
                            _create_image_file(task_id, user_id, record_id, filename, Path(image_path))

                            candidate_files = candidates or [filename]
                            candidate_urls = [f"/api/images/{f}" for f in candidate_files]

                            _publish_event(task_id, "complete", {
                                "index": index,
                                "status": "done",
                                "image_url": f"/api/images/{filename}",
                                "candidates": candidate_urls,
                                "phase": "content",
                            })

                            TaskStore.update_task_status(
                                task_type=task_type,
                                task_id=task_id,
                                progress_current=len(generated_images),
                            )

                            # 实时同步到历史记录
                            _sync_history_record(task_id, record_id, user_id)
                        else:
                            failed_pages.append(page)
                            ImageTaskStateStore.add_failed(task_id, page_index, error or "图片生成失败", retryable)

                            _publish_event(task_id, "error", {
                                "index": page_index,
                                "status": "error",
                                "message": error or "图片生成失败",
                                "retryable": retryable,
                                "phase": "content",
                            })

                    except Exception as e:
                        failed_pages.append(page)
                        ImageTaskStateStore.add_failed(task_id, page_index, str(e), retryable=True)

                        _publish_event(task_id, "error", {
                            "index": page_index,
                            "status": "error",
                            "message": str(e),
                            "retryable": True,
                            "phase": "content",
                        })

        # ==================== 任务完成 ====================
        success_flag = len(failed_pages) == 0
        finish_payload = {
            "success": success_flag,
            "task_id": task_id,
            "images": generated_images,
            "total": total,
            "completed": len(generated_images),
            "failed": len(failed_pages),
            "failed_indices": [p.get("index") for p in failed_pages if p.get("index") is not None],
        }

        _publish_event(task_id, "finish", finish_payload)

        TaskStore.update_task_status(
            task_type=task_type,
            task_id=task_id,
            status=TaskStatus.FINISHED if success_flag else TaskStatus.FAILED,
            progress_current=len(generated_images),
            result=finish_payload,
            error="" if success_flag else "部分图片生成失败",
        )

        logger.info(
            f"[图片任务] 执行完成: task_id={task_id}, "
            f"success={success_flag}, completed={len(generated_images)}, failed={len(failed_pages)}"
        )

        # 同步最终状态到历史记录
        final_status = "completed" if success_flag else "partial"
        _sync_history_record(task_id, record_id, user_id, status=final_status)

    except Exception as e:
        logger.error(
            f"[图片任务] 执行异常: task_id={task_id}, error={e}\n{traceback.format_exc()}"
        )

        _publish_event(task_id, "error", {
            "index": None,
            "status": "error",
            "message": f"图片生成异常: {e}",
            "retryable": False,
            "phase": "unknown",
        })

        _publish_event(task_id, "finish", {
            "success": False,
            "task_id": task_id,
            "images": generated_images,
            "total": total,
            "completed": len(generated_images),
            "failed": total - len(generated_images),
            "failed_indices": [],
        })

        TaskStore.update_task_status(
            task_type=task_type,
            task_id=task_id,
            status=TaskStatus.FAILED,
            error=f"图片生成异常: {e}",
        )

        # 异常时也同步已生成的图片（状态为 partial）
        _sync_history_record(task_id, record_id, user_id, status="partial")


__all__ = ["generate_images_task"]
