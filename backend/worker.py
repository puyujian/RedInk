"""RQ Worker 启动脚本（支持多进程并发）。

支持多 Worker 进程并行处理任务，解决多用户同时发布任务时的排队问题。
通过 WORKER_CONCURRENCY 环境变量控制并发数量（默认 4）。

使用方式:
    python backend/worker.py

环境变量:
    WORKER_CONCURRENCY: 并发 Worker 数量（默认 4，上限为 CPU 核心数 * 2）
    REDIS_URL: Redis 连接地址
    WORKER_LOG_LEVEL: 日志级别（默认 INFO，可选 DEBUG/WARNING/ERROR）
    WORKER_LOG_FILE: 日志文件路径（可选，不设置则仅输出到控制台）
"""

from __future__ import annotations

import atexit
import contextlib
import logging
import multiprocessing
import os
import platform
import signal
import sys
import time
from multiprocessing.connection import wait as mp_wait
from pathlib import Path
from typing import List, Optional

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

# RQ Worker 心跳 TTL（秒），用于判断 worker 是否失效
_DEFAULT_WORKER_TTL = int(os.getenv("RQ_WORKER_TTL", "420"))


def _pid_alive(pid: int) -> bool:
    """检查本机 PID 是否仍然存活。

    Args:
        pid: 进程 ID

    Returns:
        True 如果进程存活，False 如果进程不存在或已退出
    """
    if pid <= 0:
        return False
    try:
        # os.kill(pid, 0) 不会真正发送信号，只检查进程是否存在
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _cleanup_stale_worker(
    redis_conn,
    worker_name: str,
    worker_ttl: int = _DEFAULT_WORKER_TTL,
    process_logger: Optional[logging.Logger] = None,
) -> bool:
    """清理 Redis 中残留的同名僵尸 worker 注册信息。

    在 worker.register_birth() 前调用，避免因残留注册导致启动失败。
    使用 Redis 分布式锁防止并发清理冲突。

    清理条件（满足任一）：
    1. 心跳 key 已不存在（TTL 过期自动删除），但集合中仍有残留
    2. 心跳 key 存在但对应 PID 已不存活（进程异常退出）
    3. 心跳时间戳超过 worker_ttl（心跳长时间未更新）

    Args:
        redis_conn: Redis 连接对象
        worker_name: Worker 名称
        worker_ttl: Worker 心跳超时时间（秒）
        process_logger: 日志记录器（可选）

    Returns:
        True 如果执行了清理，False 如果无需清理或未获取锁
    """
    log = process_logger or logger
    lock_key = f"lock:rq-worker-clean:{worker_name}"
    lock = redis_conn.lock(lock_key, timeout=10, blocking_timeout=0)

    if not lock.acquire(blocking=False):
        log.debug(f"未获取清理锁，跳过清理: {worker_name}")
        return False

    try:
        worker_key = f"rq:worker:{worker_name}"
        workers_set = "rq:workers"

        # 检查 worker 是否在集合中注册
        if not redis_conn.sismember(workers_set, worker_name):
            return False  # 未注册，无需清理

        # 情况1：心跳 key 已不存在（TTL=-2 表示 key 不存在）
        ttl = redis_conn.ttl(worker_key)
        if ttl == -2:
            redis_conn.srem(workers_set, worker_name)
            log.info(f"🧹 已清理残留 worker（心跳 key 已过期）: {worker_name}")
            return True

        # 获取 worker 的 PID 和心跳信息
        worker_data = redis_conn.hgetall(worker_key)
        if not worker_data:
            redis_conn.srem(workers_set, worker_name)
            log.info(f"🧹 已清理残留 worker（无心跳数据）: {worker_name}")
            return True

        # 情况2：PID 已不存活（最可靠的判断）
        pid_str = worker_data.get(b"pid") or worker_data.get("pid")
        if pid_str:
            try:
                pid = int(pid_str)
                if not _pid_alive(pid):
                    redis_conn.delete(worker_key)
                    redis_conn.srem(workers_set, worker_name)
                    log.info(f"🧹 已清理残留 worker（PID {pid} 已退出）: {worker_name}")
                    return True
            except (ValueError, TypeError):
                pass  # PID 解析失败，继续检查心跳

        # 情况3：心跳超时（兜底检查）
        # RQ 心跳可能是 float 时间戳或 UTC 字符串格式
        last_heartbeat = worker_data.get(b"last_heartbeat") or worker_data.get("last_heartbeat")
        if last_heartbeat:
            heartbeat_time: Optional[float] = None
            try:
                # 尝试解析为 float 时间戳
                if isinstance(last_heartbeat, bytes):
                    last_heartbeat = last_heartbeat.decode("utf-8")
                heartbeat_time = float(last_heartbeat)
            except (ValueError, TypeError):
                # 尝试解析 UTC 字符串格式（如 "2024-01-01 12:00:00.123456"）
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(str(last_heartbeat).replace(" ", "T"))
                    heartbeat_time = dt.timestamp()
                except Exception:
                    pass  # 解析失败，跳过心跳检查

            if heartbeat_time is not None and time.time() - heartbeat_time > worker_ttl:
                redis_conn.delete(worker_key)
                redis_conn.srem(workers_set, worker_name)
                log.info(f"🧹 已清理残留 worker（心跳超时）: {worker_name}")
                return True

        # 情况4：TTL 为永久（-1）但无法确定存活状态，保守不清理
        # 这种情况很少见，通常 PID 检查已经覆盖

        return False

    finally:
        with contextlib.suppress(Exception):
            lock.release()


