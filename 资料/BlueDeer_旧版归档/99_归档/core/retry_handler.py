"""BlueDeer Retry Handler: exponential backoff, jitter, retry policies."""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

logger = logging.getLogger("bluedeer.retry")

T = TypeVar("T")


class RetryStrategy(Enum):
    FIXED = "fixed"
    EXPONENTIAL = "exponential"
    LINEAR = "linear"


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter: bool = True
    backoff_factor: float = 2.0
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def get_delay(self, attempt: int) -> float:
        if self.strategy == RetryStrategy.FIXED:
            delay = self.base_delay
        elif self.strategy == RetryStrategy.LINEAR:
            delay = self.base_delay * attempt
        else:
            delay = self.base_delay * (self.backoff_factor ** (attempt - 1))
        delay = min(delay, self.max_delay)
        if self.jitter:
            delay = delay * (0.5 + random.random())
        return delay


@dataclass
class RetryResult:
    success: bool
    attempts: int
    last_error: Exception | None = None
    total_time: float = 0.0


class RetryHandler:
    """Executes callables with retry logic."""

    def __init__(self, policy: RetryPolicy | None = None) -> None:
        self._policy = policy or RetryPolicy()

    async def call(self, fn: Callable[[], Coroutine[Any, Any, T]]) -> RetryResult:
        policy = self._policy
        start = time.monotonic()
        last_error: Exception | None = None
        for attempt in range(1, policy.max_attempts + 1):
            try:
                await fn()
                return RetryResult(
                    success=True,
                    attempts=attempt,
                    total_time=time.monotonic() - start,
                )
            except policy.retryable_exceptions as e:
                last_error = e
                logger.warning(
                    "Attempt %d/%d failed: %s", attempt, policy.max_attempts, e
                )
                if attempt < policy.max_attempts:
                    delay = policy.get_delay(attempt)
                    logger.info("Retrying in %.2fs...", delay)
                    await asyncio_sleep(delay)
        return RetryResult(
            success=False,
            attempts=policy.max_attempts,
            last_error=last_error,
            total_time=time.monotonic() - start,
        )

    async def call_with_result(
        self, fn: Callable[[], Coroutine[Any, Any, T]]
    ) -> tuple[T, RetryResult]:
        policy = self._policy
        start = time.monotonic()
        last_error: Exception | None = None
        result_val: T | None = None
        for attempt in range(1, policy.max_attempts + 1):
            try:
                result_val = await fn()
                return (
                    result_val,
                    RetryResult(
                        success=True,
                        attempts=attempt,
                        total_time=time.monotonic() - start,
                    ),
                )
            except policy.retryable_exceptions as e:
                last_error = e
                logger.warning(
                    "Attempt %d/%d failed: %s", attempt, policy.max_attempts, e
                )
                if attempt < policy.max_attempts:
                    delay = policy.get_delay(attempt)
                    logger.info("Retrying in %.2fs...", delay)
                    await asyncio_sleep(delay)
        raise last_error or RuntimeError("All retry attempts failed")


async def asyncio_sleep(delay: float) -> None:
    import asyncio

    await asyncio.sleep(delay)


__all__ = [
    "RetryHandler",
    "RetryPolicy",
    "RetryResult",
    "RetryStrategy",
]
