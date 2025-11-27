"""RQ Worker 启动脚本（支持多进程并发）。

支持多 Worker 进程并行处理任务，解决多用户同时发布任务时的排队问题。
通过 WORKER_CONCURRENCY 环境变量控制并发数量（默认 4）。

使用方式:
    python backend/worker.py

环境变量:
    WORKER_CONCURRENCY: 并发 Worker 数量（默认 4）
    REDIS_URL: Redis 连接地址
"""

from __future__ import annotations

import atexit
import logging
import multiprocessing
import os
import platform
import signal
import sys
import time
from multiprocessing.connection import wait as mp_wait
from pathlib import Path
from typing import List

# 确保项目根目录在 sys.path 中
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from backend.config import Config

# 主进程日志配置（支持环境变量调整级别与文件输出）
_LOG_LEVEL = os.getenv("WORKER_LOG_LEVEL", "INFO").upper()
_LOG_FILE = os.getenv("WORKER_LOG_FILE")
_LOG_HANDLERS: List[logging.Handler] = [logging.StreamHandler()]
if _LOG_FILE:
    _LOG_HANDLERS.append(logging.FileHandler(_LOG_FILE, encoding="utf-8"))

logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=_LOG_HANDLERS,
)
logger = logging.getLogger(__name__)

# 全局停止标志
_shutdown_requested = False

# 进程列表（模块级变量，便于异常处理时访问）
_worker_processes: List[multiprocessing.Process] = []

# 重启节流配置，避免异常重启风暴
_RESTART_BACKOFF_SECONDS = 5


def _setup_child_logging(worker_id: int) -> logging.Logger:
    """为子进程配置独立的日志。

    Windows spawn 模式下子进程不会继承父进程的 logging 配置，
    需要在子进程中重新配置。

    Args:
        worker_id: Worker 编号

    Returns:
        配置好的 Logger 实例
    """
    # 重新配置日志（子进程独立配置）
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,  # Python 3.8+ 允许重新配置
    )
    return logging.getLogger(f"worker-{worker_id}")


