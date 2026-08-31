"""BlueDeer 熔断器：CircuitBreaker + CircuitState。

P2-1 拆分自 core/healer.py。
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """熔断器：连续失败达到阈值后断开，经过恢复时间后半开尝试。"""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_retries: int = 3,
    ) -> None:
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_retries = half_open_max_retries
        self._half_open_retries = 0
        self._last_failure_time: float = 0.0

    @property
    def state(self) -> CircuitState:
        if (
            self._state == CircuitState.OPEN
            and time.time() - self._last_failure_time > self._recovery_timeout
        ):
            self._state = CircuitState.HALF_OPEN
            self._half_open_retries = 0
        return self._state

    def call(self, fn: Any, *args: Any, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            raise RuntimeError("熔断器已断开，拒绝调用")
        try:
            result = fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_retries += 1
            if self._half_open_retries >= self._half_open_max_retries:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._half_open_retries = 0
        else:
            self._failure_count = 0

    def _on_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self._failure_threshold:
            self._state = CircuitState.OPEN
