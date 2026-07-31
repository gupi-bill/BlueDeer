"""BlueDeer 组合限流器：令牌桶 + 滑动窗口 + 并发信号量。

evolution（并发维度 - R178）：
- 单一限流算法各有局限：
  - 令牌桶控平均速率但不控瞬时并发
  - 滑动窗口控时间窗内总量但不控瞬时并发
  - 信号量控并发但不控速率
- 组合限流器：三层防护，按优先级检查
  - 并发信号量（第一道，防止过载）
  - 令牌桶（第二道，控制平均速率）
  - 滑动窗口（第三道，控制时间窗总量）
- 所有层都通过才放行
"""

from __future__ import annotations

import logging
import threading
import time
from enum import IntEnum
from typing import Callable

from core.token_bucket import TokenBucketLimiter
from core.sliding_window import SlidingWindowLimiter
from core.semaphore_pool import SemaphorePool

logger = logging.getLogger("bluedeer.composite")


class Priority(IntEnum):
    LOW = 0
    NORMAL = 5
    HIGH = 10
    CRITICAL = 20


class CompositeLimiter:
    """组合限流器：三层防护 + 优先级调度。

    用法：
        lim = CompositeLimiter(
            max_concurrent=10,       # 最多 10 个并发
            token_capacity=100,      # 令牌桶容量 100（突发上限）
            token_rate=10.0,         # 10 令牌/秒
            window=60.0,              # 滑动窗口 60 秒
            window_max=1000,          # 60 秒内最多 1000 次
        )
        if lim.try_acquire("user-1", priority=Priority.HIGH):
            ...执行...
            lim.release("user-1")
    """

    def __init__(
        self,
        max_concurrent: int = 0,
        token_capacity: float = 0,
        token_rate: float = 0,
        window: float = 0,
        window_max: float = 0,
        priority_quotas: dict[Priority, dict] | None = None,
    ) -> None:
        self._use_semaphore = max_concurrent > 0
        self._use_token = token_capacity > 0 and token_rate > 0
        self._use_window = window > 0 and window_max > 0
        if not (self._use_semaphore or self._use_token or self._use_window):
            raise ValueError("至少要配置一种限流")
        self._semaphore = (
            SemaphorePool(default_capacity=max_concurrent)
            if self._use_semaphore else None
        )
        self._token = (
            TokenBucketLimiter(capacity=token_capacity, rate=token_rate)
            if self._use_token else None
        )
        self._window = (
            SlidingWindowLimiter(window=window, max_requests=window_max)
            if self._use_window else None
        )
        self._lock = threading.RLock()
        self._accepted = 0
        self._rejected_concurrent = 0
        self._rejected_token = 0
        self._rejected_window = 0
        self._released = 0
        self._held: dict[int, str] = {}
        # 优先级配额覆盖
        self._pq: dict[Priority, dict] = priority_quotas or {}
        self._pq_sem: dict[Priority, SemaphorePool] = {}
        self._pq_token: dict[Priority, TokenBucketLimiter] = {}
        self._pq_window: dict[Priority, SlidingWindowLimiter] = {}
        for pri, cfg in self._pq.items():
            if sem := cfg.get("max_concurrent"):
                self._pq_sem[pri] = SemaphorePool(default_capacity=sem)
            if tc := cfg.get("token_capacity"):
                self._pq_token[pri] = TokenBucketLimiter(
                    capacity=tc, rate=cfg.get("token_rate", tc)
                )
            if w := cfg.get("window"):
                self._pq_window[pri] = SlidingWindowLimiter(
                    window=w, max_requests=cfg.get("window_max", w)
                )

    def _limit_for(self, limiter, pq_map: dict, pri: Priority, key: str) -> bool:
        if pq_map and pri in pq_map:
            return pq_map[pri].try_acquire(key)
        return limiter.try_acquire(key) if limiter else True

    def _release_for(self, limiter, pq_map: dict, pri: Priority, key: str) -> None:
        if pq_map and pri in pq_map:
            pq_map[pri].release(key)
        elif limiter:
            limiter.release(key)

    def try_acquire(self, key: str = "default", priority: Priority = Priority.NORMAL) -> bool:
        with self._lock:
            if self._use_semaphore:
                if not self._limit_for(self._semaphore, self._pq_sem, priority, key):
                    self._rejected_concurrent += 1
                    return False
            if self._use_token:
                if not self._limit_for(self._token, self._pq_token, priority, key):
                    if self._use_semaphore:
                        self._release_for(self._semaphore, self._pq_sem, priority, key)
                    self._rejected_token += 1
                    return False
            if self._use_window:
                if not self._limit_for(self._window, self._pq_window, priority, key):
                    if self._use_semaphore:
                        self._release_for(self._semaphore, self._pq_sem, priority, key)
                    self._rejected_window += 1
                    return False
            self._accepted += 1
            return True

    def release(self, key: str = "default", priority: Priority = Priority.NORMAL) -> None:
        if self._use_semaphore:
            self._release_for(self._semaphore, self._pq_sem, priority, key)
        with self._lock:
            self._released += 1

    def acquire_ctx(self, key: str = "default", priority: Priority = Priority.NORMAL):
        class _Ctx:
            def __init__(self, lim, k, p):
                self._lim = lim
                self._key = k
                self._pri = p
                self._ok = False

            def __enter__(self):
                self._ok = self._lim.try_acquire(self._key, priority=self._pri)
                return self._ok

            def __exit__(self, exc_type, exc, tb):
                if self._ok:
                    self._lim.release(self._key, priority=self._pri)
                return False

        return _Ctx(self, key, priority)

    def call(self, func: Callable, *args, key: str = "default", priority: Priority = Priority.NORMAL, **kwargs):
        if not self.try_acquire(key, priority=priority):
            raise RateLimitError(f"被限流：{key} (pri={priority.name})")
        try:
            return func(*args, **kwargs)
        finally:
            self.release(key, priority=priority)

    def available_tokens(self, key: str = "default", priority: Priority | None = None) -> float:
        if priority and priority in self._pq_token:
            return self._pq_token[priority].available(key)
        if self._use_token:
            return self._token.available(key)
        return float("inf")

    def window_current(self, key: str = "default", priority: Priority | None = None) -> float:
        if priority and priority in self._pq_window:
            return self._pq_window[priority].current(key)
        if self._use_window:
            return self._window.current(key)
        return 0.0

    def available_concurrent(self, key: str = "default", priority: Priority | None = None) -> int:
        if priority and priority in self._pq_sem:
            return self._pq_sem[priority].available(key)
        if self._use_semaphore:
            return self._semaphore.available(key)
        return -1

    def reset_all(self) -> None:
        with self._lock:
            for s in self._pq_sem.values():
                s.reset_all()
            for t in self._pq_token.values():
                t.reset_all()
            for w in self._pq_window.values():
                w.reset_all()
            if self._use_semaphore:
                self._semaphore.reset_all()
            if self._use_token:
                self._token.reset_all()
            if self._use_window:
                self._window.reset_all()

    def status(self) -> dict:
        with self._lock:
            return {
                "use_semaphore": self._use_semaphore,
                "use_token": self._use_token,
                "use_window": self._use_window,
                "accepted": self._accepted,
                "released": self._released,
                "rejected_concurrent": self._rejected_concurrent,
                "rejected_token": self._rejected_token,
                "rejected_window": self._rejected_window,
                "priority_quotas": {p.name: k for p, k in self._pq.items()},
                "semaphore": self._semaphore.status() if self._use_semaphore else None,
                "token": self._token.status() if self._use_token else None,
                "window": self._window.status() if self._use_window else None,
            }


class RateLimitError(Exception):
    """被限流。"""
