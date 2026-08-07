"""BlueDeer 优雅停机控制器：拒绝新任务 + 等待在途完成 + 超时强制。

evolution（并发维度 - R177）：
- 服务停机时不能立即 kill 线程，否则会丢数据和半完成请求
- 优雅停机：1) 拒绝新任务进入 2) 等待在途任务完成 3) 超时强制返回
- 与线程池解耦：可包装任意工作线程池或任务管理器
- 状态机：RUNNING → DRAINING → TERMINATED
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("bluedeer.shutdown")

# 状态
RUNNING = "running"


def drain(connections: list, timeout: float = 30.0) -> bool:
    end = time.time() + timeout
    for conn in connections:
        remaining = end - time.time()
        if remaining <= 0:
            return False
        active = (
            conn.active
            if hasattr(conn, "active")
            else conn.is_active() if hasattr(conn, "is_active") else 0
        )
        while active > 0 and remaining > 0:
            time.sleep(0.1)
            remaining = end - time.time()
            active = (
                conn.active
                if hasattr(conn, "active")
                else conn.is_active() if hasattr(conn, "is_active") else 0
            )
    return True


def shutdown_with_timeout(seconds: float) -> bool:
    gs = GracefulShutdown()
    return gs.shutdown(timeout=seconds)


DRAINING = "draining"
TERMINATED = "terminated"


class ShuttingDownError(Exception):
    """停机中拒绝新任务。"""


class GracefulShutdown:
    """优雅停机控制器。

    用法：
        gs = GracefulShutdown()
        # 工作线程
        def worker():
            with gs.task_ctx():
                do_work()
        # 提交任务前检查
        if gs.accept():
            submit(task)
        else:
            ...拒绝...
        # 停机
        gs.shutdown(timeout=30.0)
    """

    def __init__(self) -> None:
        self._state = RUNNING
        self._active = 0
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._shutdown_event = threading.Event()
        # 统计
        self._total_accepted = 0
        self._total_rejected = 0
        self._total_completed = 0
        self._shutdown_at = 0.0
        self._terminated_at = 0.0

    @property
    def state(self) -> str:
        return self._state

    def is_running(self) -> bool:
        return self._state == RUNNING

    def is_draining(self) -> bool:
        return self._state == DRAINING

    def is_terminated(self) -> bool:
        return self._state == TERMINATED

    def accept(self) -> bool:
        """检查是否接受新任务。RUNNING 才接受。"""
        with self._lock:
            if self._state == RUNNING:
                self._total_accepted += 1
                return True
            self._total_rejected += 1
            return False

    def require_accept(self) -> None:
        """要求接受，否则抛 ShuttingDownError。"""
        if not self.accept():
            raise ShuttingDownError("服务正在停机，拒绝新任务")

    def begin_task(self) -> bool:
        """开始一个任务（增加活跃计数）。返回是否成功开始。
        DRAINING 后不再允许新任务开始。"""
        with self._cond:
            if self._state != RUNNING:
                self._total_rejected += 1
                return False
            self._active += 1
            self._total_accepted += 1
            return True

    def end_task(self) -> None:
        """结束一个任务（减少活跃计数）。"""
        with self._cond:
            if self._active > 0:
                self._active -= 1
            self._total_completed += 1
            if self._state == DRAINING and self._active == 0:
                self._cond.notify_all()

    def task_ctx(self) -> Any:
        """上下文管理器：自动 begin/end。"""

        class _Ctx:
            def __init__(self, gs):
                self._gs = gs
                self._ok = False

            def __enter__(self):
                self._ok = self._gs.begin_task()
                return self._ok

            def __exit__(self, exc_type, exc, tb):
                if self._ok:
                    self._gs.end_task()
                return False

        return _Ctx(self)

    def active_count(self) -> int:
        with self._lock:
            return self._active

    def shutdown(self, timeout: float | None = None) -> bool:
        """发起停机并等待在途任务完成。返回是否在超时前完成。

        - 拒绝新任务
        - 等待 active 归零
        - 超时则强制 TERMINATED（不真的中断任务，仅状态切换）
        """
        with self._cond:
            if self._state == TERMINATED:
                return True
            if self._state == RUNNING:
                self._state = DRAINING
                self._shutdown_at = time.time()
                self._shutdown_event.set()
                self._cond.notify_all()
            # 等待 active 归零
            if self._active == 0:
                self._state = TERMINATED
                self._terminated_at = time.time()
                return True
            if timeout is None:
                while self._active > 0:
                    self._cond.wait()
                self._state = TERMINATED
                self._terminated_at = time.time()
                return True
            end = time.time() + timeout
            while self._active > 0:
                remaining = end - time.time()
                if remaining <= 0:
                    # 超时：强制切到 TERMINATED（任务仍在跑，但状态变了）
                    self._state = TERMINATED
                    self._terminated_at = time.time()
                    logger.warning("停机超时，仍有 %d 个活跃任务", self._active)
                    return False
                self._cond.wait(remaining)
            self._state = TERMINATED
            self._terminated_at = time.time()
            return True

    def force_terminate(self) -> int:
        """立即强制终止（不等待）。返回剩余活跃数。"""
        with self._cond:
            self._state = TERMINATED
            self._terminated_at = time.time()
            self._cond.notify_all()
            return self._active

    def wait_shutdown(self, timeout: float | None = None) -> bool:
        """等待 TERMINATED 状态。"""
        with self._cond:
            if self._state == TERMINATED:
                return True
            if timeout is None:
                while self._state != TERMINATED:
                    self._cond.wait()
                return True
            end = time.time() + timeout
            while self._state != TERMINATED:
                remaining = end - time.time()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)
            return True

    def reset(self) -> None:
        """重置回 RUNNING（用于测试或重启）。"""
        with self._cond:
            self._state = RUNNING
            self._active = 0
            self._shutdown_event.clear()
            self._shutdown_at = 0.0
            self._terminated_at = 0.0

    def status(self) -> dict:
        with self._lock:
            return {
                "state": self._state,
                "active": self._active,
                "total_accepted": self._total_accepted,
                "total_rejected": self._total_rejected,
                "total_completed": self._total_completed,
                "shutdown_at": self._shutdown_at,
                "terminated_at": self._terminated_at,
            }


class TaskRunner:
    """带优雅停机的任务执行器（单线程顺序执行）。

    用法：
        runner = TaskRunner()
        runner.start()
        runner.submit(task1)
        runner.submit(task2)
        runner.shutdown(timeout=5.0)
    """

    def __init__(self) -> None:
        self._gs = GracefulShutdown()
        self._queue: list = []
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._thread: threading.Thread | None = None
        self._executed = 0

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="task-runner"
        )
        self._thread.start()

    def submit(self, task: Callable, *args: Any, **kwargs) -> bool:
        """提交任务。停机中拒绝。返回是否接受。"""
        if not self._gs.accept():
            return False
        with self._cond:
            self._queue.append((task, args, kwargs))
            self._cond.notify()
        return True

    def _loop(self) -> None:
        while True:
            with self._cond:
                while not self._queue and self._gs.is_running():
                    self._cond.wait(timeout=0.1)
                if not self._queue:
                    if self._gs.is_draining() or self._gs.is_terminated():
                        return
                    continue
                task, args, kwargs = self._queue.pop(0)
            self._gs.begin_task()
            try:
                task(*args, **kwargs)
            except Exception as e:
                logger.warning("任务异常: %s", e)
            finally:
                self._gs.end_task()
                self._executed += 1

    def shutdown(self, timeout: float = 30.0) -> bool:
        """停机：拒绝新任务 + 等待队列清空 + 等待活跃完成。"""
        ok = self._gs.shutdown(timeout=timeout)
        if self._thread is not None:
            with self._cond:
                self._cond.notify_all()
            self._thread.join(timeout=max(0.5, timeout))
            self._thread = None
        return ok

    def status(self) -> dict:
        s = self._gs.status()
        s["queue_size"] = len(self._queue)
        s["executed"] = self._executed
        return s
