"""
数据库迁移脚本：添加 user_images_json 字段到 history_records 表

使用方法：
    python migrate_add_user_images.py
"""
import logging
import sqlite3
from pathlib import Path

from backend.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_add_user_images_json():
    """添加 user_images_json 字段到 history_records 表"""

    # 从 DATABASE_URL 提取数据库文件路径
    db_url = Config.DATABASE_URL
    if not db_url.startswith("sqlite:///"):
        logger.error("此迁移脚本仅支持 SQLite 数据库")
        return False

    db_path = db_url.replace("sqlite:///", "")

    if not Path(db_path).exists():
        logger.error(f"数据库文件不存在: {db_path}")
        return False

    logger.info(f"连接到数据库: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 检查字段是否已存在
        cursor.execute("PRAGMA table_info(history_records)")
        columns = [row[1] for row in cursor.fetchall()]

        if "user_images_json" in columns:
            logger.info("✓ user_images_json 字段已存在，无需迁移")
            conn.close()
            return True

        logger.info("开始添加 user_images_json 字段...")

        # SQLite 支持 ALTER TABLE ADD COLUMN
        cursor.execute("""
            ALTER TABLE history_records
            ADD COLUMN user_images_json TEXT
        """)

        conn.commit()
        logger.info("✓ 成功添加 user_images_json 字段")

        # 验证字段已添加
        cursor.execute("PRAGMA table_info(history_records)")
        columns = [row[1] for row in cursor.fetchall()]

        if "user_images_json" in columns:
            logger.info("✓ 验证成功：user_images_json 字段已存在于表中")
            conn.close()
            return True
        else:
            logger.error("✗ 验证失败：字段未成功添加")
            conn.close()
            return False

    except sqlite3.Error as e:
        logger.error(f"数据库操作失败: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False
    except Exception as e:
        logger.error(f"迁移失败: {e}")
        if conn:
            conn.close()
        return False


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("数据库迁移：添加 user_images_json 字段")
    logger.info("=" * 60)

    success = migrate_add_user_images_json()

    if success:
        logger.info("\n✓ 迁移成功完成！")
    else:
        logger.error("\n✗ 迁移失败，请检查错误信息")
        exit(1)
