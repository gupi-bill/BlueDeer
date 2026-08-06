"""BlueDeer 信号量池：多 key 计数信号量 + 容量管理。

evolution（并发维度 - R176）：
- threading.Semaphore 单一全局，无法按 key 限流（如每个 API key 独立并发上限）
- 信号量池：每个 key 独立信号量，配置可统一也可按 key 覆盖
- acquire/release/try_acquire/上下文管理器
- 支持容量动态调整：扩容直接加 permit，缩容等到下次 release 时回收
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("bluedeer.sema")


@dataclass
class _Sema:
    permits: int
    capacity: int
    waiters: int = 0
    acquired: int = 0
    released: int = 0
    rejected: int = 0


class SemaphorePool:
    """多 key 计数信号量池。

    用法：
        pool = SemaphorePool(default_capacity=10)
        with pool.acquire_ctx("api-key-1"):
            ...do work...
        if pool.try_acquire("api-key-2"):
            try:
                ...
            finally:
                pool.release("api-key-2")
        pool.set_capacity("api-key-1", 5)
    """

    def __init__(self, default_capacity: int = 10) -> None:
        if default_capacity < 1:
            raise ValueError("default_capacity 必须 >= 1")
        self._default = default_capacity
        self._semas: dict[str, _Sema] = {}
        self._lock = threading.RLock()
        self._conds: dict[str, threading.Condition] = {}

    def _get_sema(self, key: str) -> _Sema:
        s = self._semas.get(key)
        if s is None:
            s = _Sema(permits=self._default, capacity=self._default)
            self._semas[key] = s
            self._conds[key] = threading.Condition(self._lock)
        return s

    def acquire(self, key: str, timeout: float = None) -> bool:
        with self._lock:
            s = self._get_sema(key)
            cond = self._conds[key]
            s.waiters += 1
            end = None if timeout is None else time.time() + timeout
            try:
                while s.permits <= 0:
                    if end is None:
                        cond.wait()
                    else:
                        rem = end - time.time()
                        if rem <= 0:
                            return False
                        cond.wait(rem)
                s.permits -= 1
                s.acquired += 1
                return True
            finally:
                s.waiters -= 1

    def try_acquire(self, key: str) -> bool:
        with self._lock:
            s = self._get_sema(key)
            if s.permits <= 0:
                s.rejected += 1
                return False
            s.permits -= 1
            s.acquired += 1
            return True

    def release(self, key: str, n: int = 1) -> int:
        if n <= 0:
            raise ValueError("n 必须 > 0")
        with self._lock:
            s = self._semas.get(key)
            if s is None:
                return 0
            add = min(n, s.capacity - s.permits)
            s.permits += add
            s.released += add
            self._conds[key].notify(n=min(n, s.waiters) if s.waiters else 1)
            return s.permits

    def acquire_ctx(self, key: str, timeout: float = None) -> Any:
        class _Ctx:
            def __init__(self, pool, k, t):
                self._pool = pool
                self._key = k
                self._timeout = t
                self._got = False

            def __enter__(self):
                self._got = self._pool.acquire(self._key, timeout=self._timeout)
                return self._got

            def __exit__(self, exc_type, exc, tb):
                if self._got:
                    self._pool.release(self._key)
                return False

        return _Ctx(self, key, timeout)

    def set_capacity(self, key: str, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity 必须 >= 1")
        with self._lock:
            s = self._get_sema(key)
            old_cap = s.capacity
            occupied = old_cap - s.permits
            occupied = max(occupied, 0)
            s.capacity = capacity
            if capacity >= old_cap:
                diff = capacity - old_cap
                s.permits += diff
                if diff > 0:
                    self._conds[key].notify(diff)
            else:
                new_permits = max(0, capacity - occupied)
                s.permits = new_permits

    def resize(self, key: str, new_capacity: int) -> int:
        """调整信号量容量。返回调整后的 permits 数。
        扩容立即增加可用 permit；缩容超出的 permit 被回收。
        """
        self.set_capacity(key, new_capacity)
        return self.available(key)

    def auto_scale(self, factor: float) -> dict[str, int]:
        """按比例缩放所有信号量容量。factor > 1 扩容，0 < factor < 1 缩容。
        返回 {key: 新 capacity} 映射。
        """
        if factor <= 0:
            raise ValueError("factor 必须 > 0")
        with self._lock:
            result = {}
            for key, s in list(self._semas.items()):
                old_cap = s.capacity
                new_cap = max(1, int(old_cap * factor))
                occupied = old_cap - s.permits
                occupied = max(occupied, 0)
                s.capacity = new_cap
                if new_cap >= old_cap:
                    diff = new_cap - old_cap
                    s.permits += diff
                else:
                    s.permits = max(0, new_cap - occupied)
                result[key] = new_cap
            return result

    def get_capacity(self, key: str) -> int:
        with self._lock:
            s = self._semas.get(key)
            return s.capacity if s else self._default

    def available(self, key: str) -> int:
        with self._lock:
            s = self._semas.get(key)
            return s.permits if s else self._default

    def waiters(self, key: str) -> int:
        with self._lock:
            s = self._semas.get(key)
            return s.waiters if s else 0

    def reset(self, key: str) -> bool:
        with self._lock:
            s = self._semas.get(key)
            if s is None:
                return False
            s.permits = s.capacity
            self._conds[key].notify_all()
            return True

    def reset_all(self) -> None:
        with self._lock:
            for k, s in self._semas.items():
                s.permits = s.capacity
                self._conds[k].notify_all()

    def remove(self, key: str) -> bool:
        with self._lock:
            if key in self._semas:
                del self._semas[key]
                del self._conds[key]
                return True
            return False

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._semas.keys())

    def cleanup_idle(self) -> int:
        with self._lock:
            before = len(self._semas)
            to_remove = [
                k
                for k, s in self._semas.items()
                if s.permits >= s.capacity and s.waiters == 0
            ]
            for k in to_remove:
                del self._semas[k]
                del self._conds[k]
            return before - len(self._semas)

    def status(self) -> dict:
        with self._lock:
            return {
                "default_capacity": self._default,
                "keys": len(self._semas),
                "details": {
                    k: {
                        "permits": s.permits,
                        "capacity": s.capacity,
                        "waiters": s.waiters,
                        "acquired": s.acquired,
                        "released": s.released,
                        "rejected": s.rejected,
                    }
                    for k, s in self._semas.items()
                },
            }

    def key_status(self, key: str) -> dict | None:
        with self._lock:
            s = self._semas.get(key)
            if s is None:
                return None
            return {
                "key": key,
                "permits": s.permits,
                "capacity": s.capacity,
                "waiters": s.waiters,
                "acquired": s.acquired,
                "released": s.released,
                "rejected": s.rejected,
            }