def _force_cleanup_worker(
    redis_conn,
    worker_name: str,
    process_logger: Optional[logging.Logger] = None,
) -> bool:
    """强制清理 worker 注册（不检查存活状态）。

    用于启动时清理当前主机的所有旧注册。如果对应 PID 仍存活，
    会先尝试终止该进程。

    Args:
        redis_conn: Redis 连接对象
        worker_name: Worker 名称
        process_logger: 日志记录器（可选）

    Returns:
        True 如果执行了清理
    """
    log = process_logger or logger
    worker_key = f"rq:worker:{worker_name}"
    workers_set = "rq:workers"

    # 检查是否注册
    if not redis_conn.sismember(workers_set, worker_name):
        # 也检查孤立的 worker key
        if not redis_conn.exists(worker_key):
            return False

    # 尝试获取并终止残留进程
    worker_data = redis_conn.hgetall(worker_key)
    if worker_data:
        pid_str = worker_data.get(b"pid") or worker_data.get("pid")
        if pid_str:
            try:
                pid = int(pid_str)
                if _pid_alive(pid):
                    log.info(f"🔪 正在终止残留进程 PID {pid}: {worker_name}")
                    try:
                        os.kill(pid, signal.SIGTERM)
                        # 给进程一点时间优雅退出
                        time.sleep(0.1)
                        if _pid_alive(pid):
                            os.kill(pid, signal.SIGKILL)
                    except OSError:
                        pass  # 进程可能已退出
            except (ValueError, TypeError):
                pass

    # 强制删除 Redis 注册
    redis_conn.delete(worker_key)
    redis_conn.srem(workers_set, worker_name)
    log.info(f"🧹 已强制清理 worker 注册: {worker_name}")
    return True


def _cleanup_all_stale_workers_for_host(redis_conn, force: bool = False) -> int:
    """清理当前主机所有残留的僵尸 worker。

    在主进程启动时调用，批量清理当前主机名前缀的所有历史 worker。

    Args:
        redis_conn: Redis 连接对象
        force: 是否强制清理（True=不检查存活状态直接清理并终止进程）

    Returns:
        清理的 worker 数量
    """
    host_prefix = f"worker-{platform.node()}-"
    workers_set = "rq:workers"
    cleaned_count = 0

    try:
        # 获取所有注册的 worker
        all_workers = redis_conn.smembers(workers_set)
        for worker_name_bytes in all_workers:
            worker_name = (
                worker_name_bytes.decode("utf-8")
                if isinstance(worker_name_bytes, bytes)
                else worker_name_bytes
            )

            # 只清理当前主机的 worker
            if worker_name.startswith(host_prefix):
                if force:
                    if _force_cleanup_worker(redis_conn, worker_name):
                        cleaned_count += 1
                else:
                    if _cleanup_stale_worker(redis_conn, worker_name):
                        cleaned_count += 1

    except Exception as e:
        logger.warning(f"⚠ 批量清理残留 worker 时出错: {e}")

    return cleaned_count


def _setup_child_logging(worker_id: int) -> logging.Logger:
    """为子进程配置独立的日志。

    Windows spawn 模式下子进程不会继承父进程的 logging 配置，
    需要在子进程中重新配置。继承父进程的日志级别和文件输出设置。

    Args:
        worker_id: Worker 编号

    Returns:
        配置好的 Logger 实例
    """
    # 从环境变量读取配置（与主进程保持一致）
    log_level = os.getenv("WORKER_LOG_LEVEL", "INFO").upper()
    log_file = os.getenv("WORKER_LOG_FILE")

    handlers: List[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    # 重新配置日志（子进程独立配置）
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
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

        # 子进程级别强制清理：确保同名 worker 注册不存在（双重保护）
        _force_cleanup_worker(
            redis_conn,
            worker_name,
            process_logger=process_logger,
        )

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

        # 强制清理当前主机残留的 worker 注册（终止残留进程并删除注册）
        cleaned_count = _cleanup_all_stale_workers_for_host(redis_conn, force=True)
        if cleaned_count > 0:
            logger.info(f"✓ 已清理 {cleaned_count} 个残留 worker 注册")

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

        # 记录节流期间是否已警告，避免重复日志刷屏
        throttle_warned: List[bool] = [False for _ in range(concurrency)]

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
                    time_since_last = now - last_restart_ts[i]
                    if time_since_last < _RESTART_BACKOFF_SECONDS:
                        # 仅首次警告，避免日志刷屏
                        if not throttle_warned[i]:
                            remaining = _RESTART_BACKOFF_SECONDS - time_since_last
                            logger.warning(
                                f"⚠ Worker {i} 短时间内多次崩溃，{remaining:.1f}s 后重启"
                            )
                            throttle_warned[i] = True
                        continue

                    # 重置节流警告标志
                    throttle_warned[i] = False
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
