"""
历史记录服务

使用 SQLAlchemy 数据库存储，确保用户数据隔离
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from sqlalchemy import func

from backend.db import db_session
from backend.models import HistoryRecord


class HistoryService:
    """历史记录服务（数据库版本）

    所有方法都要求传入 user_id 参数，确保数据隔离
    """

    def __init__(self):
        """初始化服务（无需文件系统操作）"""
        pass

    def create_record(
        self,
        user_id: int,
        topic: str,
        outline: Dict,
        task_id: Optional[str] = None,
        user_images: Optional[List[str]] = None,
        record_id: Optional[str] = None
    ) -> str:
        """创建历史记录

        Args:
            user_id: 用户 ID
            topic: 主题标题
            outline: 大纲数据（dict）
            task_id: 图片生成任务 ID（可选）
            user_images: 用户上传的参考图片（base64 编码列表，可选）
            record_id: 指定的记录 UUID（可选，用于幂等创建）

        Returns:
            str: 记录 UUID
        """
        with db_session() as db:
            record_uuid = record_id or str(uuid.uuid4())
            record = HistoryRecord(
                record_uuid=record_uuid,
                user_id=user_id,
                title=topic,
                outline_json=outline,
                image_task_id=task_id,
                user_images_json={'images': user_images} if user_images else None,
                status='draft',
            )
            db.add(record)
            db.flush()  # 确保生成/占用 UUID
            return record.record_uuid

    def create_or_update_draft(
        self,
        user_id: int,
        topic: str,
        outline: Dict,
        task_id: Optional[str] = None,
        user_images: Optional[List[str]] = None,
        record_id: Optional[str] = None
    ) -> str:
        """幂等草稿创建/更新，支持客户端自带 record_id

        如果指定的 record_id 已存在且属于该用户，则更新草稿内容；
        否则创建新的草稿记录。这样可以支持前端重试而不会重复创建记录。

        Args:
            user_id: 用户 ID
            topic: 主题标题
            outline: 大纲数据（dict）
            task_id: 图片生成任务 ID（可选）
            user_images: 用户上传的参考图片（base64 编码列表，可选）
            record_id: 指定的记录 UUID（可选）

        Returns:
            str: 记录 UUID
        """
        with db_session() as db:
            # 如果提供了 record_id，先尝试查找现有记录
            if record_id:
                existing = db.query(HistoryRecord).filter(
                    HistoryRecord.record_uuid == record_id,
                    HistoryRecord.user_id == user_id
                ).first()

                if existing:
                    # 更新现有草稿
                    existing.title = topic
                    existing.outline_json = outline
                    existing.image_task_id = task_id
                    existing.user_images_json = {'images': user_images} if user_images else None
                    existing.status = 'draft'
                    existing.updated_at = datetime.now(timezone.utc)
                    db.flush()  # 确保更新被提交
                    return existing.record_uuid

            # 不存在则按给定 record_id（或新 UUID）创建
            new_uuid = record_id or str(uuid.uuid4())
            record = HistoryRecord(
                record_uuid=new_uuid,
                user_id=user_id,
                title=topic,
                outline_json=outline,
                image_task_id=task_id,
                user_images_json={'images': user_images} if user_images else None,
                status='draft',
            )
            db.add(record)
            db.flush()
            return record.record_uuid

    def get_record(self, user_id: int, record_id: str) -> Optional[Dict]:
        """获取历史记录详情

        Args:
            user_id: 用户 ID
            record_id: 记录 UUID

        Returns:
            Optional[Dict]: 记录详情，不存在或无权限返回 None
        """
        with db_session() as db:
            record = db.query(HistoryRecord).filter(
                HistoryRecord.record_uuid == record_id,
                HistoryRecord.user_id == user_id
            ).first()

            return self._record_to_dict(record) if record else None

    def update_record(
        self,
        user_id: int,
        record_id: str,
        outline: Optional[Dict] = None,
        images: Optional[Dict] = None,
        status: Optional[str] = None,
        thumbnail: Optional[str] = None,
        user_images: Optional[List[str]] = None
    ) -> bool:
        """更新历史记录

        Args:
            user_id: 用户 ID
            record_id: 记录 UUID
            outline: 大纲数据（可选）
            images: 图片数据（可选）
            status: 状态（可选）
            thumbnail: 缩略图 URL（可选）
            user_images: 用户上传的参考图片（base64 编码列表，可选）

        Returns:
            bool: 是否更新成功
        """
        with db_session() as db:
            record = db.query(HistoryRecord).filter(
                HistoryRecord.record_uuid == record_id,
                HistoryRecord.user_id == user_id
            ).first()

            if not record:
                return False

            # 更新字段
            if outline is not None:
                record.outline_json = outline
            if images is not None:
                record.images_json = images
            if status is not None:
                record.status = status
            if thumbnail is not None:
                record.thumbnail_url = thumbnail
            if user_images is not None:
                record.user_images_json = {'images': user_images}

            # 更新时间戳（数据库会自动更新，这里显式设置确保一致性）
            record.updated_at = datetime.now(timezone.utc)

            return True

    def delete_record(self, user_id: int, record_id: str) -> bool:
        """删除历史记录

        Args:
            user_id: 用户 ID
            record_id: 记录 UUID

        Returns:
            bool: 是否删除成功

        Note:
            关联的 ImageFile 会通过数据库级联删除
        """
        with db_session() as db:
            record = db.query(HistoryRecord).filter(
                HistoryRecord.record_uuid == record_id,
                HistoryRecord.user_id == user_id
            ).first()

            if not record:
                return False

            db.delete(record)
            return True

    def list_records(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None
    ) -> Dict:
        """获取历史记录列表（分页）

        Args:
            user_id: 用户 ID
            page: 页码（从 1 开始）
            page_size: 每页数量
            status: 状态过滤（可选）

        Returns:
            Dict: 包含 records, total, page, page_size, total_pages
        """
        with db_session() as db:
            # 构建查询
            query = db.query(HistoryRecord).filter(
                HistoryRecord.user_id == user_id
            )

            if status:
                query = query.filter(HistoryRecord.status == status)

            # 按创建时间倒序
            query = query.order_by(HistoryRecord.created_at.desc())

            # 计算总数
            total = query.count()

            # 分页查询
            records = query.offset((page - 1) * page_size).limit(page_size).all()

            return {
                'records': [self._record_to_dict(r, summary=True) for r in records],
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': (total + page_size - 1) // page_size if total > 0 else 0
            }

    def search_records(self, user_id: int, keyword: str) -> List[Dict]:
        """搜索历史记录（按标题）

        Args:
            user_id: 用户 ID
            keyword: 搜索关键词

        Returns:
            List[Dict]: 匹配的记录列表
        """
        with db_session() as db:
            records = db.query(HistoryRecord).filter(
                HistoryRecord.user_id == user_id,
                HistoryRecord.title.contains(keyword)
            ).order_by(HistoryRecord.created_at.desc()).all()

            return [self._record_to_dict(r, summary=True) for r in records]

    def get_statistics(self, user_id: int) -> Dict:
        """获取用户统计信息

        Args:
            user_id: 用户 ID

        Returns:
            Dict: 包含 total 和 by_status 统计
        """
        with db_session() as db:
            # 总记录数
            total = db.query(HistoryRecord).filter(
                HistoryRecord.user_id == user_id
            ).count()

            # 按状态分组统计
            status_counts = db.query(
                HistoryRecord.status,
                func.count(HistoryRecord.id)
            ).filter(
                HistoryRecord.user_id == user_id
            ).group_by(HistoryRecord.status).all()

            return {
                'total': total,
                'by_status': {status: count for status, count in status_counts}
            }

    @staticmethod
    def _record_to_dict(record: HistoryRecord, summary: bool = False) -> Dict:
        """将 HistoryRecord 模型转换为 dict

        Args:
            record: HistoryRecord 实例
            summary: 是否只返回摘要信息（用于列表显示）

        Returns:
            Dict: 记录数据
        """
        if not record:
            return {}

        # 基础信息
        data = {
            'id': record.record_uuid,
            'title': record.title,
            'created_at': record.created_at.isoformat() if record.created_at else None,
            'updated_at': record.updated_at.isoformat() if record.updated_at else None,
            'status': record.status,
            'thumbnail': record.thumbnail_url,
        }

        if summary:
            # 列表显示：仅包含基础信息和页数
            data['page_count'] = (
                len(record.outline_json.get('pages', []))
                if record.outline_json else 0
            )
        else:
            # 详情显示：包含完整数据
            data['outline'] = record.outline_json
            data['images'] = record.images_json or {
                'task_id': record.image_task_id,
                'generated': []
            }
            data['page_count'] = (
                len(record.outline_json.get('pages', []))
                if record.outline_json else 0
            )
            # 添加用户参考图片
            if record.user_images_json:
                data['user_images'] = record.user_images_json.get('images', [])
            else:
                data['user_images'] = []

        return data


# 单例模式
_service_instance = None


def get_history_service() -> HistoryService:
    """获取 HistoryService 单例

    Returns:
        HistoryService: 服务实例
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = HistoryService()
    return _service_instance
