"""
Reset user password tool
"""
import sys
import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.auth import hash_password
from backend.db import get_db
from backend.models import User

def main():
    print("=" * 70)
    print("Password Reset Tool")
    print("=" * 70)
    print()

    username = input("Username: ").strip()
    if not username:
        print("Username cannot be empty")
        sys.exit(1)

    db = get_db()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            print(f"User '{username}' not found")
            sys.exit(1)

        print(f"User found: {user.username} (Role: {user.role})")
        print()

        new_password = getpass.getpass("New password: ")
        if len(new_password) < 6:
            print("Password must be at least 6 characters")
            sys.exit(1)

        confirm = getpass.getpass("Confirm password: ")
        if new_password != confirm:
            print("Passwords do not match")
            sys.exit(1)

        # Update password
        user.password_hash = hash_password(new_password)
        db.commit()

        print()
        print("=" * 70)
        print("Password updated successfully!")
        print("=" * 70)

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()

if __name__ == '__main__':
    main()
