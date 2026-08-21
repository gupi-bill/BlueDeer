"""BlueDeer 自动恢复：指数退避重试装饰器。

P2-1 拆分自 core/healer.py。
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Any

logger = logging.getLogger("bluedeer.healer")


def auto_heal(
    fn=None,
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    circuit_breaker: Any = None,
):
    """带指数退避重试 + 可选熔断的自动恢复装饰器。

    用法:
        @auto_heal(max_retries=3)
        def unstable_service():
            ...
    """
    def decorator(inner_fn):
        @functools.wraps(inner_fn)
        def wrapper(*args: Any, **kwargs) -> Any:
            last_exc: Exception | None = None
            delay = base_delay
            for attempt in range(max_retries + 1):
                try:
                    if circuit_breaker is not None:
                        return circuit_breaker.call(inner_fn, *args, **kwargs)
                    return inner_fn(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if attempt < max_retries:
                        logger.warning(
                            "auto_heal 重试 %d/%d: %s", attempt + 1, max_retries, e
                        )
                        time.sleep(delay)
                        delay = min(delay * backoff_factor, max_delay)
                    else:
                        logger.exception("auto_heal 已达最大重试次数 %d: %s")
            raise last_exc  # type: ignore[misc]

        return wrapper

    if fn is not None:
        # 被调用为 @auto_heal（无参数）
        return decorator(fn)
    # 被调用为 @auto_heal(...)（带参数）
    return decorator
