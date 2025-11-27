"""
后台管理 API 路由

提供用户管理、生成记录管理、图片管理、配置管理、注册开关等功能
所有端点均需要管理员权限
"""
import io
import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any

import yaml
from flask import Blueprint, request, jsonify, g
from sqlalchemy import func, or_

from backend.auth import admin_required, get_current_user, hash_password
from backend.db import get_db
from backend.models import (
    User,
    HistoryRecord,
    ImageFile,
    ConfigVersion,
    RegistrationSetting,
    AuditLog,
)
from backend.config import Config

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


# ============================================================================
# 工具函数
# ============================================================================

def _json_success(data: Any = None, **kwargs) -> tuple:
    """返回成功响应"""
    response = {"success": True}
    if data is not None:
        response["data"] = data
    response.update(kwargs)
    return jsonify(response), 200


def _json_error(message: str, status: int = 400) -> tuple:
    """返回错误响应"""
    return jsonify({"success": False, "error": message}), status


def _get_pagination_params() -> tuple:
    """获取分页参数"""
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
    return page, page_size


def _user_to_dict(user: User) -> dict:
    """将用户对象转换为字典"""
    return {
        "id": user.id,
        "uuid": user.uuid,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "client_id": user.client_id,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def _record_to_dict(record: HistoryRecord) -> dict:
    """将历史记录对象转换为字典"""
    return {
        "id": record.id,
        "record_uuid": record.record_uuid,
        "user_id": record.user_id,
        "client_id": record.client_id,
        "title": record.title,
        "status": record.status,
        "thumbnail_url": record.thumbnail_url,
        "page_count": record.page_count,
        "image_task_id": record.image_task_id,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def _image_to_dict(image: ImageFile) -> dict:
    """将图片文件对象转换为字典"""
    return {
        "id": image.id,
        "user_id": image.user_id,
        "record_id": image.record_id,
        "task_id": image.task_id,
        "filename": image.filename,
        "file_size": image.file_size,
        "created_at": image.created_at.isoformat() if image.created_at else None,
    }


def _audit_log(
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[dict] = None
) -> None:
    """记录审计日志"""
    db = get_db()
    try:
        user = get_current_user()
        log = AuditLog(
            actor_id=user.id if user else None,
            actor_username=user.username if user else None,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            details=details,
            ip_address=request.remote_addr,
        )
        db.add(log)
        db.commit()
    except Exception as e:
        logger.error(f"记录审计日志失败: {e}")
        db.rollback()
    finally:
        db.close()


def _is_last_admin(user: User, db) -> bool:
    """检查是否是唯一的管理员"""
    if user.role != "admin":
        return False
    admin_count = db.query(User).filter(
        User.role == "admin",
        User.is_active == True
    ).count()
    return admin_count <= 1


# ============================================================================
# 用户管理
# ============================================================================

@admin_bp.route("/users", methods=["GET"])
@admin_required
def list_users():
    """
    获取用户列表（分页）

    Query Parameters:
        page: 页码，默认 1
        page_size: 每页数量，默认 20，最大 100
        username: 用户名筛选（模糊匹配）
        email: 邮箱筛选（模糊匹配）
        role: 角色筛选
        status: 状态筛选（active/inactive）
        sort: 排序字段，默认 -created_at（负号表示降序）
    """
    try:
        page, page_size = _get_pagination_params()

        db = get_db()
        try:
            query = db.query(User)

            # 筛选条件
            if username := request.args.get("username"):
                query = query.filter(User.username.ilike(f"%{username}%"))
            if email := request.args.get("email"):
                query = query.filter(User.email.ilike(f"%{email}%"))
            if role := request.args.get("role"):
                query = query.filter(User.role == role)
            if status := request.args.get("status"):
                query = query.filter(User.is_active == (status == "active"))

            # 排序
            sort = request.args.get("sort", "-created_at")
            desc = sort.startswith("-")
            sort_field = sort[1:] if desc else sort
            if hasattr(User, sort_field):
                col = getattr(User, sort_field)
                query = query.order_by(col.desc() if desc else col.asc())

            # 统计总数
            total = query.count()

            # 分页
            offset = (page - 1) * page_size
            users = query.offset(offset).limit(page_size).all()

            return _json_success(
                data=[_user_to_dict(u) for u in users],
                page=page,
                page_size=page_size,
                total=total,
            )
        finally:
            db.close()

    except Exception as e:
        logger.error(f"获取用户列表失败: {e}", exc_info=True)
        return _json_error("获取用户列表失败", 500)


@admin_bp.route("/users/<int:user_id>", methods=["GET"])
@admin_required
def get_user(user_id: int):
    """获取用户详情"""
    try:
        db = get_db()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return _json_error("用户不存在", 404)
            return _json_success(data=_user_to_dict(user))
        finally:
            db.close()

    except Exception as e:
        logger.error(f"获取用户详情失败: {e}", exc_info=True)
        return _json_error("获取用户详情失败", 500)


@admin_bp.route("/users", methods=["POST"])
@admin_required
def create_user():
    """
    创建用户

    Request Body:
        {
            "username": "用户名（必填）",
            "email": "邮箱（可选）",
            "password": "密码（必填）",
            "role": "角色（可选，默认 user）",
            "is_active": "是否激活（可选，默认 true）"
        }
    """
    try:
        data = request.get_json() or {}
        username = (data.get("username") or "").strip()
        email = (data.get("email") or "").strip() or None
        password = data.get("password") or ""
        role = data.get("role", "user")
        is_active = data.get("is_active", True)

        # 验证输入
        if not username:
            return _json_error("用户名不能为空")
        if len(username) < 3 or len(username) > 50:
            return _json_error("用户名长度必须在 3-50 个字符之间")
        if not password:
            return _json_error("密码不能为空")
        if len(password) < 6:
            return _json_error("密码长度至少为 6 个字符")
        if role not in ("user", "admin", "pro"):
            return _json_error("角色必须是 user、admin 或 pro")

        db = get_db()
        try:
            # 检查用户名是否已存在
            if db.query(User).filter(User.username == username).first():
                return _json_error("用户名已被使用")

            # 检查邮箱是否已存在
            if email and db.query(User).filter(User.email == email).first():
                return _json_error("邮箱已被使用")

            # 创建用户
            user = User(
                username=username,
                email=email,
                password_hash=hash_password(password),
                role=role,
                is_active=is_active,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            # 记录审计日志
            _audit_log("create_user", "user", user.id, {"username": username, "role": role})

            return jsonify({
                "success": True,
                "data": _user_to_dict(user)
            }), 201

        finally:
            db.close()

    except Exception as e:
        logger.error(f"创建用户失败: {e}", exc_info=True)
        return _json_error("创建用户失败", 500)


@admin_bp.route("/users/<int:user_id>", methods=["PUT"])
@admin_required
def update_user(user_id: int):
    """
    更新用户信息

    Request Body:
        {
            "username": "用户名（可选）",
            "email": "邮箱（可选）",
            "password": "密码（可选，重置密码）",
            "role": "角色（可选）",
            "is_active": "是否激活（可选）"
        }
    """
    try:
        data = request.get_json() or {}

        db = get_db()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return _json_error("用户不存在", 404)

            # 防止降级或禁用唯一管理员
            if _is_last_admin(user, db):
                if "role" in data and data["role"] != "admin":
                    return _json_error("禁止降级唯一管理员")
                if "is_active" in data and not data["is_active"]:
                    return _json_error("禁止禁用唯一管理员")

            # 更新字段
            changes = {}
            if "username" in data:
                username = (data["username"] or "").strip()
                if username and username != user.username:
                    if db.query(User).filter(User.username == username, User.id != user_id).first():
                        return _json_error("用户名已被使用")
                    user.username = username
                    changes["username"] = username

            if "email" in data:
                email = (data["email"] or "").strip() or None
                if email != user.email:
                    if email and db.query(User).filter(User.email == email, User.id != user_id).first():
                        return _json_error("邮箱已被使用")
                    user.email = email
                    changes["email"] = email

            if "password" in data and data["password"]:
                user.password_hash = hash_password(data["password"])
                changes["password"] = "***已重置***"

            if "role" in data:
                if data["role"] not in ("user", "admin", "pro"):
                    return _json_error("角色必须是 user、admin 或 pro")
                user.role = data["role"]
                changes["role"] = data["role"]

            if "is_active" in data:
                user.is_active = bool(data["is_active"])
                changes["is_active"] = user.is_active

            db.commit()
            db.refresh(user)

            # 记录审计日志
            _audit_log("update_user", "user", user_id, changes)

            return _json_success(data=_user_to_dict(user))

        finally:
            db.close()

    except Exception as e:
        logger.error(f"更新用户失败: {e}", exc_info=True)
        return _json_error("更新用户失败", 500)


@admin_bp.route("/users/<int:user_id>/status", methods=["PATCH"])
@admin_required
def toggle_user_status(user_id: int):
    """
    切换用户状态（启用/禁用）

    Request Body:
        {
            "is_active": true/false
        }
    """
    try:
        data = request.get_json() or {}
        if "is_active" not in data:
            return _json_error("缺少 is_active 参数")

        db = get_db()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return _json_error("用户不存在", 404)

            # 防止禁用唯一管理员
            if _is_last_admin(user, db) and not data["is_active"]:
                return _json_error("禁止禁用唯一管理员")

            user.is_active = bool(data["is_active"])
            db.commit()
            db.refresh(user)

            # 记录审计日志
            _audit_log(
                "toggle_user_status",
                "user",
                user_id,
                {"is_active": user.is_active}
            )

            return _json_success(data=_user_to_dict(user))

        finally:
            db.close()

    except Exception as e:
        logger.error(f"切换用户状态失败: {e}", exc_info=True)
        return _json_error("切换用户状态失败", 500)


@admin_bp.route("/users/<int:user_id>", methods=["DELETE"])
@admin_required
def delete_user(user_id: int):
    """删除用户"""
    try:
        db = get_db()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return _json_error("用户不存在", 404)

            # 防止删除唯一管理员
            if _is_last_admin(user, db):
                return _json_error("禁止删除唯一管理员")

            username = user.username
            db.delete(user)
            db.commit()

            # 记录审计日志
            _audit_log("delete_user", "user", user_id, {"username": username})

            return _json_success(message="用户已删除")

        finally:
            db.close()

    except Exception as e:
        logger.error(f"删除用户失败: {e}", exc_info=True)
        return _json_error("删除用户失败", 500)


# ============================================================================
# 生成记录管理
# ============================================================================

@admin_bp.route("/records", methods=["GET"])
@admin_required
def list_records():
    """
    获取生成记录列表（分页）

    Query Parameters:
        page: 页码
        page_size: 每页数量
        user_id: 用户 ID 筛选
        status: 状态筛选
        q: 标题关键词搜索
        start_at: 开始时间
        end_at: 结束时间
        sort: 排序字段
    """
    try:
        page, page_size = _get_pagination_params()

        db = get_db()
        try:
            query = db.query(HistoryRecord)

            # 筛选条件
            if user_id := request.args.get("user_id"):
                query = query.filter(HistoryRecord.user_id == int(user_id))
            if status := request.args.get("status"):
                query = query.filter(HistoryRecord.status == status)
            if q := request.args.get("q"):
                query = query.filter(HistoryRecord.title.ilike(f"%{q}%"))
            if start_at := request.args.get("start_at"):
                query = query.filter(HistoryRecord.created_at >= start_at)
            if end_at := request.args.get("end_at"):
                query = query.filter(HistoryRecord.created_at <= end_at)

            # 排序
            sort = request.args.get("sort", "-created_at")
            desc = sort.startswith("-")
            sort_field = sort[1:] if desc else sort
            if hasattr(HistoryRecord, sort_field):
                col = getattr(HistoryRecord, sort_field)
                query = query.order_by(col.desc() if desc else col.asc())

            # 统计总数
            total = query.count()

            # 分页
            offset = (page - 1) * page_size
            records = query.offset(offset).limit(page_size).all()

            return _json_success(
                data=[_record_to_dict(r) for r in records],
                page=page,
                page_size=page_size,
                total=total,
            )
        finally:
            db.close()

    except Exception as e:
        logger.error(f"获取记录列表失败: {e}", exc_info=True)
        return _json_error("获取记录列表失败", 500)


@admin_bp.route("/records/<int:record_id>", methods=["GET"])
@admin_required
def get_record(record_id: int):
    """获取记录详情（包含完整数据）"""
    try:
        db = get_db()
        try:
            record = db.query(HistoryRecord).filter(HistoryRecord.id == record_id).first()
            if not record:
                return _json_error("记录不存在", 404)

            data = _record_to_dict(record)
            # 添加详细数据
            data["outline_raw"] = record.outline_raw
            data["outline_json"] = record.outline_json
            data["images_json"] = record.images_json

            return _json_success(data=data)
        finally:
            db.close()

    except Exception as e:
        logger.error(f"获取记录详情失败: {e}", exc_info=True)
        return _json_error("获取记录详情失败", 500)


@admin_bp.route("/records/<int:record_id>", methods=["DELETE"])
@admin_required
def delete_record(record_id: int):
    """删除记录"""
    try:
        db = get_db()
        try:
            record = db.query(HistoryRecord).filter(HistoryRecord.id == record_id).first()
            if not record:
                return _json_error("记录不存在", 404)

            title = record.title
            db.delete(record)
            db.commit()

            # 记录审计日志
            _audit_log("delete_record", "history_record", record_id, {"title": title})

            return _json_success(message="记录已删除")

        finally:
            db.close()

    except Exception as e:
        logger.error(f"删除记录失败: {e}", exc_info=True)
        return _json_error("删除记录失败", 500)


@admin_bp.route("/records", methods=["DELETE"])
@admin_required
def bulk_delete_records():
    """
    批量删除记录

    Request Body:
        {
            "ids": [1, 2, 3]
        }
    """
    try:
        data = request.get_json() or {}
        ids = data.get("ids", [])
        if not ids:
            return _json_error("缺少 ids 参数")

        db = get_db()
        try:
            deleted = db.query(HistoryRecord).filter(
                HistoryRecord.id.in_(ids)
            ).delete(synchronize_session=False)
            db.commit()

            # 记录审计日志
            _audit_log("bulk_delete_records", "history_record", details={"ids": ids, "deleted": deleted})

            return _json_success(deleted=deleted)

        finally:
            db.close()

    except Exception as e:
        logger.error(f"批量删除记录失败: {e}", exc_info=True)
        return _json_error("批量删除记录失败", 500)


# ============================================================================
# 图片管理
# ============================================================================

@admin_bp.route("/images", methods=["GET"])
@admin_required
def list_images():
    """
    获取图片列表（分页）

    Query Parameters:
        page: 页码
        page_size: 每页数量
        user_id: 用户 ID 筛选
        record_id: 记录 ID 筛选
        start_at: 开始时间
        end_at: 结束时间
        sort: 排序字段
    """
    try:
        page, page_size = _get_pagination_params()

        db = get_db()
        try:
            query = db.query(ImageFile)

            # 筛选条件
            if user_id := request.args.get("user_id"):
                query = query.filter(ImageFile.user_id == int(user_id))
            if record_id := request.args.get("record_id"):
                query = query.filter(ImageFile.record_id == int(record_id))
            if start_at := request.args.get("start_at"):
                query = query.filter(ImageFile.created_at >= start_at)
            if end_at := request.args.get("end_at"):
                query = query.filter(ImageFile.created_at <= end_at)

            # 排序
            sort = request.args.get("sort", "-created_at")
            desc = sort.startswith("-")
            sort_field = sort[1:] if desc else sort
            if hasattr(ImageFile, sort_field):
                col = getattr(ImageFile, sort_field)
                query = query.order_by(col.desc() if desc else col.asc())

            # 统计总数
            total = query.count()

            # 分页
            offset = (page - 1) * page_size
            images = query.offset(offset).limit(page_size).all()

            return _json_success(
                data=[_image_to_dict(img) for img in images],
                page=page,
                page_size=page_size,
                total=total,
            )
        finally:
            db.close()

    except Exception as e:
        logger.error(f"获取图片列表失败: {e}", exc_info=True)
        return _json_error("获取图片列表失败", 500)


@admin_bp.route("/images/stats", methods=["GET"])
@admin_required
def image_stats():
    """获取图片存储统计"""
    try:
        db = get_db()
        try:
            total_count = db.query(ImageFile).count()
            total_size = db.query(func.coalesce(func.sum(ImageFile.file_size), 0)).scalar()

            # 按用户统计
            user_stats = db.query(
                ImageFile.user_id,
                func.count(ImageFile.id).label("count"),
                func.coalesce(func.sum(ImageFile.file_size), 0).label("size")
            ).group_by(ImageFile.user_id).all()

            return _json_success(
                data={
                    "total_count": total_count,
                    "total_size_bytes": total_size,
                    "total_size_mb": round(total_size / (1024 * 1024), 2) if total_size else 0,
                    "by_user": [
                        {"user_id": s.user_id, "count": s.count, "size_bytes": s.size}
                        for s in user_stats
                    ]
                }
            )
        finally:
            db.close()

    except Exception as e:
        logger.error(f"获取图片统计失败: {e}", exc_info=True)
        return _json_error("获取图片统计失败", 500)


@admin_bp.route("/images/<int:image_id>", methods=["DELETE"])
@admin_required
def delete_image(image_id: int):
    """删除图片"""
    try:
        db = get_db()
        try:
            image = db.query(ImageFile).filter(ImageFile.id == image_id).first()
            if not image:
                return _json_error("图片不存在", 404)

            filename = image.filename

            # 删除物理文件
            file_path = Path(Config.OUTPUT_DIR) / filename
            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception as e:
                    logger.warning(f"删除文件失败: {file_path}, {e}")

            db.delete(image)
            db.commit()

            # 记录审计日志
            _audit_log("delete_image", "image_file", image_id, {"filename": filename})

            return _json_success(message="图片已删除")

        finally:
            db.close()

    except Exception as e:
        logger.error(f"删除图片失败: {e}", exc_info=True)
        return _json_error("删除图片失败", 500)


@admin_bp.route("/images", methods=["DELETE"])
@admin_required
def bulk_delete_images():
    """
    批量删除图片

    Request Body:
        {
            "ids": [1, 2, 3]
        }
    """
    try:
        data = request.get_json() or {}
        ids = data.get("ids", [])
        if not ids:
            return _json_error("缺少 ids 参数")

        db = get_db()
        try:
            # 获取要删除的图片信息
            images = db.query(ImageFile).filter(ImageFile.id.in_(ids)).all()

            # 删除物理文件
            for image in images:
                file_path = Path(Config.OUTPUT_DIR) / image.filename
                if file_path.exists():
                    try:
                        file_path.unlink()
                    except Exception as e:
                        logger.warning(f"删除文件失败: {file_path}, {e}")

            # 删除数据库记录
            deleted = db.query(ImageFile).filter(
                ImageFile.id.in_(ids)
            ).delete(synchronize_session=False)
            db.commit()

            # 记录审计日志
            _audit_log("bulk_delete_images", "image_file", details={"ids": ids, "deleted": deleted})

            return _json_success(deleted=deleted)

        finally:
            db.close()

    except Exception as e:
        logger.error(f"批量删除图片失败: {e}", exc_info=True)
        return _json_error("批量删除图片失败", 500)


# ============================================================================
# 配置文件管理（image_providers.yaml）
# ============================================================================

def _get_config_path() -> Path:
    """获取配置文件路径"""
    return Path(__file__).parent.parent.parent / "image_providers.yaml"


def _get_next_version(config_name: str, db) -> int:
    """获取下一个版本号"""
    last = db.query(ConfigVersion).filter(
        ConfigVersion.config_name == config_name
    ).order_by(ConfigVersion.version.desc()).first()
    return 1 if not last else last.version + 1


@admin_bp.route("/config/image-providers", methods=["GET"])
@admin_required
def get_image_providers():
    """获取图片服务商配置"""
    try:
        config_path = _get_config_path()
        if not config_path.exists():
            return _json_error("配置文件不存在", 404)

        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()

        try:
            parsed = yaml.safe_load(content) if content else {}
        except yaml.YAMLError:
            parsed = None

        return _json_success(data={
            "content": content,
            "parsed": parsed,
        })

    except Exception as e:
        logger.error(f"获取配置失败: {e}", exc_info=True)
        return _json_error("获取配置失败", 500)


@admin_bp.route("/config/image-providers", methods=["PUT"])
@admin_required
def update_image_providers():
    """
    更新图片服务商配置

    Request Body:
        {
            "content": "YAML 配置内容",
            "diff_summary": "变更摘要（可选）"
        }
    """
    try:
        data = request.get_json() or {}
        content = data.get("content")
        if content is None:
            return _json_error("缺少 content 参数")

        # YAML 语法验证
        try:
            parsed = yaml.safe_load(io.StringIO(content)) or {}
        except yaml.YAMLError as e:
            return _json_error(f"YAML 语法错误: {e}")

        # 配置结构验证
        if "providers" not in parsed:
            return _json_error("配置必须包含 providers 字段")

        config_path = _get_config_path()

        db = get_db()
        try:
            # 保存配置文件
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(content)

            # 清除缓存
            Config._image_providers_config = None

            # 记录版本
            user = get_current_user()
            version = _get_next_version("image_providers", db)
            cv = ConfigVersion(
                config_name="image_providers",
                version=version,
                content=content,
                diff_summary=data.get("diff_summary"),
                created_by=user.id if user else None,
            )
            db.add(cv)
            db.commit()

            # 记录审计日志
            _audit_log("update_image_providers", "config", version, {"version": version})

            return _json_success(data={
                "version": version,
                "parsed": parsed,
            })

        finally:
            db.close()

    except Exception as e:
        logger.error(f"更新配置失败: {e}", exc_info=True)
        return _json_error("更新配置失败", 500)


@admin_bp.route("/config/image-providers/history", methods=["GET"])
@admin_required
def image_providers_history():
    """获取配置修改历史"""
    try:
        db = get_db()
        try:
            versions = db.query(ConfigVersion).filter(
                ConfigVersion.config_name == "image_providers"
            ).order_by(ConfigVersion.version.desc()).all()

            return _json_success(data=[
                {
                    "id": v.id,
                    "version": v.version,
                    "diff_summary": v.diff_summary,
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                    "created_by": v.created_by,
                }
                for v in versions
            ])
        finally:
            db.close()

    except Exception as e:
        logger.error(f"获取配置历史失败: {e}", exc_info=True)
        return _json_error("获取配置历史失败", 500)


@admin_bp.route("/config/image-providers/history/<int:version>", methods=["GET"])
@admin_required
def get_image_providers_version(version: int):
    """获取指定版本的配置"""
    try:
        db = get_db()
        try:
            cv = db.query(ConfigVersion).filter(
                ConfigVersion.config_name == "image_providers",
                ConfigVersion.version == version
            ).first()

            if not cv:
                return _json_error("版本不存在", 404)

            return _json_success(data={
                "id": cv.id,
                "version": cv.version,
                "content": cv.content,
                "diff_summary": cv.diff_summary,
                "created_at": cv.created_at.isoformat() if cv.created_at else None,
                "created_by": cv.created_by,
            })
        finally:
            db.close()

    except Exception as e:
        logger.error(f"获取配置版本失败: {e}", exc_info=True)
        return _json_error("获取配置版本失败", 500)


@admin_bp.route("/config/image-providers/rollback/<int:version>", methods=["POST"])
@admin_required
def rollback_image_providers(version: int):
    """回滚到指定版本"""
    try:
        db = get_db()
        try:
            cv = db.query(ConfigVersion).filter(
                ConfigVersion.config_name == "image_providers",
                ConfigVersion.version == version
            ).first()

            if not cv:
                return _json_error("版本不存在", 404)

            # 保存配置文件
            config_path = _get_config_path()
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(cv.content)

            # 清除缓存
            Config._image_providers_config = None

            # 创建新版本记录
            user = get_current_user()
            new_version = _get_next_version("image_providers", db)
            new_cv = ConfigVersion(
                config_name="image_providers",
                version=new_version,
                content=cv.content,
                diff_summary=f"回滚到版本 {version}",
                created_by=user.id if user else None,
            )
            db.add(new_cv)
            db.commit()

            # 记录审计日志
            _audit_log(
                "rollback_image_providers",
                "config",
                new_version,
                {"rolled_back_to": version}
            )

            return _json_success(data={
                "rolled_back_to": version,
                "new_version": new_version,
            })

        finally:
            db.close()

    except Exception as e:
        logger.error(f"回滚配置失败: {e}", exc_info=True)
        return _json_error("回滚配置失败", 500)


# ============================================================================
# 注册开关管理
# ============================================================================

def _get_registration_setting(db) -> RegistrationSetting:
    """获取或创建注册配置"""
    setting = db.query(RegistrationSetting).filter(RegistrationSetting.id == 1).first()
    if not setting:
        setting = RegistrationSetting(id=1)
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


def _registration_to_dict(setting: RegistrationSetting) -> dict:
    """将注册配置转换为字典"""
    return {
        "id": setting.id,
        "enabled": setting.enabled,
        "default_role": setting.default_role,
        "invite_required": setting.invite_required,
        "invite_code": setting.invite_code,
        "email_verification_required": setting.email_verification_required,
        "rate_limit_per_hour": setting.rate_limit_per_hour,
        "updated_at": setting.updated_at.isoformat() if setting.updated_at else None,
        "updated_by": setting.updated_by,
    }


@admin_bp.route("/registration", methods=["GET"])
@admin_required
def get_registration():
    """获取注册配置"""
    try:
        db = get_db()
        try:
            setting = _get_registration_setting(db)
            return _json_success(data=_registration_to_dict(setting))
        finally:
            db.close()

    except Exception as e:
        logger.error(f"获取注册配置失败: {e}", exc_info=True)
        return _json_error("获取注册配置失败", 500)


@admin_bp.route("/registration", methods=["PUT"])
@admin_required
def update_registration():
    """
    更新注册配置

    Request Body:
        {
            "enabled": true/false,
            "default_role": "user",
            "invite_required": false,
            "invite_code": "xxx",
            "email_verification_required": false,
            "rate_limit_per_hour": 0
        }
    """
    try:
        data = request.get_json() or {}

        db = get_db()
        try:
            setting = _get_registration_setting(db)
            user = get_current_user()

            # 更新字段
            changes = {}
            for field in ["enabled", "default_role", "invite_required", "invite_code",
                          "email_verification_required", "rate_limit_per_hour"]:
                if field in data and hasattr(setting, field):
                    old_value = getattr(setting, field)
                    new_value = data[field]
                    if old_value != new_value:
                        setattr(setting, field, new_value)
                        changes[field] = {"old": old_value, "new": new_value}

            setting.updated_by = user.id if user else None
            db.commit()
            db.refresh(setting)

            # 记录版本
            if changes:
                version = _get_next_version("registration", db)
                cv = ConfigVersion(
                    config_name="registration",
                    version=version,
                    content=yaml.safe_dump(_registration_to_dict(setting), allow_unicode=True),
                    diff_summary=str(changes),
                    created_by=user.id if user else None,
                )
                db.add(cv)
                db.commit()

                # 记录审计日志
                _audit_log("update_registration", "config", version, changes)

            return _json_success(data=_registration_to_dict(setting))

        finally:
            db.close()

    except Exception as e:
        logger.error(f"更新注册配置失败: {e}", exc_info=True)
        return _json_error("更新注册配置失败", 500)


@admin_bp.route("/registration/history", methods=["GET"])
@admin_required
def registration_history():
    """获取注册配置变更历史"""
    try:
        db = get_db()
        try:
            versions = db.query(ConfigVersion).filter(
                ConfigVersion.config_name == "registration"
            ).order_by(ConfigVersion.version.desc()).all()

            return _json_success(data=[
                {
                    "id": v.id,
                    "version": v.version,
                    "diff_summary": v.diff_summary,
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                    "created_by": v.created_by,
                }
                for v in versions
            ])
        finally:
            db.close()

    except Exception as e:
        logger.error(f"获取注册配置历史失败: {e}", exc_info=True)
        return _json_error("获取注册配置历史失败", 500)


# ============================================================================
# 审计日志
# ============================================================================

@admin_bp.route("/audit-logs", methods=["GET"])
@admin_required
def list_audit_logs():
    """
    获取审计日志列表（分页）

    Query Parameters:
        page: 页码
        page_size: 每页数量
        actor_id: 操作者 ID 筛选
        action: 操作类型筛选
        resource_type: 资源类型筛选
        start_at: 开始时间
        end_at: 结束时间
    """
    try:
        page, page_size = _get_pagination_params()

        db = get_db()
        try:
            query = db.query(AuditLog)

            # 筛选条件
            if actor_id := request.args.get("actor_id"):
                query = query.filter(AuditLog.actor_id == int(actor_id))
            if action := request.args.get("action"):
                query = query.filter(AuditLog.action == action)
            if resource_type := request.args.get("resource_type"):
                query = query.filter(AuditLog.resource_type == resource_type)
            if start_at := request.args.get("start_at"):
                query = query.filter(AuditLog.created_at >= start_at)
            if end_at := request.args.get("end_at"):
                query = query.filter(AuditLog.created_at <= end_at)

            # 排序（默认按时间降序）
            query = query.order_by(AuditLog.created_at.desc())

            # 统计总数
            total = query.count()

            # 分页
            offset = (page - 1) * page_size
            logs = query.offset(offset).limit(page_size).all()

            return _json_success(
                data=[
                    {
                        "id": log.id,
                        "actor_id": log.actor_id,
                        "actor_username": log.actor_username,
                        "action": log.action,
                        "resource_type": log.resource_type,
                        "resource_id": log.resource_id,
                        "details": log.details,
                        "ip_address": log.ip_address,
                        "created_at": log.created_at.isoformat() if log.created_at else None,
                    }
                    for log in logs
                ],
                page=page,
                page_size=page_size,
                total=total,
            )
        finally:
            db.close()

    except Exception as e:
        logger.error(f"获取审计日志失败: {e}", exc_info=True)
        return _json_error("获取审计日志失败", 500)


# ============================================================================
# 仪表盘统计
# ============================================================================

@admin_bp.route("/dashboard/stats", methods=["GET"])
@admin_required
def dashboard_stats():
    """获取仪表盘统计数据"""
    try:
        db = get_db()
        try:
            # 用户统计
            total_users = db.query(User).count()
            active_users = db.query(User).filter(User.is_active == True).count()

            # 记录统计
            total_records = db.query(HistoryRecord).count()
            completed_records = db.query(HistoryRecord).filter(
                HistoryRecord.status == "completed"
            ).count()

            # 图片统计
            total_images = db.query(ImageFile).count()
            total_size = db.query(func.coalesce(func.sum(ImageFile.file_size), 0)).scalar()

            return _json_success(data={
                "users": {
                    "total": total_users,
                    "active": active_users,
                },
                "records": {
                    "total": total_records,
                    "completed": completed_records,
                },
                "images": {
                    "total": total_images,
                    "size_bytes": total_size,
                    "size_mb": round(total_size / (1024 * 1024), 2) if total_size else 0,
                },
            })
        finally:
            db.close()

    except Exception as e:
        logger.error(f"获取仪表盘统计失败: {e}", exc_info=True)
        return _json_error("获取仪表盘统计失败", 500)
