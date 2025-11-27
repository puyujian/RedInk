"""API 路由"""
import base64
import json
import logging
from typing import Any, Dict, List, Optional
from flask import Blueprint, request, jsonify, Response, send_file
from backend.services.image import get_image_service, ImageTaskStateStore
from backend.services.history import get_history_service
from backend.task_queue import get_outline_queue, get_image_queue
from backend.task_queue.task_store import TaskStore, TaskType, TaskStatus
from backend.tasks import generate_outline_task, generate_images_task
from backend.auth import login_required, get_current_user

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/outline', methods=['POST'])
@login_required
def create_outline_task():
    """创建大纲生成任务（异步）。

    请求格式:
        - multipart/form-data: topic (必需), images[] (可选)
        - application/json: {"topic": "...", "images": ["base64..."]}

    响应:
        - 202 Accepted: {"success": true, "task_id": "...", "status": "pending"}
        - 400 Bad Request: topic 为空
        - 500 Internal Error: 创建任务失败

    前端需轮询 GET /api/outline/<task_id> 获取结果。
    """
    try:
        user = get_current_user()
        user_id = str(user.id)
        images_base64 = []

        # 解析请求体
        if request.content_type and 'multipart/form-data' in request.content_type:
            topic = request.form.get('topic')
            if 'images' in request.files:
                files = request.files.getlist('images')
                for file in files:
                    if file and file.filename:
                        image_data = file.read()
                        images_base64.append(base64.b64encode(image_data).decode('utf-8'))
        else:
            data = request.get_json() or {}
            topic = data.get('topic')
            images_base64 = data.get('images') or []

        # 参数校验
        if not topic or not topic.strip():
            return jsonify({
                "success": False,
                "error": "topic 参数不能为空"
            }), 400

        # 创建任务
        task_id = TaskStore.create_task(
            task_type=TaskType.OUTLINE,
            user_id=user_id,
            progress_total=1,
            extra_fields={"topic": topic.strip()},
        )

        # 入队异步执行
        outline_queue = get_outline_queue()
        outline_queue.enqueue(
            generate_outline_task,
            task_id,
            topic.strip(),
            images_base64 if images_base64 else None,
            job_id=task_id,
        )

        logger.info(f"大纲任务已创建: task_id={task_id}, user_id={user_id}")

        return jsonify({
            "success": True,
            "task_id": task_id,
            "status": TaskStatus.PENDING.value,
        }), 202

    except Exception as e:
        logger.exception("创建大纲任务失败")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route('/outline/<task_id>', methods=['GET'])
