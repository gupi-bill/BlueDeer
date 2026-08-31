"""BlueDeer 滑动窗口限流器：时间窗口统计 + 多 key + 加权。

evolution（网络维度 - R171）：
- 滑动窗口按"过去 N 秒内请求数"统计，适合硬上限（如 100 次/分钟）
- 每个请求记录时间戳，滑出窗口的丢弃
- 支持加权：不同请求消耗不同配额
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger("bluedeer.sliding")


@dataclass
class _Window:
    timestamps: deque = field(default_factory=lambda: deque())
    weights: deque = field(default_factory=lambda: deque())
    total_weight: float = 0.0

    def prune(self, window: float, now: float) -> float:
        removed = 0.0
        cutoff = now - window
        while self.timestamps and self.timestamps[0] <= cutoff:
            self.timestamps.popleft()
            removed += self.weights.popleft()
        self.total_weight -= removed
        self.total_weight = max(self.total_weight, 0)
        return removed

    def add(self, weight: float, now: float) -> None:
        self.timestamps.append(now)
        self.weights.append(weight)
        self.total_weight += weight


class SlidingWindowLimiter:
    def __init__(
        self, window: float, max_requests: float, precision: float = 0.001
    ) -> None:
        if window <= 0:
            raise ValueError("window 必须 > 0")
        if max_requests <= 0:
            raise ValueError("max_requests 必须 > 0")
        if precision <= 0:
            raise ValueError("precision 必须 > 0")
        self._window = window
        self._max = max_requests
        self._precision = precision
        self._windows: dict[str, _Window] = {}
        self._lock = threading.RLock()
        self._acquired = 0
        self._rejected = 0
        self._pruned = 0

    def _get_window(self, key: str) -> _Window:
        w = self._windows.get(key)
        if w is None:
            w = _Window()
            self._windows[key] = w
        return w

    def try_acquire(self, key: str, weight: float = 1.0) -> bool:
        if weight <= 0:
            raise ValueError("weight 必须 > 0")
        now = time.time()
        with self._lock:
            w = self._get_window(key)
            self._pruned += w.prune(self._window, now)
            if w.total_weight + weight > self._max:
                self._rejected += 1
                return False
            w.add(weight, now)
            self._acquired += 1
            return True

    def current(self, key: str) -> float:
        now = time.time()
        with self._lock:
            w = self._windows.get(key)
            if w is None:
                return 0.0
            w.prune(self._window, now)
            return w.total_weight

    def multi_window(self, keys: dict[str, float]) -> dict[str, float]:
        """多窗口查询：{key: window_size} -> {key: current_weight}。"""
        now = time.time()
        with self._lock:
            result = {}
            for key, window_size in keys.items():
                if window_size <= 0:
                    result[key] = 0.0
                    continue
                w = self._windows.get(key)
                if w is None:
                    result[key] = 0.0
                else:
                    w.prune(window_size, now)
                    result[key] = w.total_weight
            return result

    def reset(self, key: str) -> float:
        with self._lock:
            w = self._windows.pop(key, None)
            if w is None:
                return 0.0
            return w.total_weight

    def reset_all(self) -> int:
        with self._lock:
            n = len(self._windows)
            self._windows.clear()
            return n

    def set_max(self, max_requests: float) -> None:
        if max_requests <= 0:
            raise ValueError("max_requests 必须 > 0")
        with self._lock:
            self._max = max_requests

    def set_precision(self, precision: float) -> None:
        if precision <= 0:
            raise ValueError("precision 必须 > 0")
        with self._lock:
            self._precision = precision

    def cleanup_idle(self, idle_seconds: float = 300.0) -> int:
        now = time.time()
        with self._lock:
            before = len(self._windows)
            self._windows = {
                k: w
                for k, w in self._windows.items()
                if w.timestamps and (now - w.timestamps[-1]) < idle_seconds
            }
            return before - len(self._windows)

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._windows.keys())

    def status(self) -> dict:
        with self._lock:
            return {
                "window": self._window,
                "max_requests": self._max,
                "precision": self._precision,
                "keys": len(self._windows),
                "acquired": self._acquired,
                "rejected": self._rejected,
                "pruned": self._pruned,
            }

    def key_status(self, key: str, window: float | None = None) -> dict | None:
        now = time.time()
        w_size = self._window if window is None else window
        with self._lock:
            w = self._windows.get(key)
            if w is None:
                return None
            w.prune(w_size, now)
            return {
                "key": key,
                "current": w.total_weight,
                "max": self._max,
                "window": w_size,
                "remaining": max(0, self._max - w.total_weight),
                "count": len(w.timestamps),
            }
