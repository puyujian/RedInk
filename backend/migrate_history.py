"""
历史记录迁移脚本

将旧的 JSON 文件历史记录迁移到数据库
"""
import json
import logging
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.db import get_db
from backend.models import HistoryRecord

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate_history_records():
    """迁移历史记录"""
    history_dir = Path(__file__).parent.parent / 'history'
    index_file = history_dir / 'index.json'

    if not index_file.exists():
        logger.warning(f"历史记录索引文件不存在: {index_file}")
        return 0

    # 读取索引文件
    try:
        with open(index_file, 'r', encoding='utf-8') as f:
            index_data = json.load(f)
    except Exception as e:
        logger.error(f"读取索引文件失败: {e}")
        return 0

    records = index_data.get('records', [])
    if not records:
        logger.info("没有需要迁移的历史记录")
        return 0

    logger.info(f"找到 {len(records)} 条历史记录，开始迁移...")

    db = get_db()
    migrated_count = 0
    skipped_count = 0

    try:
        for record_meta in records:
            record_id = record_meta.get('id')
            if not record_id:
                logger.warning("跳过无效记录（缺少 ID）")
                skipped_count += 1
                continue

            # 检查是否已迁移
            existing = db.query(HistoryRecord).filter(
                HistoryRecord.record_uuid == record_id
            ).first()

            if existing:
                logger.debug(f"记录 {record_id} 已存在，跳过")
                skipped_count += 1
                continue

            # 读取完整记录
            record_file = history_dir / f"{record_id}.json"
            if not record_file.exists():
                logger.warning(f"记录文件不存在: {record_file}")
                skipped_count += 1
                continue

            try:
                with open(record_file, 'r', encoding='utf-8') as f:
                    record_data = json.load(f)
            except Exception as e:
                logger.error(f"读取记录文件失败 {record_file}: {e}")
                skipped_count += 1
                continue

            # 解析数据
            title = record_data.get('title', '未命名')
            status = record_data.get('status', 'draft')
            outline = record_data.get('outline', {})
            images = record_data.get('images', {})
            created_at_str = record_data.get('created_at')
            updated_at_str = record_data.get('updated_at')

            # 解析时间
            try:
                created_at = datetime.fromisoformat(created_at_str) if created_at_str else datetime.now()
                updated_at = datetime.fromisoformat(updated_at_str) if updated_at_str else created_at
            except Exception:
                created_at = datetime.now()
                updated_at = created_at

            # 创建数据库记录
            db_record = HistoryRecord(
                record_uuid=record_id,
                user_id=None,  # 遗留数据，无用户关联
                client_id=None,  # 旧数据没有 client_id
                title=title,
                status=status,
                thumbnail_url=record_data.get('thumbnail'),
                page_count=len(outline.get('pages', [])),
                outline_raw=outline.get('raw'),
                outline_json=outline,
                images_json=images,
                image_task_id=images.get('task_id'),
                created_at=created_at,
                updated_at=updated_at,
            )

            db.add(db_record)
            migrated_count += 1

            if migrated_count % 10 == 0:
                logger.info(f"已迁移 {migrated_count} 条记录...")

        # 提交所有更改
        db.commit()
        logger.info(f"成功迁移 {migrated_count} 条记录，跳过 {skipped_count} 条")

        return migrated_count

    except Exception as e:
        logger.error(f"迁移失败: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


def main():
    """主函数"""
    try:
        logger.info("=" * 60)
        logger.info("开始迁移历史记录")
        logger.info("=" * 60)

        count = migrate_history_records()

        logger.info("=" * 60)
        logger.info(f"历史记录迁移完成！共迁移 {count} 条记录")
        logger.info("=" * 60)

        # 提示
        if count > 0:
            logger.info("\n注意事项：")
            logger.info("1. 迁移的记录没有关联用户（user_id 为 NULL）")
            logger.info("2. 这些记录将被标记为遗留数据，仅管理员可见")
            logger.info("3. 用户注册时如果提供 client_id，可以自动绑定历史记录")
            logger.info("4. 原始 JSON 文件已保留，可以安全删除或备份")

    except Exception as e:
        logger.error(f"迁移失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
