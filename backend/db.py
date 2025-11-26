"""
数据库连接和会话管理

支持 SQLite（默认）和 MySQL，通过 DATABASE_URL 环境变量配置
"""
import logging
from contextlib import contextmanager
from typing import Generator

import sqlalchemy as sa
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session, Session

from backend.config import Config

logger = logging.getLogger(__name__)

# 声明基类
Base = declarative_base()

# 创建引擎
engine = sa.create_engine(
    Config.DATABASE_URL,
    future=True,
    pool_pre_ping=True,  # 自动检测断开的连接
    echo=Config.DEBUG,  # 开发环境打印 SQL
)

# 创建会话工厂
SessionLocal = scoped_session(
    sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
)


def init_db() -> None:
    """
    初始化数据库表结构

    注意：仅在开发/测试环境使用，生产环境应使用 Alembic 迁移
    """
    # 导入所有模型以确保它们被注册
    from backend import models  # noqa: F401

    logger.info(f"正在初始化数据库: {Config.DATABASE_URL}")
    Base.metadata.create_all(bind=engine)
    logger.info("数据库初始化完成")


def get_db() -> Session:
    """
    获取数据库会话（用于依赖注入）

    Returns:
        Session: 数据库会话对象
    """
    return SessionLocal()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """
    数据库会话上下文管理器

    使用示例:
        with db_session() as db:
            user = db.query(User).first()

    Yields:
        Session: 数据库会话对象
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def close_db() -> None:
    """关闭数据库连接"""
    SessionLocal.remove()
