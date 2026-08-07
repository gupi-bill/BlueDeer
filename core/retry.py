"""任务重试策略：exponential backoff + max_retries。

配合 Harness._on_task_failed 在失败时按指数退避重新下发同一 Agent。
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from core.config import get_config

logger = logging.getLogger("bluedeer.retry")


@dataclass(slots=True)
class RetryState:
    task_id: str
    attempt: int = 0
    last_attempt_time: float = 0.0
    next_retry_time: float = 0.0
    error: str = ""
    exhausted: bool = False


class RetryManager:
    def __init__(self) -> None:
        self._states: dict[str, RetryState] = {}

    def record_failure(self, task_id: str, error: str) -> RetryState:
        cfg = get_config().task
        state = self._states.get(task_id)
        if state is None:
            state = RetryState(task_id=task_id)
            self._states[task_id] = state

        state.attempt += 1
        state.last_attempt_time = time.time()
        state.error = error

        if not cfg.retry_enabled or state.attempt >= cfg.retry_max_attempts:
            state.exhausted = True
            logger.info(
                "任务 %s 重试已达上限 %d/%d",
                task_id,
                state.attempt,
                cfg.retry_max_attempts,
            )
            return state

        delay = self._compute_delay(state.attempt, cfg)
        state.next_retry_time = state.last_attempt_time + delay
        logger.info(
            "任务 %s 第 %d/%d 次重试，等待 %.1fs",
            task_id,
            state.attempt,
            cfg.retry_max_attempts,
            delay,
        )
        return state

    def record_success(self, task_id: str) -> None:
        self._states.pop(task_id, None)

    def due_for_retry(self) -> list[RetryState]:
        now = time.time()
        return [
            s
            for s in self._states.values()
            if not s.exhausted and s.next_retry_time <= now
        ]

    def retry_summary(self) -> dict[str, Any]:
        return {
            task_id: {
                "attempt": s.attempt,
                "next_retry": s.next_retry_time,
                "remaining": max(0, get_config().task.retry_max_attempts - s.attempt),
                "exhausted": s.exhausted,
                "error": s.error[:120] if s.error else "",
            }
            for task_id, s in self._states.items()
        }

    @staticmethod
    def _compute_delay(attempt: int, cfg: Any) -> float:
        return compute_backoff_delay(
            attempt,
            cfg.retry_base_delay,
            cfg.retry_max_delay,
            cfg.retry_jitter,
        )


def compute_backoff_delay(
    attempt: int,
    base_delay: float,
    max_delay: float,
    jitter: bool = True,
) -> float:
    """指数退避 + full jitter 延迟计算。

    Args:
        attempt: 第几次尝试（从 1 开始）。
        base_delay: 基础延迟秒数。
        max_delay: 最大延迟上限秒数。
        jitter: 是否添加 0.5x~1.5x 随机抖动（默认 True）。

    Returns:
        本次应等待的秒数。
    """
    delay = base_delay * (2 ** (attempt - 1))
    delay = min(delay, max_delay)
    if jitter:
        delay *= 0.5 + random.random()
    return delay


def retry_with_backoff(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    **kwargs: Any,
) -> tuple[Any, int, float]:
    """指数退避重试包装。

    Args:
        func: 要重试的函数。
        max_retries: 最大重试次数（默认 3）。
        base_delay: 基础延迟秒数（默认 1）。
        max_delay: 最大延迟秒数（默认 60）。
        jitter: 是否添加 +/-10% 随机抖动（默认 True）。

    Returns:
        (result, attempts, total_time)
    """
    start = time.time()
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            result = func(*args, **kwargs)
            return (result, attempt + 1, time.time() - start)
        except Exception as e:
            last_exc = e
            if attempt >= max_retries:
                time.time() - start
                raise RuntimeError(f"重试 {max_retries} 次后仍失败: {e}") from e
            delay = base_delay * (2**attempt)
            delay = min(delay, max_delay)
            if jitter:
                delay *= random.uniform(0.9, 1.1)
            logger.debug("重试 %d/%d, 等待 %.2fs", attempt + 1, max_retries, delay)
            time.sleep(delay)
    raise RuntimeError("不可达") from last_exc
