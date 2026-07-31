"""BlueDeer 令牌桶限流器：多 key + 突发 + 阻塞获取。

evolution（网络维度 - R170）：
- 令牌桶：按固定速率补充令牌，请求消耗令牌，桶满则丢弃多余令牌
- 桶容量 = 突发上限；速率 = 平均上限
- 多 key：按 用户/IP/接口 分别维护独立桶
"""
from __future__ import annotations
import logging
import threading
import time

logger = logging.getLogger("bluedeer.ratelimit")


class _Bucket:
    __slots__ = ("tokens", "last_refill", "capacity", "rate")

    def __init__(self, capacity: float, rate: float, now: float) -> None:
        self.capacity = capacity
        self.rate = rate
        self.tokens = capacity
        self.last_refill = now

    def refill(self, now: float) -> None:
        elapsed = now - self.last_refill
        if elapsed <= 0:
            return
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

    def try_take(self, n: float, now: float) -> float:
        self.refill(now)
        if self.tokens >= n:
            return 0.0
        deficit = n - self.tokens
        if self.rate <= 0:
            return float("inf")
        return deficit / self.rate


class TokenBucketLimiter:
    def __init__(self, capacity: float, rate: float) -> None:
        if capacity <= 0:
            raise ValueError("capacity 必须 > 0")
        if rate <= 0:
            raise ValueError("rate 必须 > 0")
        self._capacity = capacity
        self._rate = rate
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._acquired = 0
        self._rejected = 0
        self._waited = 0

    def _get_bucket(self, key: str, now: float) -> _Bucket:
        b = self._buckets.get(key)
        if b is None:
            b = _Bucket(self._capacity, self._rate, now)
            self._buckets[key] = b
        return b

    def try_acquire(self, key: str, n: float = 1.0) -> bool:
        now = time.time()
        with self._lock:
            b = self._get_bucket(key, now)
            if b.try_take(n, now) <= 0:
                b.tokens -= n
                self._acquired += 1
                return True
            self._rejected += 1
            return False

    def acquire(self, key: str, n: float = 1.0, timeout: float = 30.0) -> bool:
        end = time.time() + timeout
        with self._cond:
            while True:
                now = time.time()
                b = self._get_bucket(key, now)
                wait = b.try_take(n, now)
                if wait <= 0:
                    b.tokens -= n
                    self._acquired += 1
                    return True
                remaining = end - now
                if wait >= remaining:
                    self._rejected += 1
                    return False
                self._cond.wait(wait)
                self._waited += 1

    def burst(self, key: str, tokens: float) -> bool:
        """一次性突发注入令牌（不超过 capacity）。"""
        if tokens <= 0:
            raise ValueError("tokens 必须 > 0")
        now = time.time()
        with self._lock:
            b = self._get_bucket(key, now)
            b.refill(now)
            added = min(tokens, b.capacity - b.tokens)
            if added <= 0:
                return False
            b.tokens += added
            self._cond.notify_all()
            return True

    def warmup(self, key: str, duration: float) -> float:
        """从空桶开始逐步填满，duration 秒内匀速填到 capacity。
        返回预热结束时注入的总令牌数。
        """
        if duration <= 0:
            raise ValueError("duration 必须 > 0")
        now = time.time()
        with self._lock:
            b = self._get_bucket(key, now)
            b.tokens = 0  # 清空
            b.last_refill = now
            interval = 0.1
            steps = max(1, int(duration / interval))
            per_step = self._capacity / steps
            for i in range(steps):
                b.tokens = min(b.capacity, b.tokens + per_step)
                b.last_refill = now + (i + 1) * interval
            b.tokens = b.capacity
            b.last_refill = now + duration
            self._cond.notify_all()
            return self._capacity

    def available(self, key: str) -> float:
        now = time.time()
        with self._lock:
            b = self._get_bucket(key, now)
            b.refill(now)
            return b.tokens

    def set_capacity(self, key: str, capacity: float) -> None:
        if capacity <= 0:
            raise ValueError("capacity 必须 > 0")
        now = time.time()
        with self._lock:
            b = self._get_bucket(key, now)
            b.refill(now)
            b.capacity = capacity
            b.tokens = min(b.tokens, capacity)

    def set_rate(self, key: str, rate: float) -> None:
        if rate <= 0:
            raise ValueError("rate 必须 > 0")
        now = time.time()
        with self._lock:
            b = self._get_bucket(key, now)
            b.refill(now)
            b.rate = rate

    def reset(self, key: str) -> None:
        with self._cond:
            self._buckets.pop(key, None)
            self._cond.notify_all()

    def reset_all(self) -> None:
        with self._cond:
            self._buckets.clear()
            self._cond.notify_all()

    def cleanup_idle(self, idle_seconds: float = 300.0) -> int:
        now = time.time()
        with self._lock:
            before = len(self._buckets)
            self._buckets = {
                k: b for k, b in self._buckets.items()
                if now - b.last_refill < idle_seconds
            }
            return before - len(self._buckets)

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._buckets.keys())

    def status(self) -> dict:
        with self._lock:
            return {
                "capacity": self._capacity,
                "rate": self._rate,
                "buckets": len(self._buckets),
                "acquired": self._acquired,
                "rejected": self._rejected,
                "waited": self._waited,
            }

    def key_status(self, key: str) -> dict | None:
        now = time.time()
        with self._lock:
            b = self._buckets.get(key)
            if b is None:
                return None
            b.refill(now)
            return {
                "key": key, "capacity": b.capacity, "rate": b.rate,
                "tokens": b.tokens, "last_refill": b.last_refill,
            }
