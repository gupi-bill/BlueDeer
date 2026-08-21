"""BlueDeer 修复引擎（向后兼容入口）。

P2-1 拆分为多个子模块：
- healer_records：FixRecord / FixResult
- healer_strategies：FixStrategy / _ERROR_STRATEGY / _RETRY_TEMPLATE
- healer_engine：Healer 主类
- healer_circuit：CircuitBreaker 熔断器
- healer_retry：auto_heal 指数退避装饰器
"""

from __future__ import annotations

# 向后兼容：所有原 core.healer 的公共 API 继续可从本模块导入
from core.healer_circuit import CircuitBreaker, CircuitState
from core.healer_engine import Healer
from core.healer_records import FixRecord, FixResult
from core.healer_retry import auto_heal
from core.healer_strategies import (
    _ERROR_STRATEGY,
    _RETRY_TEMPLATE,
    FixStrategy,
)
from core.test_runner import TestFailure

__all__ = [
    "_ERROR_STRATEGY",
    "_RETRY_TEMPLATE",
    "CircuitBreaker",
    "CircuitState",
    "FixRecord",
    "FixResult",
    "FixStrategy",
    "Healer",
    "TestFailure",
    "auto_heal",
]
