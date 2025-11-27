"""
数据库初始化脚本

用于创建数据库表结构和初始数据
"""
import logging
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.db import init_db, get_db
from backend.models import Role, Permission, RolePermission, User
from backend.auth import hash_password
from backend.config import Config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_default_roles_and_permissions():
    """创建默认角色和权限"""
    db = get_db()
    try:
        # 检查是否已存在角色
        existing_roles = db.query(Role).count()
        if existing_roles > 0:
            logger.info("角色和权限已存在，跳过初始化")
            return

        logger.info("正在创建默认角色和权限...")

        # 创建角色
        roles = {
            'user': Role(name='user', description='普通用户'),
            'pro': Role(name='pro', description='专业版用户'),
            'admin': Role(name='admin', description='管理员'),
        }

        for role in roles.values():
            db.add(role)

        db.commit()

        # 创建权限
        permissions = [
            # 历史记录权限
            Permission(code='history.read', name='查看历史记录', description='查看自己的历史记录'),
            Permission(code='history.write', name='创建历史记录', description='创建新的历史记录'),
            Permission(code='history.update', name='更新历史记录', description='更新自己的历史记录'),
            Permission(code='history.delete', name='删除历史记录', description='删除自己的历史记录'),
            Permission(code='history.read_all', name='查看所有历史记录', description='查看所有用户的历史记录（管理员）'),

            # 生成权限
            Permission(code='generate.outline', name='生成大纲', description='生成内容大纲'),
            Permission(code='generate.image', name='生成图片', description='生成图片'),

            # 用量权限
            Permission(code='usage.view', name='查看用量', description='查看自己的用量统计'),
            Permission(code='usage.view_all', name='查看所有用量', description='查看所有用户的用量统计（管理员）'),

            # 用户管理权限
            Permission(code='user.read', name='查看用户', description='查看用户信息'),
            Permission(code='user.update', name='更新用户', description='更新用户信息'),
            Permission(code='user.delete', name='删除用户', description='删除用户（管理员）'),
            Permission(code='user.manage', name='管理用户', description='管理所有用户（管理员）'),

            # 计费权限（预留）
            Permission(code='billing.view', name='查看计费', description='查看计费信息'),
            Permission(code='billing.manage', name='管理计费', description='管理计费系统（管理员）'),
        ]

        for permission in permissions:
            db.add(permission)

        db.commit()

        # 刷新对象以获取 ID
        for role in roles.values():
            db.refresh(role)
        for permission in permissions:
            db.refresh(permission)

        # 分配权限给角色
        # 普通用户权限
        user_permissions = [
            'history.read', 'history.write', 'history.update', 'history.delete',
            'generate.outline', 'generate.image',
            'usage.view',
            'user.read', 'user.update',
        ]

        for perm_code in user_permissions:
            perm = next((p for p in permissions if p.code == perm_code), None)
            if perm:
                db.add(RolePermission(role_id=roles['user'].id, permission_id=perm.id))

        # 专业版用户权限（继承普通用户 + 额外权限）
        pro_permissions = user_permissions + ['billing.view']

        for perm_code in pro_permissions:
            perm = next((p for p in permissions if p.code == perm_code), None)
            if perm:
                db.add(RolePermission(role_id=roles['pro'].id, permission_id=perm.id))

        # 管理员权限（所有权限）
        for perm in permissions:
            db.add(RolePermission(role_id=roles['admin'].id, permission_id=perm.id))

        db.commit()

        logger.info(f"成功创建 {len(roles)} 个角色和 {len(permissions)} 个权限")

    except Exception as e:
        logger.error(f"创建角色和权限失败: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


def bootstrap_initial_admin():
    """
    自动创建初始管理员账户(幂等)

    仅在以下条件全部满足时创建:
    1. ADMIN_BOOTSTRAP_ON_START 配置开启
    2. 数据库中没有任何管理员账户
    3. 环境变量中配置了完整且有效的管理员凭证

    此函数保证幂等性,不会重复创建管理员
    """
    if not Config.ADMIN_BOOTSTRAP_ON_START:
        logger.info("管理员自动创建功能已关闭")
        return

    db = get_db()
    try:
        # 检查是否已存在管理员
        existing_admin = db.query(User).filter(User.role == 'admin').first()
        if existing_admin:
            logger.info(f"系统中已存在管理员账户,跳过自动创建")
            return

        # 检查环境变量配置是否完整
        if not Config.INITIAL_ADMIN_PASSWORD:
            logger.warning(
                "未设置 INITIAL_ADMIN_PASSWORD 环境变量,"
                "无法自动创建管理员账户。"
                "请运行 'python backend/create_admin.py' 手动创建"
            )
            return

        # 严格验证用户名
        username = (Config.INITIAL_ADMIN_USERNAME or '').strip()
        if not username:
            logger.error("INITIAL_ADMIN_USERNAME 为空,无法创建管理员")
            return
        if len(username) < 3 or len(username) > 50:
            logger.error(
                f"INITIAL_ADMIN_USERNAME 长度必须在 3-50 字符之间,"
                f"当前长度: {len(username)}"
            )
            return

        # 严格验证邮箱
        email = (Config.INITIAL_ADMIN_EMAIL or '').strip()
        if not email:
            logger.error("INITIAL_ADMIN_EMAIL 为空,无法创建管理员")
            return
        if '@' not in email or '.' not in email.split('@')[1]:
            logger.error(f"INITIAL_ADMIN_EMAIL 格式不正确: {email}")
            return

        # 严格验证密码强度
        password = Config.INITIAL_ADMIN_PASSWORD
        if len(password) < 8:
            logger.error(
                "INITIAL_ADMIN_PASSWORD 太弱!密码长度至少为 8 个字符。"
                "为确保安全,建议使用 12 位以上包含大小写字母、数字、符号的强密码"
            )
            return

        # 检查密码复杂度(建议至少包含3种字符类型)
        has_lower = any(c.islower() for c in password)
        has_upper = any(c.isupper() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(not c.isalnum() for c in password)
        complexity = sum([has_lower, has_upper, has_digit, has_special])

        if complexity < 2:
            logger.error(
                "INITIAL_ADMIN_PASSWORD 太简单!密码应至少包含以下2种:"
                "小写字母、大写字母、数字、特殊符号"
            )
            return

        if complexity < 3:
            logger.warning(
                "INITIAL_ADMIN_PASSWORD 强度一般,建议包含大小写字母、数字和符号"
            )

        # 检查用户名是否已被占用
        existing_user = db.query(User).filter(
            User.username == username
        ).first()
        if existing_user:
            logger.error(
                f"用户名 '{username}' 已存在(角色: {existing_user.role})。"
                f"无法创建管理员账户。"
                f"解决方案: 修改 INITIAL_ADMIN_USERNAME 环境变量,"
                f"或使用 'python backend/create_admin.py' 手动创建"
            )
            return

        # 检查邮箱是否已被占用
        existing_email = db.query(User).filter(
            User.email == email
        ).first()
        if existing_email:
            logger.error(
                f"邮箱 '{email}' 已被使用。无法创建管理员账户。"
                f"解决方案: 修改 INITIAL_ADMIN_EMAIL 环境变量,"
                f"或使用 'python backend/create_admin.py' 手动创建"
            )
            return

        # 创建管理员账户
        logger.info("正在创建初始管理员账户...")
        password_hash = hash_password(password)

        admin_user = User(
            username=username,
            email=email,
            password_hash=password_hash,
            role='admin',
            is_active=True,
        )

        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)

        logger.info("=" * 60)
        logger.info("✅ 初始管理员账户创建成功!")
        logger.info(f"   用户ID: {admin_user.id}")
        logger.info(f"   用户名: {admin_user.username}")
        logger.info(f"   邮箱: {admin_user.email}")
        logger.info("=" * 60)
        logger.warning(
            "🔒 安全提示:"
        )
        logger.warning(
            "   1. 请立即登录后台并修改管理员密码"
        )
        logger.warning(
            "   2. 修改完成后,从环境变量中删除 INITIAL_ADMIN_PASSWORD"
        )
        logger.warning(
            "   3. 检查 .env 文件是否已加入 .gitignore"
        )

    except Exception as e:
        logger.error(f"自动创建管理员失败: {e}", exc_info=True)
        db.rollback()
        logger.error(
            "⚠️ 初始化失败!请使用以下方式手动创建管理员:"
        )
        logger.error(
            "   python backend/create_admin.py"
        )
    finally:
        db.close()


def main():
    """主函数"""
    try:
        logger.info("=" * 60)
        logger.info("开始初始化数据库")
        logger.info("=" * 60)

        # 创建表结构
        logger.info("正在创建数据库表...")
        init_db()
        logger.info("数据库表创建成功")

        # 创建默认角色和权限
        create_default_roles_and_permissions()

        # 自动创建初始管理员账户
        bootstrap_initial_admin()

        logger.info("=" * 60)
        logger.info("数据库初始化完成！")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"数据库初始化失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
