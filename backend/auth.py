"""
JWT 认证工具和中间件

提供 token 生成、验证、用户加载等功能
"""
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Optional, Dict, Any

import bcrypt
import jwt
from flask import request, g, jsonify

from backend.config import Config
from backend.db import get_db
from backend.models import User, RefreshToken

logger = logging.getLogger(__name__)


# ============================================================================
# 密码加密
# ============================================================================

def hash_password(password: str) -> str:
    """
    使用 bcrypt 加密密码

    Args:
        password: 明文密码

    Returns:
        str: 加密后的密码哈希
    """
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """
    验证密码是否正确

    Args:
        password: 明文密码
        password_hash: 加密后的密码哈希

    Returns:
        bool: 密码是否匹配
    """
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except Exception as e:
        logger.error(f"密码验证失败: {e}")
        return False


# ============================================================================
# JWT Token 生成与验证
# ============================================================================

def create_access_token(user: User) -> str:
    """
    创建 access token

    Args:
        user: 用户对象

    Returns:
        str: JWT access token
    """
    now = datetime.now(timezone.utc)
    payload = {
        'sub': str(user.id),
        'uuid': user.uuid,
        'username': user.username,
        'role': user.role,
        'type': 'access',
        'iat': int(now.timestamp()),
        'exp': int((now + timedelta(seconds=Config.JWT_ACCESS_EXPIRES)).timestamp()),
    }
    return jwt.encode(payload, Config.JWT_SECRET_KEY, algorithm='HS256')


def create_refresh_token(user: User, jti: str) -> str:
    """
    创建 refresh token

    Args:
        user: 用户对象
        jti: JWT ID（唯一标识）

    Returns:
        str: JWT refresh token
    """
    now = datetime.now(timezone.utc)
    payload = {
        'sub': str(user.id),
        'jti': jti,
        'type': 'refresh',
        'iat': int(now.timestamp()),
        'exp': int((now + timedelta(seconds=Config.JWT_REFRESH_EXPIRES)).timestamp()),
    }
    return jwt.encode(payload, Config.JWT_SECRET_KEY, algorithm='HS256')


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    解码并验证 JWT token

    Args:
        token: JWT token 字符串

    Returns:
        Optional[Dict]: token payload，验证失败返回 None
    """
    try:
        payload = jwt.decode(
            token,
            Config.JWT_SECRET_KEY,
            algorithms=['HS256']
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token 已过期")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"无效的 token: {e}")
        return None


def hash_token(token: str) -> str:
    """
    对 token 进行哈希（用于存储 refresh token）

    Args:
        token: token 字符串

    Returns:
        str: SHA256 哈希值
    """
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


# ============================================================================
# 用户加载
# ============================================================================

def load_current_user() -> Optional[User]:
    """
    从请求中加载当前用户

    优先级：
    1. Authorization 头中的 JWT token
    2. 查询参数中的 token（用于 SSE 连接，因为 EventSource 不支持自定义头）
    3. X-User-Id 头中的匿名 UUID（向后兼容）

    Returns:
        Optional[User]: 当前用户对象，未登录返回 None
    """
    token = None
    
    # 尝试从 Authorization 头获取 JWT token
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
    
    # 如果 Authorization 头中没有 token，尝试从查询参数获取（用于 SSE）
    if not token:
        token = request.args.get('token', '').strip()
    
    # 验证 token 并加载用户
    if token:
        payload = decode_token(token)

        if payload and payload.get('type') == 'access':
            user_id = payload.get('sub')
            if user_id:
                db = get_db()
                try:
                    user = db.query(User).filter(
                        User.id == int(user_id),
                        User.is_active == True
                    ).first()
                    return user
                except Exception as e:
                    logger.error(f"加载用户失败: {e}")
                finally:
                    db.close()

    # 向后兼容：从 X-User-Id 获取匿名 UUID
    client_id = request.headers.get('X-User-Id', '').strip()
    if client_id:
        g.client_id = client_id

    return None


def get_current_user() -> Optional[User]:
    """
    获取当前请求的用户对象

    Returns:
        Optional[User]: 当前用户，未登录返回 None
    """
    if not hasattr(g, 'current_user'):
        g.current_user = load_current_user()
    return g.current_user


def get_client_id() -> str:
    """
    获取客户端 ID（匿名 UUID 或用户绑定的 client_id）

    Returns:
        str: 客户端 ID
    """
    # 优先使用已登录用户的 client_id
    user = get_current_user()
    if user and user.client_id:
        return user.client_id

    # 其次使用请求头中的 X-User-Id
    if hasattr(g, 'client_id'):
        return g.client_id

    # 最后尝试从查询参数获取（SSE 请求）
    return request.args.get('user_id', '').strip()


# ============================================================================
# 装饰器
# ============================================================================

def login_required(f):
    """
    要求用户必须登录的装饰器

    使用示例:
        @app.route('/api/profile')
        @login_required
        def get_profile():
            user = get_current_user()
            return jsonify({'username': user.username})
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if user is None:
            return jsonify({
                'success': False,
                'error': '需要登录才能访问此资源'
            }), 401
        return f(*args, **kwargs)
    return decorated_function


