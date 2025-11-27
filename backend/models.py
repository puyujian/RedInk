"""
数据库模型定义

包含用户、历史记录、图片文件、用量统计、权限系统等表
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import relationship, Mapped, mapped_column

from backend.db import Base


# ============================================================================
# 用户与认证
# ============================================================================

class User(Base):
    """用户表"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(
        sa.String(36),
        nullable=False,
        unique=True,
        default=lambda: str(uuid.uuid4()),
        comment="对外暴露的用户 UUID"
    )
    username: Mapped[str] = mapped_column(
        sa.String(50),
        nullable=False,
        unique=True,
        index=True,
        comment="用户名"
    )
    email: Mapped[Optional[str]] = mapped_column(
        sa.String(255),
        unique=True,
        index=True,
        comment="邮箱地址"
    )
    password_hash: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
        comment="bcrypt 加密的密码"
    )
    role: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default="user",
        comment="用户角色（user/admin/pro）"
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=True,
        comment="账号是否激活"
    )
    client_id: Mapped[Optional[str]] = mapped_column(
        sa.String(36),
        unique=True,
        index=True,
        comment="绑定的前端匿名 UUID（用于迁移历史数据）"
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        comment="更新时间"
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True),
        comment="最后登录时间"
    )

    # 关系
    history_records = relationship("HistoryRecord", back_populates="user", cascade="all, delete-orphan")
    image_files = relationship("ImageFile", back_populates="user", cascade="all, delete-orphan")
    usage_events = relationship("UsageEvent", back_populates="user", cascade="all, delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"


class RefreshToken(Base):
    """Refresh Token 表（用于 JWT 刷新和登出管理）"""
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="用户 ID"
    )
    jti: Mapped[str] = mapped_column(
        sa.String(36),
        nullable=False,
        unique=True,
        index=True,
        comment="JWT ID（唯一标识）"
    )
    token_hash: Mapped[str] = mapped_column(
        sa.String(128),
        nullable=False,
        comment="Token 的哈希值（不存储明文）"
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        sa.String(255),
        comment="用户代理"
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        sa.String(45),
        comment="IP 地址"
    )
    expires_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="过期时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        comment="创建时间"
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True),
        comment="撤销时间（登出时设置）"
    )

    # 关系
    user = relationship("User", back_populates="refresh_tokens")

    def __repr__(self) -> str:
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, jti='{self.jti}')>"


# ============================================================================
# 历史记录与图片
# ============================================================================

class HistoryRecord(Base):
    """历史记录表"""
    __tablename__ = "history_records"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    record_uuid: Mapped[str] = mapped_column(
        sa.String(36),
        nullable=False,
        unique=True,
        index=True,
        comment="记录 UUID（兼容旧 JSON 文件）"
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        comment="用户 ID（NULL 表示遗留数据）"
    )
    client_id: Mapped[Optional[str]] = mapped_column(
        sa.String(36),
        index=True,
        comment="匿名用户 ID（用于绑定迁移）"
    )
    title: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
        comment="标题（用户主题）"
    )
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default="draft",
        index=True,
        comment="状态（draft/generating/completed/partial）"
    )
    thumbnail_url: Mapped[Optional[str]] = mapped_column(
        sa.String(255),
        comment="缩略图 URL"
    )
    page_count: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        comment="页面数量"
    )
    outline_raw: Mapped[Optional[str]] = mapped_column(
        sa.Text,
        comment="原始大纲文本"
    )
    outline_json: Mapped[Optional[dict]] = mapped_column(
        sa.JSON,
        comment="结构化大纲数据"
    )
    images_json: Mapped[Optional[dict]] = mapped_column(
        sa.JSON,
        comment="图片数据（task_id, generated 等）"
    )
    image_task_id: Mapped[Optional[str]] = mapped_column(
        sa.String(64),
        index=True,
        comment="关联的图片生成任务 ID"
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        index=True,
        comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        comment="更新时间"
    )

    # 关系
    user = relationship("User", back_populates="history_records")
    image_files = relationship("ImageFile", back_populates="record", cascade="all, delete-orphan")

    # 复合索引
    __table_args__ = (
        sa.Index("idx_history_user_created", "user_id", "created_at"),
        sa.Index("idx_history_user_status", "user_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<HistoryRecord(id={self.id}, title='{self.title}', status='{self.status}')>"


class ImageFile(Base):
    """图片文件表（用于权限控制和计费统计）"""
    __tablename__ = "image_files"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="用户 ID"
    )
    record_id: Mapped[Optional[int]] = mapped_column(
        sa.Integer,
        sa.ForeignKey("history_records.id", ondelete="CASCADE"),
        index=True,
        comment="关联的历史记录 ID"
    )
    task_id: Mapped[Optional[str]] = mapped_column(
        sa.String(64),
        index=True,
        comment="图片生成任务 ID"
    )
    filename: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
        unique=True,
        index=True,
        comment="文件名（相对于 output 目录）"
    )
    file_size: Mapped[Optional[int]] = mapped_column(
        sa.Integer,
        comment="文件大小（字节）"
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        index=True,
        comment="创建时间"
    )

    # 关系
    user = relationship("User", back_populates="image_files")
    record = relationship("HistoryRecord", back_populates="image_files")

    # 复合索引
    __table_args__ = (
        sa.Index("idx_image_files_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ImageFile(id={self.id}, filename='{self.filename}', user_id={self.user_id})>"


# ============================================================================
# 用量统计与计费
# ============================================================================

class UsageEvent(Base):
    """用量事件表（细粒度日志，用于计费）"""
    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="用户 ID"
    )
    event_type: Mapped[str] = mapped_column(
        sa.String(50),
        nullable=False,
        index=True,
        comment="事件类型（outline.generate/image.generate/api.call）"
    )
    amount: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=1,
        comment="数量（如生成图片张数）"
    )
    meta: Mapped[Optional[dict]] = mapped_column(
        sa.JSON,
        comment="元数据（模型名、prompt 长度等）"
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        index=True,
        comment="创建时间"
    )

    # 关系
    user = relationship("User", back_populates="usage_events")

    # 复合索引
    __table_args__ = (
        sa.Index("idx_usage_user_time", "user_id", "created_at"),
        sa.Index("idx_usage_type_time", "event_type", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<UsageEvent(id={self.id}, user_id={self.user_id}, type='{self.event_type}', amount={self.amount})>"


# ============================================================================
# RBAC 权限系统（预留）
# ============================================================================

class Role(Base):
    """角色表"""
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        sa.String(50),
        nullable=False,
        unique=True,
        comment="角色名称（admin/user/pro）"
    )
    description: Mapped[Optional[str]] = mapped_column(
        sa.Text,
        comment="角色描述"
    )

    # 关系
    permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Role(id={self.id}, name='{self.name}')>"


class Permission(Base):
    """权限表"""
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(
        sa.String(100),
        nullable=False,
        unique=True,
        comment="权限代码（history.read/billing.view）"
    )
    name: Mapped[str] = mapped_column(
        sa.String(100),
        nullable=False,
        comment="权限名称"
    )
    description: Mapped[Optional[str]] = mapped_column(
        sa.Text,
        comment="权限描述"
    )

    # 关系
    roles = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Permission(id={self.id}, code='{self.code}')>"


class RolePermission(Base):
    """角色-权限关联表"""
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True
    )
    permission_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True
    )

    # 关系
    role = relationship("Role", back_populates="permissions")
    permission = relationship("Permission", back_populates="roles")

    def __repr__(self) -> str:
        return f"<RolePermission(role_id={self.role_id}, permission_id={self.permission_id})>"


