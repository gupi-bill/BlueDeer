"""BlueDeer 对象池：复用昂贵对象 + 动态扩缩容。

evolution（数据维度 - R192）：
- DB 连接、HTTP 客户端、大对象创建/销毁成本高
- 每次用完即丢浪费资源；对象池预创建 + 借出归还
- 配合 max_size 上限防止失控，min_size 保持热备
- 借出超时可等待或抛异常
- 归还时验证对象有效性，失效则丢弃
- 后台清理 idle 过久的对象（节省内存）
- 典型用途：连接池、线程池、字符串池
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import threading
import time
from collections.abc import Callable
from typing import Any


class _Pooled:
    __slots__ = ("created_at", "last_used", "obj", "use_count")

    def __init__(self, obj: Any) -> None:
        self.obj = obj
        self.created_at = time.time()
        self.last_used = self.created_at
        self.use_count = 0


class ObjectPool:
    """通用对象池。

    用法：
        def make_conn():
            return MyConnection(...)
        def check(conn):
            return conn.is_alive()
        pool = ObjectPool(factory=make_conn, validator=check,
                          min_size=2, max_size=10)
        with pool.acquire() as conn:
            conn.query(...)
        # 自动归还
    """

    def __init__(
        self,
        factory: Callable[[], Any],
        validator: Callable[[Any], bool] | None = None,
        destroyer: Callable[[Any], None] | None = None,
        min_size: int = 0,
        max_size: int = 10,
        max_idle: float | None = None,
        acquire_timeout: float | None = None,
    ) -> None:
        if max_size < 1:
            raise ValueError("max_size 必须 >= 1")
        if min_size < 0 or min_size > max_size:
            raise ValueError("min_size 必须 0 <= min_size <= max_size")
        self._factory = factory
        self._validator = validator
        self._destroyer = destroyer
        self._min = min_size
        self._max = max_size
        self._max_idle = max_idle
        self._acquire_timeout = acquire_timeout
        # 空闲池：list[_Pooled]
        self._idle: list[_Pooled] = []
        self._active: set[int] = set()  # 借出对象的 id 集合
        self._active_objs: dict[int, _Pooled] = {}
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._closed = False
        self._stats = {
            "created": 0,
            "acquired": 0,
            "released": 0,
            "evicted_invalid": 0,
            "evicted_idle": 0,
            "acquire_timeout": 0,
        }
        # 预热
        with self._lock:
            for _ in range(self._min):
                self._idle.append(self._make_one())

    def __len__(self) -> int:
        with self._lock:
            return len(self._idle) + len(self._active_objs)

    @property
    def idle_size(self) -> int:
        with self._lock:
            return len(self._idle)

    @property
    def active_size(self) -> int:
        with self._lock:
            return len(self._active_objs)

    def _make_one(self) -> _Pooled:
        obj = self._factory()
        self._stats["created"] += 1
        return _Pooled(obj)

    def acquire(self, timeout: float | None = None) -> Any:
        """借出对象。无可用对象且未达 max 时创建；已达 max 时等待。"""
        if timeout is None:
            timeout = self._acquire_timeout
        with self._cond:
            if self._closed:
                raise RuntimeError("对象池已关闭")
            end = None if timeout is None else time.time() + timeout
            while True:
                # 尝试从空闲池取
                while self._idle:
                    p = self._idle.pop()
                    # 验证有效性
                    if self._validator is not None:
                        try:
                            if not self._validator(p.obj):
                                self._destroy(p)
                                self._stats["evicted_invalid"] += 1
                                continue
                        except Exception:
                            self._destroy(p)
                            self._stats["evicted_invalid"] += 1
                            continue
                    p.last_used = time.time()
                    p.use_count += 1
                    self._active_objs[id(p.obj)] = p
                    self._stats["acquired"] += 1
                    return p.obj
                # 没空闲，且未达上限：创建新的
                if len(self._active_objs) < self._max:
                    p = self._make_one()
                    p.last_used = time.time()
                    p.use_count += 1
                    self._active_objs[id(p.obj)] = p
                    self._stats["acquired"] += 1
                    return p.obj
                # 达上限：等待归还
                if timeout is None:
                    self._cond.wait()
                else:
                    if end is None:
                        break
                    rem = end - time.time()
                    if rem <= 0:
                        self._stats["acquire_timeout"] += 1
                        raise TimeoutError("acquire 超时")
                    self._cond.wait(rem)
                if self._closed:
                    raise RuntimeError("对象池已关闭")

    def release(self, obj: Any, broken: bool = False) -> None:
        """归还对象。broken=True 表示对象已损坏，应丢弃。"""
        with self._cond:
            oid = id(obj)
            p = self._active_objs.pop(oid, None)
            if p is None:
                return  # 不在池中，忽略
            self._stats["released"] += 1
            if self._closed or broken:
                self._destroy(p)
                if broken:
                    self._stats["evicted_invalid"] += 1
                # 唤醒等待者（可能要新建）
                self._cond.notify()
                return
            # 验证
            if self._validator is not None:
                try:
                    if not self._validator(p.obj):
                        self._destroy(p)
                        self._stats["evicted_invalid"] += 1
                        self._cond.notify()
                        return
                except Exception:
                    self._destroy(p)
                    self._stats["evicted_invalid"] += 1
                    self._cond.notify()
                    return
            p.last_used = time.time()
            self._idle.append(p)
            self._cond.notify()

    def _destroy(self, p: _Pooled) -> None:
        if self._destroyer is not None:
            try:
                self._destroyer(p.obj)
            except Exception:
                logger.exception("Exception in block")

    def acquire_ctx(self, timeout: float | None = None) -> Any:
        """上下文管理器：自动归还。"""

        class _Ctx:
            def __init__(self, pool, t):
                self._pool = pool
                self._timeout = t
                self._obj = None
                self._broken = False

            def __enter__(self):
                self._obj = self._pool.acquire(timeout=self._timeout)
                return self._obj

            def __exit__(self, exc_type, exc, tb):
                if self._obj is not None:
                    self._pool.release(
                        self._obj, broken=self._broken or exc is not None
                    )
                return False

            def mark_broken(self) -> None:
                self._broken = True

        return _Ctx(self, timeout)

    def shrink(self) -> int:
        """收缩到 min_size。返回清理数。"""
        with self._lock:
            n = 0
            while len(self._idle) > self._min:
                p = self._idle.pop()
                self._destroy(p)
                self._stats["evicted_idle"] += 1
                n += 1
            return n

    def evict_idle(self, max_idle: float | None = None) -> int:
        """清理 idle 超过 max_idle 的对象（保留 min_size）。"""
        if max_idle is None:
            max_idle = self._max_idle
        if max_idle is None:
            return 0
        now = time.time()
        with self._lock:
            n = 0
            keep: list[_Pooled] = []
            for p in self._idle:
                if now - p.last_used > max_idle and len(keep) >= self._min:
                    self._destroy(p)
                    self._stats["evicted_idle"] += 1
                    n += 1
                else:
                    keep.append(p)
            self._idle = keep
            return n

    def close(self) -> None:
        """关闭池：销毁所有空闲对象。"""
        with self._lock:
            self._closed = True
            for p in self._idle:
                self._destroy(p)
            self._idle.clear()
            self._cond.notify_all()

    def leak_detect(self, max_age: float = 300.0) -> list[tuple[int, Any, float]]:
        """检测借出超过 max_age 秒的对象。

        返回 [(对象ID, 对象, 已借出秒数)]。
        """
        with self._lock:
            now = time.time()
            leaks = []
            for oid, p in self._active_objs.items():
                elapsed = now - p.last_used
                if elapsed > max_age:
                    leaks.append((oid, p.obj, elapsed))
            return leaks

    def __contains__(self, obj: Any) -> bool:
        with self._lock:
            return id(obj) in self._active_objs or any(p.obj is obj for p in self._idle)

    def status(self) -> dict:
        with self._lock:
            return {
                "min_size": self._min,
                "max_size": self._max,
                "idle": len(self._idle),
                "active": len(self._active_objs),
                "total": len(self._idle) + len(self._active_objs),
                "closed": self._closed,
                **self._stats,
            }
