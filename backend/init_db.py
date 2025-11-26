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
from backend.models import Role, Permission, RolePermission

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

        logger.info("=" * 60)
        logger.info("数据库初始化完成！")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"数据库初始化失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
