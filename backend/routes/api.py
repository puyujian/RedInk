"""API 路由"""
import base64
import json
import logging
from typing import Any, Dict
from flask import Blueprint, request, jsonify, Response, send_file
from backend.services.image import get_image_service, ImageTaskStateStore
from backend.services.history import get_history_service
from backend.task_queue import get_outline_queue, get_image_queue
from backend.task_queue.task_store import TaskStore, TaskType, TaskStatus
from backend.tasks import generate_outline_task, generate_images_task
from backend.auth import login_required, get_current_user

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')


def _get_user_id() -> str:
    """获取当前请求绑定的用户标识。

    已登录用户返回用户 UUID，兼容性保留对匿名 X-User-Id 的支持。
    """
    user = get_current_user()
    if user:
        return user.uuid

    user_id = request.headers.get('X-User-Id')
    if not user_id:
        user_id = request.args.get('user_id')
    return (user_id or '').strip()


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
        - 401 Unauthorized: 未登录
        - 500 Internal Error: 创建任务失败

    前端需轮询 GET /api/outline/<task_id> 获取结果。
    """
    try:
        user = get_current_user()
        user_identifier = user.uuid
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
            user_id=user_identifier,
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

        logger.info(f"大纲任务已创建: task_id={task_id}, user_id={user_identifier}")

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
        user_id = _get_user_id()
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
    """创建图片生成任务（异步）。

    请求格式（JSON）:
        {
            "pages": [...],
            "task_id": "可选，前端自定义 ID",
            "full_outline": "...",
            "user_topic": "...",
            "user_images": ["data:image/png;base64,...", ...]
        }

    响应:
        - 202 Accepted: {"success": true, "task_id": "...", "status": "pending"}
        - 400 Bad Request: 参数错误
        - 401 Unauthorized: 未登录
        - 500 Internal Error: 创建任务失败

    前端通过 GET /api/generate/stream/<task_id> 订阅 SSE 事件。
    """
    try:
        user = get_current_user()
        user_identifier = user.uuid
        data = request.get_json() or {}

        pages = data.get('pages') or []
        client_task_id = data.get('task_id')  # 兼容前端自定义 ID
        full_outline = (data.get('full_outline') or '').strip()
        user_topic = (data.get('user_topic') or '').strip()
        user_images_base64 = data.get('user_images') or []

        if not isinstance(pages, list) or not pages:
            return jsonify({
                "success": False,
                "error": "pages 参数不能为空"
            }), 400

        total = len(pages)

        # 创建任务状态（高层任务信息）
        task_id = TaskStore.create_task(
            task_type=TaskType.IMAGE,
            task_id=client_task_id,
            user_id=user_identifier,
            progress_total=total,
        )

        # 初始化图片任务状态（详细页信息、用户参数等）
        ImageTaskStateStore.init_task(
            task_id=task_id,
            pages=pages,
            full_outline=full_outline,
            user_topic=user_topic,
            user_images_base64=user_images_base64,
        )

        # 将任务推入图片队列，由 RQ worker 异步执行
        image_queue = get_image_queue()
        image_queue.enqueue(
            generate_images_task,
            task_id,
            job_id=task_id,
        )

        logger.info(
            f"图片任务已创建: task_id={task_id}, user_id={user_identifier}, total_pages={total}"
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
def stream_image_task(task_id: str):
    """通过 SSE 订阅图片生成任务事件。

    事件格式保持与原实现一致:
        - event: progress / complete / error / finish
        - data: {...}

    前端使用 EventSource 订阅此接口。
    """
    try:
        user_id = _get_user_id()
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

        # 订阅 Redis Pub/Sub 频道
        pubsub = TaskStore.subscribe_events(TaskType.IMAGE, task_id)

        def event_stream():
            try:
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

                    yield f"event: {event_type}\n"
                    yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

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
        user_id = _get_user_id()
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
                    images_summary.append({
                        "index": index,
                        "status": "error",
                        "error": failed[key],
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
        record_id = history_service.create_record(
            topic=topic,
            outline=outline,
            user_id=user.id,
            task_id=task_id
        )

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
        result = history_service.list_records(
            user_id=user.id,
            page=page,
            page_size=page_size,
            status=status
        )

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
        record = history_service.get_record(record_id, user_id=user.id)

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
            record_id=record_id,
            user_id=user.id,
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
        success = history_service.delete_record(record_id, user_id=user.id)

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
        results = history_service.search_records(user_id=user.id, keyword=keyword)

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
        stats = history_service.get_statistics(user_id=user.id)

        return jsonify({
            "success": True,
            **stats
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