# ============================================================================
# 后台管理系统模型
# ============================================================================

class ConfigVersion(Base):
    """配置版本历史表"""
    __tablename__ = "config_versions"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    config_name: Mapped[str] = mapped_column(
        sa.String(128),
        nullable=False,
        index=True,
        comment="配置名称（如 image_providers, registration）"
    )
    version: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        comment="版本号"
    )
    content: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        comment="配置内容（YAML 或 JSON 文本）"
    )
    diff_summary: Mapped[Optional[str]] = mapped_column(
        sa.Text,
        comment="变更摘要"
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        comment="创建时间"
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        comment="创建者用户 ID"
    )

    # 唯一约束：同一配置名下版本号唯一
    __table_args__ = (
        sa.UniqueConstraint("config_name", "version", name="uq_config_name_version"),
        sa.Index("idx_config_versions_name_version", "config_name", "version"),
    )

    def __repr__(self) -> str:
        return f"<ConfigVersion(config_name='{self.config_name}', version={self.version})>"


class RegistrationSetting(Base):
    """注册配置表（单行配置）"""
    __tablename__ = "registration_settings"

    id: Mapped[int] = mapped_column(
        sa.Integer,
        primary_key=True,
        default=1,
        comment="固定为 1（单行配置）"
    )
    enabled: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=True,
        comment="是否启用注册"
    )
    default_role: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        default="user",
        comment="新用户默认角色"
    )
    invite_required: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=False,
        comment="是否需要邀请码"
    )
    invite_code: Mapped[Optional[str]] = mapped_column(
        sa.String(128),
        comment="有效的邀请码（为空表示不限制）"
    )
    email_verification_required: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=False,
        comment="是否需要邮箱验证"
    )
    rate_limit_per_hour: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        comment="每小时注册限制（0 表示不限制）"
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        comment="更新时间"
    )
    updated_by: Mapped[Optional[int]] = mapped_column(
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        comment="更新者用户 ID"
    )

    def __repr__(self) -> str:
        return f"<RegistrationSetting(enabled={self.enabled}, invite_required={self.invite_required})>"


class AuditLog(Base):
    """审计日志表"""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[Optional[int]] = mapped_column(
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        comment="操作者用户 ID"
    )
    actor_username: Mapped[Optional[str]] = mapped_column(
        sa.String(128),
        comment="操作者用户名（冗余存储，防止用户删除后丢失）"
    )
    action: Mapped[str] = mapped_column(
        sa.String(128),
        nullable=False,
        index=True,
        comment="操作类型（如 create_user, update_config）"
    )
    resource_type: Mapped[str] = mapped_column(
        sa.String(128),
        nullable=False,
        index=True,
        comment="资源类型（如 user, config, history_record）"
    )
    resource_id: Mapped[Optional[str]] = mapped_column(
        sa.String(128),
        comment="资源 ID"
    )
    details: Mapped[Optional[dict]] = mapped_column(
        sa.JSON,
        comment="操作详情（JSON 格式）"
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        sa.String(64),
        comment="操作者 IP 地址"
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        index=True,
        comment="操作时间"
    )

    # 复合索引
    __table_args__ = (
        sa.Index("idx_audit_logs_actor_created", "actor_id", "created_at"),
        sa.Index("idx_audit_logs_action_created", "action", "created_at"),
        sa.Index("idx_audit_logs_resource", "resource_type", "resource_id"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action='{self.action}', resource='{self.resource_type}')>"
