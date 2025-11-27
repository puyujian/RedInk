"""
认证相关 API 路由

提供用户注册、登录、刷新 token、登出等功能
"""
import logging
import uuid
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, make_response

from backend.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    save_refresh_token,
    verify_refresh_token,
    revoke_refresh_token,
    revoke_all_user_tokens,
    login_required,
    get_current_user,
)
from backend.db import get_db
from backend.models import User, HistoryRecord, RegistrationSetting

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


# ============================================================================
# 用户注册
# ============================================================================

@auth_bp.route('/register', methods=['POST'])
def register():
    """
    用户注册

    请求体:
        {
            "username": "用户名",
            "email": "邮箱（可选）",
            "password": "密码",
            "client_id": "前端匿名 UUID（可选，用于绑定历史数据）",
            "invite_code": "邀请码（如果需要）"
        }

    响应:
        {
            "success": true,
            "user": {
                "id": 1,
                "uuid": "...",
                "username": "...",
                "role": "user"
            },
            "access_token": "...",
            "refresh_token": "..."  # 也会通过 HttpOnly Cookie 返回
        }
    """
    try:
        data = request.get_json() or {}
        username = (data.get('username') or '').strip()
        email = (data.get('email') or '').strip() or None
        password = data.get('password') or ''
        client_id = data.get('client_id') or request.headers.get('X-User-Id')
        invite_code = (data.get('invite_code') or '').strip()

        db = get_db()
        try:
            # 检查注册配置
            reg_setting = db.query(RegistrationSetting).filter(RegistrationSetting.id == 1).first()
            if reg_setting:
                # 检查注册是否开启
                if not reg_setting.enabled:
                    return jsonify({
                        'success': False,
                        'error': '注册功能已关闭'
                    }), 403

                # 检查邀请码
                if reg_setting.invite_required:
                    if not invite_code:
                        return jsonify({
                            'success': False,
                            'error': '需要邀请码才能注册'
                        }), 400
                    if reg_setting.invite_code and invite_code != reg_setting.invite_code:
                        return jsonify({
                            'success': False,
                            'error': '邀请码无效'
                        }), 400

            # 验证输入
            if not username:
                return jsonify({
                    'success': False,
                    'error': '用户名不能为空'
                }), 400

            if len(username) < 3 or len(username) > 50:
                return jsonify({
                    'success': False,
                    'error': '用户名长度必须在 3-50 个字符之间'
                }), 400

            if not password:
                return jsonify({
                    'success': False,
                    'error': '密码不能为空'
                }), 400

            if len(password) < 6:
                return jsonify({
                    'success': False,
                    'error': '密码长度至少为 6 个字符'
                }), 400

            # 检查用户名是否已存在
            existing_user = db.query(User).filter(User.username == username).first()
            if existing_user:
                return jsonify({
                    'success': False,
                    'error': '用户名已被使用'
                }), 400

            # 检查邮箱是否已存在
            if email:
                existing_email = db.query(User).filter(User.email == email).first()
                if existing_email:
                    return jsonify({
                        'success': False,
                        'error': '邮箱已被使用'
                    }), 400

            # 确定用户角色
            default_role = reg_setting.default_role if reg_setting else 'user'

            # 创建用户
            user = User(
                username=username,
                email=email,
                password_hash=hash_password(password),
                role=default_role,
                client_id=client_id,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            # 如果提供了 client_id，迁移历史记录
            if client_id:
                migrated_count = db.query(HistoryRecord).filter(
                    HistoryRecord.client_id == client_id,
                    HistoryRecord.user_id.is_(None)
                ).update({'user_id': user.id})
                db.commit()
                logger.info(f"用户 {user.id} 注册时迁移了 {migrated_count} 条历史记录")

            # 生成 tokens
            jti = str(uuid.uuid4())
            access_token = create_access_token(user)
            refresh_token = create_refresh_token(user, jti)

            # 保存 refresh token
            user_agent = request.headers.get('User-Agent')
            ip_address = request.remote_addr
            save_refresh_token(user.id, jti, refresh_token, user_agent, ip_address)

            # 构造响应
            response_data = {
                'success': True,
                'user': {
                    'id': user.id,
                    'uuid': user.uuid,
                    'username': user.username,
                    'email': user.email,
                    'role': user.role,
                },
                'access_token': access_token,
                'refresh_token': refresh_token,  # 前端可选存储
            }

            # 通过 HttpOnly Cookie 返回 refresh token（更安全）
            response = make_response(jsonify(response_data), 201)
            response.set_cookie(
                'refresh_token',
                refresh_token,
                httponly=True,
                secure=False,  # 生产环境应设为 True（需要 HTTPS）
                samesite='Lax',
                max_age=604800,  # 7 天
            )

            return response

        finally:
            db.close()

    except Exception as e:
        logger.error(f"注册失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': '注册失败，请稍后重试'
        }), 500


# ============================================================================
# 用户登录
# ============================================================================

