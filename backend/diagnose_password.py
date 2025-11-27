"""
Diagnose password issues
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.auth import hash_password, verify_password
from backend.db import get_db
from backend.models import User

# Test cases
test_passwords = [
    "admin",
    "admin123",
    "Admin123",
    "Admin123!",
    "password",
    "123456",
    "test123456",
]

def main():
    print("=" * 70)
    print("Password Diagnosis Tool")
    print("=" * 70)
    print()

    db = get_db()
    try:
        users = db.query(User).all()
        print(f"Found {len(users)} users in database:")
        print()

        for user in users:
            print(f"[User: {user.username}]")
            print(f"  Role: {user.role}")
            print(f"  Active: {user.is_active}")
            print(f"  Hash: {user.password_hash[:20]}... (length: {len(user.password_hash)})")
            print()

            print("  Testing common passwords:")
            for pwd in test_passwords:
                result = verify_password(pwd, user.password_hash)
                if result:
                    print(f"    [OK] MATCH: '{pwd}'")
                else:
                    print(f"    [--] No match: '{pwd}'")
            print()

    finally:
        db.close()

if __name__ == '__main__':
    main()
