"""
历史记录服务

使用数据库存储并提供完整的用户数据隔离
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

from backend.db import get_db
from backend.models import HistoryRecord, User

logger = logging.getLogger(__name__)


class HistoryService:
    """历史记录服务（基于数据库）"""

    def create_record(
        self,
        topic: str,
        outline: Dict,
        user_id: int,
        task_id: Optional[str] = None,
        client_id: Optional[str] = None
    ) -> str:
        """
        创建历史记录

        Args:
            topic: 主题/标题
            outline: 大纲数据
            user_id: 用户 ID（必需）
            task_id: 关联的任务 ID
            client_id: 客户端 ID（用于迁移）

        Returns:
            str: 记录 UUID
        """
        db = get_db()
        try:
            # 生成 UUID
            import uuid
            record_uuid = str(uuid.uuid4())

            # 创建记录
            record = HistoryRecord(
                record_uuid=record_uuid,
                user_id=user_id,
                client_id=client_id,
                title=topic,
                status="draft",
                page_count=len(outline.get("pages", [])),
                outline_raw=outline.get("outline"),
                outline_json=outline,
                image_task_id=task_id
            )

            db.add(record)
            db.commit()
            db.refresh(record)

            logger.info(f"创建历史记录: record_uuid={record_uuid}, user_id={user_id}")
            return record_uuid

        except Exception as e:
            db.rollback()
            logger.error(f"创建历史记录失败: {e}")
            raise
        finally:
            db.close()

    def get_record(self, record_id: str, user_id: int) -> Optional[Dict]:
        """
        获取历史记录详情

        Args:
            record_id: 记录 UUID
            user_id: 用户 ID（用于权限验证）

        Returns:
            Optional[Dict]: 记录数据，不存在或无权限返回 None
        """
        db = get_db()
        try:
            record = db.query(HistoryRecord).filter(
                HistoryRecord.record_uuid == record_id,
                HistoryRecord.user_id == user_id
            ).first()

            if not record:
                return None

            return {
                "id": record.record_uuid,
                "title": record.title,
                "created_at": record.created_at.isoformat(),
                "updated_at": record.updated_at.isoformat(),
                "outline": record.outline_json or {},
                "images": {
                    "task_id": record.image_task_id,
                    "generated": record.images_json.get("generated", []) if record.images_json else []
                },
                "status": record.status,
                "thumbnail": record.thumbnail_url
            }

        except Exception as e:
            logger.error(f"获取历史记录失败: {e}")
            return None
        finally:
            db.close()

    def update_record(
        self,
        record_id: str,
        user_id: int,
        outline: Optional[Dict] = None,
        images: Optional[Dict] = None,
        status: Optional[str] = None,
        thumbnail: Optional[str] = None
    ) -> bool:
        """
        更新历史记录

        Args:
            record_id: 记录 UUID
            user_id: 用户 ID（用于权限验证）
            outline: 大纲数据
            images: 图片数据
            status: 状态
            thumbnail: 缩略图 URL

        Returns:
            bool: 是否更新成功
        """
        db = get_db()
        try:
            record = db.query(HistoryRecord).filter(
                HistoryRecord.record_uuid == record_id,
                HistoryRecord.user_id == user_id
            ).first()

            if not record:
                return False

            # 更新字段
            if outline is not None:
                record.outline_json = outline
                record.outline_raw = outline.get("outline")
                record.page_count = len(outline.get("pages", []))

            if images is not None:
                record.images_json = images
                if images.get("task_id"):
                    record.image_task_id = images["task_id"]

            if status is not None:
                record.status = status

            if thumbnail is not None:
                record.thumbnail_url = thumbnail

            db.commit()
            logger.info(f"更新历史记录: record_uuid={record_id}, user_id={user_id}")
            return True

        except Exception as e:
            db.rollback()
            logger.error(f"更新历史记录失败: {e}")
            return False
        finally:
            db.close()

    def delete_record(self, record_id: str, user_id: int) -> bool:
        """
        删除历史记录

        Args:
            record_id: 记录 UUID
            user_id: 用户 ID（用于权限验证）

        Returns:
            bool: 是否删除成功
        """
        db = get_db()
        try:
            record = db.query(HistoryRecord).filter(
                HistoryRecord.record_uuid == record_id,
                HistoryRecord.user_id == user_id
            ).first()

            if not record:
                return False

            # 删除关联的图片文件记录会通过外键级联删除
            db.delete(record)
            db.commit()

            logger.info(f"删除历史记录: record_uuid={record_id}, user_id={user_id}")
            return True

        except Exception as e:
            db.rollback()
            logger.error(f"删除历史记录失败: {e}")
            return False
        finally:
            db.close()

    def list_records(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None
    ) -> Dict:
        """
        获取历史记录列表（分页）

        Args:
            user_id: 用户 ID（用于数据隔离）
            page: 页码（从 1 开始）
            page_size: 每页数量
            status: 状态过滤

        Returns:
            Dict: 包含 records, total, page, page_size, total_pages
        """
        db = get_db()
        try:
            # 构建查询
            query = db.query(HistoryRecord).filter(
                HistoryRecord.user_id == user_id
            )

            if status:
                query = query.filter(HistoryRecord.status == status)

            # 按创建时间倒序
            query = query.order_by(HistoryRecord.created_at.desc())

            # 统计总数
            total = query.count()

            # 分页查询
            start = (page - 1) * page_size
            records = query.offset(start).limit(page_size).all()

            # 转换为字典
            record_list = []
            for record in records:
                record_list.append({
                    "id": record.record_uuid,
                    "title": record.title,
                    "created_at": record.created_at.isoformat(),
                    "updated_at": record.updated_at.isoformat(),
                    "status": record.status,
                    "thumbnail": record.thumbnail_url,
                    "page_count": record.page_count
                })

            return {
                "records": record_list,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size
            }

        except Exception as e:
            logger.error(f"获取历史记录列表失败: {e}")
            return {
                "records": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0
            }
        finally:
            db.close()

    def search_records(self, user_id: int, keyword: str) -> List[Dict]:
        """
        搜索历史记录

        Args:
            user_id: 用户 ID（用于数据隔离）
            keyword: 搜索关键词

        Returns:
            List[Dict]: 匹配的记录列表
        """
        db = get_db()
        try:
            records = db.query(HistoryRecord).filter(
                HistoryRecord.user_id == user_id,
                HistoryRecord.title.ilike(f"%{keyword}%")
            ).order_by(HistoryRecord.created_at.desc()).all()

            result = []
            for record in records:
                result.append({
                    "id": record.record_uuid,
                    "title": record.title,
                    "created_at": record.created_at.isoformat(),
                    "updated_at": record.updated_at.isoformat(),
                    "status": record.status,
                    "thumbnail": record.thumbnail_url,
                    "page_count": record.page_count
                })

            return result

        except Exception as e:
            logger.error(f"搜索历史记录失败: {e}")
            return []
        finally:
            db.close()

    def get_statistics(self, user_id: int) -> Dict:
        """
        获取历史记录统计

        Args:
            user_id: 用户 ID（用于数据隔离）

        Returns:
            Dict: 统计数据
        """
        db = get_db()
        try:
            records = db.query(HistoryRecord).filter(
                HistoryRecord.user_id == user_id
            ).all()

            total = len(records)
            status_count = {}

            for record in records:
                status = record.status
                status_count[status] = status_count.get(status, 0) + 1

            return {
                "total": total,
                "by_status": status_count
            }

        except Exception as e:
            logger.error(f"获取统计数据失败: {e}")
            return {
                "total": 0,
                "by_status": {}
            }
        finally:
            db.close()


_service_instance = None


def get_history_service() -> HistoryService:
    """获取历史记录服务单例"""
    global _service_instance
    if _service_instance is None:
        _service_instance = HistoryService()
    return _service_instance