@auth_bp.route('/login', methods=['POST'])
def login():
    """
    用户登录

    请求体:
        {
            "username": "用户名或邮箱",
            "password": "密码"
        }

    响应:
        {
            "success": true,
            "user": {...},
            "access_token": "...",
            "refresh_token": "..."
        }
    """
    try:
        data = request.get_json() or {}
        username_or_email = (data.get('username') or '').strip()
        password = data.get('password') or ''

        if not username_or_email or not password:
            return jsonify({
                'success': False,
                'error': '用户名和密码不能为空'
            }), 400

        db = get_db()
        try:
            # 查找用户（支持用户名或邮箱登录）
            user = db.query(User).filter(
                (User.username == username_or_email) | (User.email == username_or_email)
            ).first()

            if not user:
                return jsonify({
                    'success': False,
                    'error': '用户名或密码错误'
                }), 401

            # 验证密码
            if not verify_password(password, user.password_hash):
                return jsonify({
                    'success': False,
                    'error': '用户名或密码错误'
                }), 401

            # 检查账号是否激活
            if not user.is_active:
                return jsonify({
                    'success': False,
                    'error': '账号已被禁用'
                }), 403

            # 更新最后登录时间
            user.last_login_at = datetime.now(timezone.utc)
            db.commit()

            # 生成 tokens
            jti = str(uuid.uuid4())
            access_token = create_access_token(user)
            refresh_token = create_refresh_token(user, jti)

            # 保存 refresh token
            user_agent = request.headers.get('User-Agent')
            ip_address = request.remote_addr
            save_refresh_token(user.id, jti, refresh_token, user_agent, ip_address)

            # 构造响应
            response_data = {
                'success': True,
                'user': {
                    'id': user.id,
                    'uuid': user.uuid,
                    'username': user.username,
                    'email': user.email,
                    'role': user.role,
                },
                'access_token': access_token,
                'refresh_token': refresh_token,
            }

            # 通过 HttpOnly Cookie 返回 refresh token
            response = make_response(jsonify(response_data), 200)
            response.set_cookie(
                'refresh_token',
                refresh_token,
                httponly=True,
                secure=False,
                samesite='Lax',
                max_age=604800,
            )

            return response

        finally:
            db.close()

    except Exception as e:
        logger.error(f"登录失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': '登录失败，请稍后重试'
        }), 500


# ============================================================================
# 刷新 Token
# ============================================================================

@auth_bp.route('/refresh', methods=['POST'])
def refresh():
    """
    刷新 access token

    从 Cookie 或请求体中获取 refresh token

    响应:
        {
            "success": true,
            "access_token": "..."
        }
    """
    try:
        # 优先从 Cookie 获取
        refresh_token = request.cookies.get('refresh_token')

        # 其次从请求体获取
        if not refresh_token:
            data = request.get_json() or {}
            refresh_token = data.get('refresh_token')

        if not refresh_token:
            return jsonify({
                'success': False,
                'error': '缺少 refresh token'
            }), 400

        # 验证 refresh token
        token_record = verify_refresh_token(refresh_token)
        if not token_record:
            return jsonify({
                'success': False,
                'error': 'refresh token 无效或已过期'
            }), 401

        # 加载用户
        db = get_db()
        try:
            user = db.query(User).filter(
                User.id == token_record.user_id,
                User.is_active == True
            ).first()

            if not user:
                return jsonify({
                    'success': False,
                    'error': '用户不存在或已被禁用'
                }), 401

            # 生成新的 access token
            access_token = create_access_token(user)

            return jsonify({
                'success': True,
                'access_token': access_token,
            }), 200

        finally:
            db.close()

    except Exception as e:
        logger.error(f"刷新 token 失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': '刷新 token 失败'
        }), 500


# ============================================================================
# 登出
# ============================================================================

@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """
    用户登出（撤销当前 refresh token）

    响应:
        {
            "success": true,
            "message": "登出成功"
        }
    """
    try:
        # 从 Cookie 或请求体获取 refresh token
        refresh_token = request.cookies.get('refresh_token')
        if not refresh_token:
            data = request.get_json() or {}
            refresh_token = data.get('refresh_token')

        if refresh_token:
            payload = decode_token(refresh_token)
            if payload and payload.get('type') == 'refresh':
                jti = payload.get('jti')
                if jti:
                    revoke_refresh_token(jti)

        # 清除 Cookie
        response = make_response(jsonify({
            'success': True,
            'message': '登出成功'
        }), 200)
        response.set_cookie('refresh_token', '', expires=0)

        return response

    except Exception as e:
        logger.error(f"登出失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': '登出失败'
        }), 500


@auth_bp.route('/logout-all', methods=['POST'])
@login_required
def logout_all():
    """
    强制下线所有设备（撤销用户的所有 refresh token）

    响应:
        {
            "success": true,
            "message": "已强制下线所有设备",
            "count": 3
        }
    """
    try:
        user = get_current_user()
        count = revoke_all_user_tokens(user.id)

        # 清除 Cookie
        response = make_response(jsonify({
            'success': True,
            'message': '已强制下线所有设备',
            'count': count
        }), 200)
        response.set_cookie('refresh_token', '', expires=0)

        return response

    except Exception as e:
        logger.error(f"强制下线失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': '操作失败'
        }), 500


# ============================================================================
# 获取当前用户信息
# ============================================================================

@auth_bp.route('/me', methods=['GET'])
@login_required
def get_me():
    """
    获取当前登录用户信息

    响应:
        {
            "success": true,
            "user": {
                "id": 1,
                "uuid": "...",
                "username": "...",
                "email": "...",
                "role": "user",
                "created_at": "...",
                "last_login_at": "..."
            }
        }
    """
    try:
        user = get_current_user()
        return jsonify({
            'success': True,
            'user': {
                'id': user.id,
                'uuid': user.uuid,
                'username': user.username,
                'email': user.email,
                'role': user.role,
                'is_active': user.is_active,
                'created_at': user.created_at.isoformat() if user.created_at else None,
                'last_login_at': user.last_login_at.isoformat() if user.last_login_at else None,
            }
        }), 200

    except Exception as e:
        logger.error(f"获取用户信息失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': '获取用户信息失败'
        }), 500
