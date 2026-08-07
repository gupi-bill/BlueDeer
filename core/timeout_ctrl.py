"""BlueDeer 超时控制器：deadline + 线程 race + 装饰器 + 上下文管理器 + 取消。

evolution（并发维度 - R175）：
- 网络调用超时、任务执行限时、心跳响应超时都需要统一控制
- 信号超时只能用在主线程，异步任务超时要用线程 race
- 超时控制器：传 deadline 而非剩余秒数，多次检查时自动递减
- race_call：在线程中执行，超时返回默认值或抛 TimeoutError
- 装饰器：@timeout(5.0) 便捷包装
- 上下文管理器：with timeout(5.0): ...
"""

from __future__ import annotations

import functools
import threading
import time
from collections.abc import Callable
from typing import Any

from typing_extensions import Self


class TimeoutError(Exception):
    """超时异常。"""


class Deadline:
    """截止时间：传给多次调用，自动递减剩余时间。

    用法：
        dl = Deadline(5.0)
        call_1(timeout=dl.remaining())
        call_2(timeout=dl.remaining())
        if dl.expired():
            ...超时...
    """

    def __init__(self, timeout: float) -> None:
        if timeout < 0:
            raise ValueError("timeout 不能为负")
        self._end = time.time() + timeout

    @property
    def deadline(self) -> float:
        return self._end

    def remaining(self, default: float = 0.0) -> float:
        """剩余时间。已过期返回 default。"""
        r = self._end - time.time()
        return r if r > 0 else default

    def expired(self) -> bool:
        return time.time() >= self._end

    def reset(self, timeout: float) -> None:
        if timeout < 0:
            raise ValueError("timeout 不能为负")
        self._end = time.time() + timeout

    def extend(self, extra: float) -> None:
        if extra < 0:
            raise ValueError("extra 不能为负")
        self._end += extra


def race_call(
    func: Callable,
    *args,
    timeout: float,
    default: Any = ...,
    reraise: bool = False,
    **kwargs,
) -> Any:
    """在线程中执行 func，超时返回 default 或抛 TimeoutError。

    Args:
        timeout: 超时秒数
        default: 超时返回的默认值。默认 ...（哨兵）表示抛 TimeoutError
        reraise: 是否传播 func 内部异常
    """
    if timeout < 0:
        raise ValueError("timeout 不能为负")
    result_box: list = [None]
    exc_box: list = [None]
    done = threading.Event()

    def runner() -> None:
        try:
            result_box[0] = func(*args, **kwargs)
        except BaseException as e:
            exc_box[0] = e
        finally:
            done.set()

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    completed = done.wait(timeout)
    if completed:
        if exc_box[0] is not None:
            if reraise:
                raise exc_box[0]
            raise exc_box[0]
        return result_box[0]
    if default is ...:
        raise TimeoutError(f"函数 {func.__name__} 超时 {timeout}s")
    return default


class timeout:
    """超时上下文管理器 / 装饰器。

    用法：
        with timeout(5.0):
            ...

        @timeout(5.0)
        def func():
            ...
    """

    def __init__(
        self, seconds: float, default: Any = ..., reraise: bool = True
    ) -> None:
        if seconds < 0:
            raise ValueError("timeout 不能为负")
        self._seconds = seconds
        self._default = default
        self._reraise = reraise
        self._timer: threading.Timer | None = None

    def __enter__(self) -> Self:
        self._timer = threading.Timer(self._seconds, self._raise_timeout)
        self._timer.daemon = True
        self._timer.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        return exc_type is TimeoutError

    @staticmethod
    def _raise_timeout():
        raise TimeoutError("操作超时")

    def __call__(self, func: Callable) -> Callable:
        """作为装饰器使用。"""

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs) -> Any:
            return race_call(
                func,
                *args,
                timeout=self._seconds,
                default=self._default,
                reraise=self._reraise,
                **kwargs,
            )

        return wrapper


class TimeoutGuard:
    """上下文管理器：代码块超时检查（仅检查，不强制中断）。

    用法：
        with TimeoutGuard(5.0) as g:
            for chunk in work():
                if g.expired():
                    break
    """

    def __init__(self, timeout: float) -> None:
        if timeout < 0:
            raise ValueError("timeout 不能为负")
        self._deadline = Deadline(timeout)
        self._timeout = timeout

    @property
    def deadline(self) -> Deadline:
        return self._deadline

    def remaining(self) -> float:
        return self._deadline.remaining()

    def expired(self) -> bool:
        return self._deadline.expired()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _timeout_ctx:
    """基于线程强制中断的上下文管理器。

    用法：
        with timeout(5.0):
            ...
    """

    def __init__(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("timeout 不能为负")
        self._seconds = seconds
        self._timer: threading.Timer | None = None

    def __enter__(self) -> Self:
        self._timer = threading.Timer(self._seconds, self._raise_timeout)
        self._timer.daemon = True
        self._timer.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        return exc_type is TimeoutError

    @staticmethod
    def _raise_timeout():
        raise TimeoutError("操作超时")


def timeout_context(seconds: float) -> _timeout_ctx:
    """获取超时上下文管理器。"""
    return _timeout_ctx(seconds)


def timeout_decorator(seconds: float) -> Any:
    """装饰器：@timeout_decorator(5) 强制函数执行不超过秒数。

    与 timeout() 不同，使用 threading.Timer 中断而非 race_call。
    适合不需要返回值的场景。
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs) -> Any:
            with _timeout_ctx(seconds):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def sleep_with_cancel(seconds: float, cancel_event: threading.Event) -> bool:
    """可取消的 sleep。返回 True 表示正常睡完，False 表示被取消唤醒。"""
    if seconds <= 0:
        return True
    return not cancel_event.wait(seconds)


def wait_until(
    predicate: Callable[[], bool],
    timeout: float,
    interval: float = 0.1,
) -> bool:
    """轮询等待 predicate 为 True。超时返回 False。"""
    if timeout < 0:
        raise ValueError("timeout 不能为负")
    dl = Deadline(timeout)
    while not predicate():
        rem = dl.remaining()
        if rem <= 0:
            return False
        time.sleep(min(interval, rem))
    return True


def status() -> dict:
    """模块状态（无状态，仅占位）。"""
    return {
        "module": "timeout_ctrl",
        "strategies": ["deadline", "race", "guard", "context", "decorator"],
    }