def optional_user(f):
    """
    可选登录的装饰器（支持匿名访问）

    使用示例:
        @app.route('/api/generate')
        @optional_user
        def generate():
            user = get_current_user()
            if user:
                # 已登录用户逻辑
                pass
            else:
                # 匿名用户逻辑
                pass
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 仅加载用户，不强制要求登录
        get_current_user()
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """
    要求管理员权限的装饰器

    使用示例:
        @app.route('/api/admin/users')
        @admin_required
        def list_users():
            # 管理员操作
            pass
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if user is None:
            return jsonify({
                'success': False,
                'error': '需要登录才能访问此资源'
            }), 401
        if user.role != 'admin':
            return jsonify({
                'success': False,
                'error': '需要管理员权限'
            }), 403
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# Refresh Token 管理
# ============================================================================

def save_refresh_token(
    user_id: int,
    jti: str,
    token: str,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None
) -> RefreshToken:
    """
    保存 refresh token 到数据库

    Args:
        user_id: 用户 ID
        jti: JWT ID
        token: refresh token 字符串
        user_agent: 用户代理
        ip_address: IP 地址

    Returns:
        RefreshToken: 保存的 token 记录
    """
    db = get_db()
    try:
        token_hash = hash_token(token)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=Config.JWT_REFRESH_EXPIRES)

        refresh_token = RefreshToken(
            user_id=user_id,
            jti=jti,
            token_hash=token_hash,
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=expires_at
        )
        db.add(refresh_token)
        db.commit()
        db.refresh(refresh_token)
        return refresh_token
    finally:
        db.close()


def verify_refresh_token(token: str) -> Optional[RefreshToken]:
    """
    验证 refresh token 是否有效

    Args:
        token: refresh token 字符串

    Returns:
        Optional[RefreshToken]: token 记录，无效返回 None
    """
    payload = decode_token(token)
    if not payload or payload.get('type') != 'refresh':
        return None

    jti = payload.get('jti')
    if not jti:
        return None

    db = get_db()
    try:
        token_record = db.query(RefreshToken).filter(
            RefreshToken.jti == jti,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(timezone.utc)
        ).first()

        if token_record:
            # 验证 token 哈希
            if token_record.token_hash == hash_token(token):
                return token_record

        return None
    finally:
        db.close()


def revoke_refresh_token(jti: str) -> bool:
    """
    撤销 refresh token（登出）

    Args:
        jti: JWT ID

    Returns:
        bool: 是否成功撤销
    """
    db = get_db()
    try:
        token_record = db.query(RefreshToken).filter(
            RefreshToken.jti == jti
        ).first()

        if token_record:
            token_record.revoked_at = datetime.now(timezone.utc)
            db.commit()
            return True
        return False
    finally:
        db.close()


def revoke_all_user_tokens(user_id: int) -> int:
    """
    撤销用户的所有 refresh token（强制下线）

    Args:
        user_id: 用户 ID

    Returns:
        int: 撤销的 token 数量
    """
    db = get_db()
    try:
        now = datetime.now(timezone.utc)
        count = db.query(RefreshToken).filter(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None)
        ).update({'revoked_at': now})
        db.commit()
        return count
    finally:
        db.close()