@login_required
def get_outline_task_status(task_id: str):
    """查询大纲生成任务状态。

    响应:
        - 200 OK: {"success": true, "status": "...", ...}
          - status=pending/running: 等待或执行中
          - status=finished: 包含 outline, pages 字段
          - status=failed: 包含 error 字段
        - 404 Not Found: 任务不存在
    """
    try:
        user = get_current_user()
        user_id = str(user.id)
        task = TaskStore.get_task(TaskType.OUTLINE, task_id)

        if not task:
            return jsonify({
                "success": False,
                "error": "任务不存在"
            }), 404

        # 可选：验证用户权限（如果有 user_id）
        task_user_id = task.get("user_id", "")
        if user_id and task_user_id and user_id != task_user_id:
            return jsonify({
                "success": False,
                "error": "无权访问此任务"
            }), 403

        response = {
            "success": True,
            "task_id": task_id,
            "status": task.get("status", "unknown"),
            "progress_current": task.get("progress_current", 0),
            "progress_total": task.get("progress_total", 0),
        }

        # 解析结果字段
        result_str = task.get("result", "")
        if result_str:
            try:
                result_data = json.loads(result_str)
                if isinstance(result_data, dict):
                    # 展开结果到响应中
                    response.update(result_data)
            except json.JSONDecodeError:
                response["result"] = result_str

        # 添加错误信息
        if task.get("error"):
            response["error"] = task.get("error")

        return jsonify(response), 200

    except Exception as e:
        logger.exception(f"查询大纲任务失败: task_id={task_id}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route('/generate', methods=['POST'])
@login_required
def create_image_task():
    """创建图片生成任务(异步)。

    请求格式(JSON):
        {
            "pages": [...],
            "task_id": "可选,前端自定义 ID",
            "full_outline": "...",
            "user_topic": "...",
            "user_images": ["data:image/png;base64,...", ...]
        }

    响应:
        - 202 Accepted: {"success": true, "task_id": "...", "status": "pending"}
        - 400 Bad Request: 参数错误
        - 413 Payload Too Large: 请求体过大
        - 500 Internal Error: 创建任务失败

    前端通过 GET /api/generate/stream/<task_id> 订阅 SSE 事件。
    """
    try:
        user = get_current_user()
        user_id = str(user.id)
        data = request.get_json() or {}

        pages = data.get('pages') or []
        client_task_id = data.get('task_id')  # 兼容前端自定义 ID
        full_outline = (data.get('full_outline') or '').strip()
        user_topic = (data.get('user_topic') or '').strip()
        user_images_base64 = data.get('user_images') or []
        record_id = (data.get('record_id') or '').strip()  # 关联的历史记录 UUID

        # 参数验证
        if not isinstance(pages, list) or not pages:
            return jsonify({
                "success": False,
                "error": "pages 参数不能为空"
            }), 400

        # 验证图片数量限制(最多10张)
        if isinstance(user_images_base64, list) and len(user_images_base64) > 10:
            return jsonify({
                "success": False,
                "error": f"最多只能上传 10 张参考图片,当前上传了 {len(user_images_base64)} 张"
            }), 400

        # 验证单张图片大小(base64 编码后最大 15MB ≈ 实际图片 11MB)
        if isinstance(user_images_base64, list):
            for idx, img_b64 in enumerate(user_images_base64):
                if img_b64:
                    # 移除 data URL 前缀
                    if "," in img_b64:
                        img_b64 = img_b64.split(",", 1)[1]
                    # 估算 base64 大小(字节)
                    img_size_mb = len(img_b64) * 0.75 / (1024 * 1024)  # base64 -> bytes
                    if img_size_mb > 15:
                        return jsonify({
                            "success": False,
                            "error": f"第 {idx + 1} 张图片过大({img_size_mb:.1f}MB),单张图片不能超过 15MB"
                        }), 400

        total = len(pages)

        # 创建任务状态(高层任务信息)
        task_id = TaskStore.create_task(
            task_type=TaskType.IMAGE,
            task_id=client_task_id,
            user_id=user_id,
            progress_total=total,
        )

        # 初始化图片任务状态(详细页信息、用户参数等)
        ImageTaskStateStore.init_task(
            task_id=task_id,
            pages=pages,
            full_outline=full_outline,
            user_topic=user_topic,
            user_images_base64=user_images_base64,
            record_id=record_id,
        )

        # 将任务推入图片队列,由 RQ worker 异步执行
        image_queue = get_image_queue()
        image_queue.enqueue(
            generate_images_task,
            task_id,
            job_id=task_id,
        )

        logger.info(
            f"图片任务已创建: task_id={task_id}, user_id={user_id}, total_pages={total}, "
            f"user_images_count={len(user_images_base64) if user_images_base64 else 0}"
        )

        return jsonify({
            "success": True,
            "task_id": task_id,
            "status": TaskStatus.PENDING.value,
        }), 202

    except Exception as e:
        logger.exception("创建图片任务失败")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route('/generate/stream/<task_id>', methods=['GET'])
@login_required
def stream_image_task(task_id: str):
    """通过 SSE 订阅图片生成任务事件。

    事件格式保持与原实现一致:
        - event: progress / complete / error / finish
        - data: {...}

    前端使用 EventSource 订阅此接口。

    为了保证前端能实时展示状态，本接口会在监听 Redis 之前，先将当前
    已完成/失败的页面补发给新订阅者（断线重连或晚订阅场景）。
    """
    try:
        user = get_current_user()
        user_id = str(user.id)
        task = TaskStore.get_task(TaskType.IMAGE, task_id)

        if not task:
            return jsonify({
                "success": False,
                "error": "任务不存在"
            }), 404

        # 验证用户权限
        task_user_id = task.get("user_id", "")
        if user_id and task_user_id and user_id != task_user_id:
            return jsonify({
                "success": False,
                "error": "无权访问此任务"
            }), 403

        task_status = str(task.get("status") or "").lower()

        # 订阅 Redis Pub/Sub 频道
        pubsub = TaskStore.subscribe_events(TaskType.IMAGE, task_id)

        def event_stream():
            try:
                initial_finished = {"value": False}

                def emit_event(event_type: str, event_data: Dict[str, Any]):
                    yield f"event: {event_type}\n"
                    yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

                def sort_index(value: str) -> int:
                    try:
                        return int(value)
                    except (TypeError, ValueError):
                        return 0

                def get_phase(index_key: str, page_type_map: Dict[str, str]) -> str:
                    return "cover" if page_type_map.get(index_key) == "cover" else "content"

                def build_finish_payload(state_data: Optional[Dict[str, Any]]):
                    result_raw = task.get("result")
                    finish_data: Optional[Dict[str, Any]] = None

                    if isinstance(result_raw, dict):
                        finish_data = result_raw
                    elif isinstance(result_raw, str) and result_raw.strip():
                        try:
                            parsed = json.loads(result_raw)
                            if isinstance(parsed, dict):
                                finish_data = parsed
                        except json.JSONDecodeError:
                            pass

                    status_lower = task_status
                    is_terminal = status_lower in (TaskStatus.FINISHED.value, TaskStatus.FAILED.value)

                    if not finish_data and state_data and is_terminal:
                        generated_map = state_data.get("generated") or {}
                        failed_map = state_data.get("failed") or {}
                        total_pages = len(state_data.get("pages") or [])

                        ordered_images = [
                            generated_map[key]
                            for key in sorted(generated_map.keys(), key=sort_index)
                            if generated_map.get(key)
                        ]

                        failed_indices: List[int] = []
                        for key in sorted(failed_map.keys(), key=sort_index):
                            try:
                                failed_indices.append(int(key))
                            except (TypeError, ValueError):
                                continue

                        finish_data = {
                            "success": status_lower == TaskStatus.FINISHED.value,
                            "task_id": task_id,
                            "images": ordered_images,
                            "total": total_pages,
                            "completed": len(ordered_images),
                            "failed": len(failed_indices),
                            "failed_indices": failed_indices,
                        }

                    if finish_data:
                        finish_data.setdefault("task_id", task_id)
                    return finish_data

                def emit_initial_state():
                    state = ImageTaskStateStore.load_state(task_id)
                    if not state:
                        return

                    generated = state.get("generated") or {}
                    failed = state.get("failed") or {}
                    candidates_map = state.get("candidates") or {}
                    pages = state.get("pages") or []

                    page_type_map: Dict[str, str] = {}
                    for page in pages:
                        index = page.get("index")
                        if index is None:
                            continue
                        page_type_map[str(index)] = page.get("type") or ""

                    # 补发已完成的页面
                    for index_key in sorted(generated.keys(), key=sort_index):
                        filename = generated.get(index_key)
                        if not filename:
                            continue

                        try:
                            index = int(index_key)
                        except (TypeError, ValueError):
                            continue

                        candidate_files = candidates_map.get(index_key) or [filename]
                        candidate_urls = [f"/api/images/{f}" for f in candidate_files]

                        event_data = {
                            "index": index,
                            "status": "done",
                            "image_url": f"/api/images/{filename}",
                            "candidates": candidate_urls,
                            "phase": get_phase(index_key, page_type_map),
                        }

                        for chunk in emit_event("complete", event_data):
                            yield chunk

                    # 补发失败的页面
                    for index_key in sorted(failed.keys(), key=sort_index):
                        failed_info = failed.get(index_key)
                        # 兼容两种格式：字符串（旧）和字典（新）
                        if isinstance(failed_info, dict):
                            message = failed_info.get("message") or "图片生成失败"
                            retryable = failed_info.get("retryable", True)
                        else:
                            message = failed_info or "图片生成失败"
                            retryable = True  # 旧格式默认可重试

                        try:
                            index = int(index_key)
                        except (TypeError, ValueError):
                            continue

                        event_data = {
                            "index": index,
                            "status": "error",
                            "message": message,
                            "retryable": retryable,
                            "phase": get_phase(index_key, page_type_map),
                        }

                        for chunk in emit_event("error", event_data):
                            yield chunk

                    finish_payload = build_finish_payload(state)
                    if finish_payload:
                        initial_finished["value"] = True
                        for chunk in emit_event("finish", finish_payload):
                            yield chunk

                # 先补发已有状态
                for chunk in emit_initial_state():
                    yield chunk

                if initial_finished["value"]:
                    return

                # 再监听新的事件
                for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue

                    data = message.get("data")
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")

                    try:
                        payload = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    event_type = payload.get("event") or "message"
                    event_data = payload.get("data") or {}

                    for chunk in emit_event(event_type, event_data):
                        yield chunk

                    # finish 事件后结束流
                    if event_type == "finish":
                        break
            finally:
                pubsub.close()

        return Response(
            event_stream(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
            }
        )

    except Exception as e:
        logger.exception(f"订阅图片任务事件失败: task_id={task_id}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route('/generate/<task_id>', methods=['GET'])
@login_required
def get_image_task_status(task_id: str):
    """查询图片生成任务状态及每页生成情况。

    响应:
        {
            "success": true,
            "task_id": "...",
            "status": "running",
            "progress_current": 5,
            "progress_total": 10,
            "images": [
                {"index": 0, "status": "done", "image_url": "...", "candidates": [...]},
                {"index": 1, "status": "error", "error": "..."},
                {"index": 2, "status": "pending"}
            ]
        }
    """
    try:
        user = get_current_user()
        user_id = str(user.id)
        task = TaskStore.get_task(TaskType.IMAGE, task_id)

        if not task:
            return jsonify({
                "success": False,
                "error": "任务不存在"
            }), 404

        # 验证用户权限
        task_user_id = task.get("user_id", "")
        if user_id and task_user_id and user_id != task_user_id:
            return jsonify({
                "success": False,
                "error": "无权访问此任务"
            }), 403

        response: Dict[str, Any] = {
            "success": True,
            "task_id": task_id,
            "status": task.get("status", "unknown"),
            "progress_current": task.get("progress_current", 0),
            "progress_total": task.get("progress_total", 0),
        }

        # 汇总每页图片生成状态
        state = ImageTaskStateStore.load_state(task_id)
        if state:
            pages = state.get("pages") or []
            generated = state.get("generated") or {}
            failed = state.get("failed") or {}
            candidates_map = state.get("candidates") or {}

            images_summary = []
            for page in pages:
                index = page.get("index")
                if index is None:
                    continue
                key = str(index)

                if key in generated:
                    filename = generated[key]
                    candidate_files = candidates_map.get(key) or [filename]
                    images_summary.append({
                        "index": index,
                        "status": "done",
                        "image_url": f"/api/images/{filename}",
                        "candidates": [f"/api/images/{f}" for f in candidate_files],
                    })
                elif key in failed:
                    # 兼容两种格式：字符串（旧）和字典（新）
                    failed_info = failed[key]
                    if isinstance(failed_info, dict):
                        error_message = failed_info.get("message") or "图片生成失败"
                        retryable = failed_info.get("retryable", True)
                    else:
                        error_message = failed_info or "图片生成失败"
                        retryable = True  # 旧格式默认可重试
                    images_summary.append({
                        "index": index,
                        "status": "error",
                        "error": error_message,
                        "retryable": retryable,
                    })
                else:
                    images_summary.append({
                        "index": index,
                        "status": "pending",
                    })

            response["images"] = images_summary

        if task.get("error"):
            response["error"] = task.get("error")

        return jsonify(response), 200

    except Exception as e:
        logger.exception(f"查询图片任务失败: task_id={task_id}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route('/images/<filename>', methods=['GET'])
def get_image(filename):
    """获取图片"""
    try:
        image_service = get_image_service()
        filepath = image_service.get_image_path(filename)

        return send_file(filepath, mimetype='image/png')

    except FileNotFoundError:
        return jsonify({
            "success": False,
            "error": "图片不存在"
        }), 404
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route('/retry', methods=['POST'])
def retry_single_image():
    """重试生成单张图片"""
    try:
        data = request.get_json()
        task_id = data.get('task_id')
        page = data.get('page')
        use_reference = data.get('use_reference', True)

        if not task_id or not page:
            return jsonify({
                "success": False,
                "error": "task_id 和 page 参数不能为空"
            }), 400

        image_service = get_image_service()
        result = image_service.retry_single_image(task_id, page, use_reference)

        return jsonify(result), 200 if result["success"] else 500

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route('/retry-failed', methods=['POST'])
def retry_failed_images():
    """批量重试失败的图片（SSE 流式返回）"""
    try:
        data = request.get_json()
        task_id = data.get('task_id')
        pages = data.get('pages')

        if not task_id or not pages:
            return jsonify({
                "success": False,
                "error": "task_id 和 pages 参数不能为空"
            }), 400

        image_service = get_image_service()

        def generate():
            """SSE 生成器"""
            for event in image_service.retry_failed_images(task_id, pages):
                event_type = event["event"]
                event_data = event["data"]

                yield f"event: {event_type}\n"
                yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

        return Response(
            generate(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
            }
        )

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route('/regenerate', methods=['POST'])
def regenerate_image():
    """重新生成图片（即使成功的也可以重新生成）"""
    try:
        data = request.get_json()
        task_id = data.get('task_id')
        page = data.get('page')
        use_reference = data.get('use_reference', True)

        if not task_id or not page:
            return jsonify({
                "success": False,
                "error": "task_id 和 page 参数不能为空"
            }), 400

        image_service = get_image_service()
        result = image_service.regenerate_image(task_id, page, use_reference)

        return jsonify(result), 200 if result["success"] else 500

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route('/task/<task_id>', methods=['GET'])
def get_task_state(task_id):
    """获取任务状态"""
    try:
        image_service = get_image_service()
        state = image_service.get_task_state(task_id)

        if state is None:
            return jsonify({
                "success": False,
                "error": "任务不存在"
            }), 404

        # 不返回封面图片数据（太大）
        safe_state = {
            "generated": state.get("generated", {}),
            "failed": state.get("failed", {}),
            "has_cover": state.get("cover_image") is not None
        }

        return jsonify({
            "success": True,
            "state": safe_state
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        "success": True,
        "message": "服务正常运行"
    }), 200


# ==================== 历史记录相关 API ====================

@api_bp.route('/history', methods=['POST'])
@login_required
def create_history():
    """创建历史记录"""
    try:
        user = get_current_user()
        data = request.get_json()
        topic = data.get('topic')
        outline = data.get('outline')
        task_id = data.get('task_id')

        if not topic or not outline:
            return jsonify({
                "success": False,
                "error": "topic 和 outline 参数不能为空"
            }), 400

        history_service = get_history_service()
        record_id = history_service.create_record(user.id, topic, outline, task_id)

        return jsonify({
            "success": True,
            "record_id": record_id
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route('/history', methods=['GET'])
@login_required
def list_history():
    """获取历史记录列表"""
    try:
        user = get_current_user()
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 20))
        status = request.args.get('status')

        history_service = get_history_service()
        result = history_service.list_records(user.id, page, page_size, status)

        return jsonify({
            "success": True,
            **result
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route('/history/<record_id>', methods=['GET'])
@login_required
def get_history(record_id):
    """获取历史记录详情"""
    try:
        user = get_current_user()
        history_service = get_history_service()
        record = history_service.get_record(user.id, record_id)

        if not record:
            return jsonify({
                "success": False,
                "error": "记录不存在"
            }), 404

        return jsonify({
            "success": True,
            "record": record
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route('/history/<record_id>', methods=['PUT'])
@login_required
def update_history(record_id):
    """更新历史记录"""
    try:
        user = get_current_user()
        data = request.get_json()
        outline = data.get('outline')
        images = data.get('images')
        status = data.get('status')
        thumbnail = data.get('thumbnail')

        history_service = get_history_service()
        success = history_service.update_record(
            user.id,
            record_id,
            outline=outline,
            images=images,
            status=status,
            thumbnail=thumbnail
        )

        if not success:
            return jsonify({
                "success": False,
                "error": "更新失败或记录不存在"
            }), 404

        return jsonify({
            "success": True
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route('/history/<record_id>', methods=['DELETE'])
@login_required
def delete_history(record_id):
    """删除历史记录"""
    try:
        user = get_current_user()
        history_service = get_history_service()
        success = history_service.delete_record(user.id, record_id)

        if not success:
            return jsonify({
                "success": False,
                "error": "删除失败或记录不存在"
            }), 404

        return jsonify({
            "success": True
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route('/history/search', methods=['GET'])
@login_required
def search_history():
    """搜索历史记录"""
    try:
        user = get_current_user()
        keyword = request.args.get('keyword', '')

        if not keyword:
            return jsonify({
                "success": False,
                "error": "keyword 参数不能为空"
            }), 400

        history_service = get_history_service()
        results = history_service.search_records(user.id, keyword)

        return jsonify({
            "success": True,
            "records": results
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route('/history/stats', methods=['GET'])
@login_required
def get_history_stats():
    """获取历史记录统计"""
    try:
        user = get_current_user()
        history_service = get_history_service()
        stats = history_service.get_statistics(user.id)

        return jsonify({
            "success": True,
            **stats
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
