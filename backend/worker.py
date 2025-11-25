"""RQ Worker 启动脚本（Windows 兼容版本）。

Windows 系统不支持 os.fork()，因此使用 SimpleWorker 替代默认的 Worker。
SimpleWorker 在主进程中同步执行任务，适用于开发环境和 Windows 平台。

使用方式:
    python backend/worker.py

注意事项:
    - SimpleWorker 不支持并发，一次只能处理一个任务
    - 生产环境建议使用 Linux 系统 + 标准 Worker
    - 可通过环境变量 WORKER_CLASS 切换 Worker 类型
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from backend.config import Config
from backend.task_queue import get_outline_queue, get_image_queue, get_redis_connection

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """启动 RQ Worker。"""
    try:
        # 测试 Redis 连接
        redis_conn = get_redis_connection()
        redis_conn.ping()
        logger.info("✓ Redis 连接成功")

        # 获取队列
        outline_queue = get_outline_queue()
        image_queue = get_image_queue()
        logger.info(f"✓ 队列已加载: {outline_queue.name}, {image_queue.name}")

        # 根据平台选择 Worker 类型
        import platform
        if platform.system() == "Windows":
            from rq.worker import SimpleWorker as WorkerClass
            logger.info("⚠ Windows 平台检测到，使用 SimpleWorker（同步模式）")
        else:
            from rq import Worker as WorkerClass
            logger.info("✓ 使用标准 Worker（多进程模式）")

        # 创建 Worker
        worker = WorkerClass(
            queues=[outline_queue, image_queue],
            connection=redis_conn,
            name=f"worker-{platform.node()}",
        )

        logger.info("=" * 60)
        logger.info("🚀 RQ Worker 已启动")
        logger.info(f"   监听队列: {[q.name for q in worker.queues]}")
        logger.info(f"   Worker 类型: {WorkerClass.__name__}")
        logger.info(f"   按 Ctrl+C 停止")
        logger.info("=" * 60)

        # 启动 Worker（阻塞）
        worker.work(with_scheduler=False)

    except KeyboardInterrupt:
        logger.info("\n⏹ Worker 已停止")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Worker 启动失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
