"""
命令行工具:创建管理员账户

用于在服务器上手动创建初始管理员账户
支持交互式输入,密码隐藏,幂等性检查

使用方法:
    python backend/create_admin.py

安全特性:
    - 密码输入隐藏
    - 二次确认密码
    - 检查用户名/邮箱是否已存在
    - 幂等性保证(不会重复创建)
"""
import sys
import logging
import getpass
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.auth import hash_password
from backend.db import get_db, init_db
from backend.models import User

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def validate_username(username: str) -> tuple[bool, str]:
    """验证用户名格式"""
    if not username:
        return False, "用户名不能为空"
    if len(username) < 3 or len(username) > 50:
        return False, "用户名长度必须在 3-50 个字符之间"
    return True, ""


def validate_email(email: str) -> tuple[bool, str]:
    """验证邮箱格式"""
    if not email:
        return False, "邮箱不能为空"
    if '@' not in email or '.' not in email.split('@')[1]:
        return False, "邮箱格式不正确"
    return True, ""


def validate_password(password: str) -> tuple[bool, str]:
    """验证密码格式和强度"""
    if not password:
        return False, "密码不能为空"
    if len(password) < 8:
        return False, "密码长度至少为 8 个字符"

    # 检查密码复杂度
    has_lower = any(c.islower() for c in password)
    has_upper = any(c.isupper() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(not c.isalnum() for c in password)
    complexity = sum([has_lower, has_upper, has_digit, has_special])

    if complexity < 2:
        return False, "密码太简单!至少包含以下2种:小写字母、大写字母、数字、特殊符号"

    if complexity < 3:
        print("ℹ️  提示: 建议密码包含大小写字母、数字和特殊符号以提高安全性")

    return True, ""


def main():
    """主函数"""
    print("=" * 70)
    print("RedInk 管理员账户创建工具")
    print("=" * 70)
    print()

    # 确保数据库已初始化
    try:
        init_db()
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        sys.exit(1)

    db = get_db()
    try:
        # 1. 获取用户名
        print("请输入管理员账户信息:")
        print("-" * 70)
        while True:
            username = input("用户名: ").strip()
            valid, error = validate_username(username)
            if not valid:
                print(f"❌ {error}")
                continue

            # 检查用户名是否已存在
            existing = db.query(User).filter(User.username == username).first()
            if existing:
                print(f"ℹ️  用户名 '{username}' 已存在")
                print(f"   用户ID: {existing.id}")
                print(f"   邮箱: {existing.email}")
                print(f"   当前角色: {existing.role}")
                print()

                # 判断是否已是管理员
                if existing.role == 'admin':
                    print("✅ 该用户已是管理员，无需重复操作")
                    return

                # 提示升级选项
                print("-" * 70)
                upgrade = input("是否将此用户升级为管理员? (y/n): ").strip().lower()
                if upgrade in ('y', 'yes'):
                    # 二次确认升级操作
                    confirm = input("确认升级? (yes/no): ").strip().lower()
                    if confirm in ('yes', 'y'):
                        existing.role = 'admin'
                        db.commit()
                        db.refresh(existing)
                        print()
                        print("=" * 70)
                        print("✅ 用户升级成功!")
                        print(f"   用户ID: {existing.id}")
                        print(f"   用户名: {existing.username}")
                        print(f"   邮箱: {existing.email}")
                        print(f"   新角色: {existing.role}")
                        print("=" * 70)
                        return
                    else:
                        print("已取消升级")

                # 询问是否重新输入
                retry = input("是否重新输入用户名? (y/n): ").strip().lower()
                if retry != 'y':
                    print("已取消")
                    return
                continue
            break

        # 2. 获取邮箱
        while True:
            email = input("邮箱: ").strip()
            valid, error = validate_email(email)
            if not valid:
                print(f"❌ {error}")
                continue

            # 检查邮箱是否已存在
            existing = db.query(User).filter(User.email == email).first()
            if existing:
                print(f"❌ 邮箱 '{email}' 已被使用")
                retry = input("是否重新输入? (y/n): ").strip().lower()
                if retry != 'y':
                    print("已取消")
                    return
                continue
            break

        # 3. 获取密码
        while True:
            password = getpass.getpass("密码(输入隐藏): ")
            valid, error = validate_password(password)
            if not valid:
                print(f"❌ {error}")
                continue

            confirm = getpass.getpass("确认密码: ")
            if password != confirm:
                print("❌ 两次密码不一致,请重新输入")
                continue
            break

        # 4. 确认创建
        print()
        print("-" * 70)
        print("即将创建管理员账户:")
        print(f"  用户名: {username}")
        print(f"  邮箱: {email}")
        print(f"  角色: admin")
        print("-" * 70)
        confirm = input("确认创建? (yes/no): ").strip().lower()

        if confirm not in ('yes', 'y'):
            print("已取消")
            return

        # 5. 创建管理员账户
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

        print()
        print("=" * 70)
        print("✅ 管理员账户创建成功!")
        print(f"   用户ID: {admin_user.id}")
        print(f"   用户名: {admin_user.username}")
        print(f"   邮箱: {admin_user.email}")
        print("=" * 70)
        print()
        print("现在您可以使用此账户登录后台管理系统了")

    except KeyboardInterrupt:
        print("\n\n操作已取消")
        sys.exit(0)
    except Exception as e:
        logger.error(f"创建管理员失败: {e}", exc_info=True)
        db.rollback()
        print(f"\n❌ 创建失败: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == '__main__':
    main()