def _run_single_worker(worker_id: int) -> None:
    """运行单个 Worker 进程。

    Args:
        worker_id: Worker 编号（用于日志区分）
    """
    # 子进程配置日志
    process_logger = _setup_child_logging(worker_id)

    # 子进程需要重新导入和初始化连接
    from backend.task_queue import (
        get_outline_queue,
        get_image_queue,
        get_redis_connection,
        reset_connections,
    )

    # 重置连接缓存，确保子进程建立独立连接
    reset_connections()

    worker_name = f"worker-{platform.node()}-{worker_id}"
    process_logger.info(f"🔧 Worker {worker_id} 正在初始化...")

    try:
        # 每个子进程建立独立的 Redis 连接
        redis_conn = get_redis_connection()
        redis_conn.ping()

        outline_queue = get_outline_queue()
        image_queue = get_image_queue()

        # 选择 Worker 类型
        if platform.system() == "Windows":
            from rq.worker import SimpleWorker as WorkerClass
        else:
            from rq import Worker as WorkerClass

        worker = WorkerClass(
            queues=[outline_queue, image_queue],
            connection=redis_conn,
            name=worker_name,
        )

        process_logger.info(f"✓ Worker {worker_id} 已启动，监听队列中...")
        worker.work(with_scheduler=False)

    except Exception as e:
        process_logger.error(f"❌ Worker {worker_id} 异常退出: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # 确保连接与句柄清理，避免资源泄漏
        try:
            reset_connections()
        except Exception:
            process_logger.debug("资源清理失败，继续退出", exc_info=True)


def _signal_handler(signum: int, frame) -> None:
    """处理中断信号，设置停止标志。"""
    global _shutdown_requested
    _shutdown_requested = True
    logger.info(f"\n⏹ 收到停止信号 ({signal.Signals(signum).name})，正在优雅关闭...")


def _create_worker_process(worker_id: int) -> multiprocessing.Process:
    """创建 Worker 进程。

    Args:
        worker_id: Worker 编号

    Returns:
        创建的进程对象
    """
    return multiprocessing.Process(
        target=_run_single_worker,
        args=(worker_id,),
        name=f"worker-{worker_id}",
        daemon=False,  # 非守护进程，确保优雅关闭
    )


def _terminate_all_workers(processes: List[multiprocessing.Process]) -> None:
    """终止所有 Worker 进程。

    Args:
        processes: 进程列表
    """
    if not processes:
        return

    logger.info("正在终止所有 Worker 进程...")

    # 发送终止信号
    for i, p in enumerate(processes):
        if p.is_alive():
            p.terminate()
            logger.info(f"✓ 已发送终止信号给 Worker {i} (PID: {p.pid})")

    # 等待所有进程退出
    for p in processes:
        p.join(timeout=10)
        if p.is_alive():
            logger.warning(f"⚠ Worker (PID: {p.pid}) 未响应，强制终止...")
            p.kill()
            p.join(timeout=5)

    logger.info("✓ 所有 Worker 已停止")


def _resolve_concurrency() -> int:
    """解析并发数，防御性校正配置，避免 CPU 过载或配置错误。

    Returns:
        校正后的并发 Worker 数量
    """
    try:
        cpu_total = multiprocessing.cpu_count() or 1
    except NotImplementedError:
        cpu_total = 1

    configured = Config.WORKER_CONCURRENCY or 4
    if configured <= 0:
        logger.warning("⚠ WORKER_CONCURRENCY 配置无效（<=0），回退为 1")
        return 1

    # 允许略高于 CPU 核心数，兼顾 I/O 密集型任务
    upper_bound = max(1, cpu_total * 2)
    if configured > upper_bound:
        logger.warning(
            f"⚠ WORKER_CONCURRENCY={configured} 过高，依据 CPU 核心数限制为 {upper_bound}"
        )
        return upper_bound
    return configured


def _register_exit_cleanup() -> None:
    """注册进程退出时的清理，确保异常终止也能回收子进程。"""
    atexit.register(_terminate_all_workers, _worker_processes)


def main() -> None:
    """启动多进程 Worker Pool。"""
    global _shutdown_requested, _worker_processes

    # 设置信号处理器
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _signal_handler)

    # Windows 多进程必须使用 spawn
    if platform.system() == "Windows":
        multiprocessing.set_start_method("spawn", force=True)

    try:
        # 测试 Redis 连接
        from backend.task_queue import get_redis_connection
        redis_conn = get_redis_connection()
        redis_conn.ping()
        logger.info("✓ Redis 连接成功")

        # 获取并发配置（带防御性校验）
        concurrency = _resolve_concurrency()
        logger.info(f"✓ 并发 Worker 数量: {concurrency}")

        logger.info("=" * 60)
        logger.info("🚀 RQ Worker Pool 启动中...")
        logger.info(f"   Worker 数量: {concurrency}")
        logger.info(f"   平台: {platform.system()}")
        logger.info("   停止方式: Ctrl+C")
        logger.info("=" * 60)

        # 注册异常退出清理
        _register_exit_cleanup()

        # 重启时间戳追踪，用于节流
        last_restart_ts: List[float] = [0.0 for _ in range(concurrency)]

        # 启动多个 Worker 进程
        for i in range(concurrency):
            p = _create_worker_process(i)
            p.start()
            _worker_processes.append(p)
            logger.info(f"✓ Worker {i} 进程已启动 (PID: {p.pid})")

        # 构建 sentinel -> worker index 映射，用于高效监听
        sentinel_index_map = {p.sentinel: i for i, p in enumerate(_worker_processes)}

        # 主进程等待子进程，使用 sentinel 监听替代轮询
        while not _shutdown_requested:
            # 使用 mp_wait 监听进程退出事件，比 sleep 轮询更高效
            ready = mp_wait(list(sentinel_index_map.keys()), timeout=1.0)

            for sentinel in ready:
                i = sentinel_index_map.get(sentinel)
                if i is None:
                    continue

                p = _worker_processes[i]
                if not p.is_alive() and p.exitcode is not None:
                    # 重启节流：避免短时间内多次重启
                    now = time.time()
                    if now - last_restart_ts[i] < _RESTART_BACKOFF_SECONDS:
                        logger.warning(
                            f"⚠ Worker {i} 短时间内多次崩溃，延后重启以避免重启风暴"
                        )
                        continue
                    last_restart_ts[i] = now

                    # 记录退出状态
                    if p.exitcode != 0:
                        logger.warning(
                            f"⚠ Worker {i} 异常退出 (exit code: {p.exitcode})，正在重启..."
                        )
                    else:
                        logger.info(f"ℹ Worker {i} 正常退出，正在重启...")

                    # 重启退出的 Worker
                    new_p = _create_worker_process(i)
                    new_p.start()
                    _worker_processes[i] = new_p

                    # 更新 sentinel 映射
                    sentinel_index_map.pop(sentinel, None)
                    sentinel_index_map[new_p.sentinel] = i

                    logger.info(f"✓ Worker {i} 已重启 (PID: {new_p.pid})")

        # 收到停止信号，终止所有子进程
        _terminate_all_workers(_worker_processes)

    except KeyboardInterrupt:
        logger.info("\n⏹ Worker Pool 已停止 (KeyboardInterrupt)")
        _terminate_all_workers(_worker_processes)
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Worker Pool 启动失败: {e}", exc_info=True)
        _terminate_all_workers(_worker_processes)
        sys.exit(1)


if __name__ == "__main__":
    # Windows spawn 模式下需要 freeze_support 以避免子进程重复执行入口
    multiprocessing.freeze_support()
    main()
