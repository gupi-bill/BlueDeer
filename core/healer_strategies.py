"""BlueDeer 修复策略：FixStrategy 枚举 + 错误类型→策略映射 + 重试模板。

P2-1 拆分自 core/healer.py，供 healer 主模块与修复记录模块共用。
"""

from __future__ import annotations

from enum import Enum


class FixStrategy(Enum):
    """修复策略类型（P7 扩容：4 → 12 种）。

    原始 4 种：RETRY_GENERATE / FIX_ASSERTION / FIX_IMPORT / ESCALATE
    P7 扩容 8 种：FIX_DEADLOCK / FIX_DEPENDENCY / FIX_INTERFACE / FIX_PATH
                 FIX_MEMORY_LEAK / FIX_TIMEOUT / FIX_ENCODING / FIX_PERMISSION
    """

    # 原始 4 种
    RETRY_GENERATE = "retry_generate"  # 重新生成代码（语法/名称错误）
    FIX_ASSERTION = "fix_assertion"  # 修正断言期望值
    FIX_IMPORT = "fix_import"  # 补导入语句
    ESCALATE = "escalate"  # 升级告警（无法自动修复）
    # P7 扩容 8 种工程级修复
    FIX_DEADLOCK = "fix_deadlock"  # 并发死锁修复（加锁/超时）
    FIX_DEPENDENCY = "fix_dependency"  # 依赖冲突修复（版本对齐）
    FIX_INTERFACE = "fix_interface"  # 接口字段兼容（参数默认值）
    FIX_PATH = "fix_path"  # 路径兼容修复
    FIX_MEMORY_LEAK = "fix_memory_leak"  # 内存泄漏修复（加 cleanup）
    FIX_TIMEOUT = "fix_timeout"  # 超时修复（调大 timeout）
    FIX_ENCODING = "fix_encoding"  # 编码修复（utf-8）
    FIX_PERMISSION = "fix_permission"  # 权限修复（chmod）


# 错误类型 → 修复策略映射（P7 扩容：6 → 14 条）
_ERROR_STRATEGY: dict[str, FixStrategy] = {
    # 原始映射
    "SyntaxError": FixStrategy.RETRY_GENERATE,
    "NameError": FixStrategy.RETRY_GENERATE,
    "IndentationError": FixStrategy.RETRY_GENERATE,
    "AssertionError": FixStrategy.FIX_ASSERTION,
    "ImportError": FixStrategy.FIX_IMPORT,
    "ModuleNotFoundError": FixStrategy.FIX_IMPORT,
    # P7 扩容映射
    "DeadlockError": FixStrategy.FIX_DEADLOCK,
    "TimeoutError": FixStrategy.FIX_TIMEOUT,
    "asyncio.TimeoutError": FixStrategy.FIX_TIMEOUT,
    "RecursionError": FixStrategy.FIX_MEMORY_LEAK,
    "MemoryError": FixStrategy.FIX_MEMORY_LEAK,
    "UnicodeDecodeError": FixStrategy.FIX_ENCODING,
    "UnicodeEncodeError": FixStrategy.FIX_ENCODING,
    "PermissionError": FixStrategy.FIX_PERMISSION,
    "FileNotFoundError": FixStrategy.FIX_PATH,
    "DependencyError": FixStrategy.FIX_DEPENDENCY,
    "TypeError": FixStrategy.FIX_INTERFACE,
    "AttributeError": FixStrategy.FIX_INTERFACE,
}


# 代码模板（用于 RETRY_GENERATE）
_RETRY_TEMPLATE = """\
# 由 Healer 自动修复生成
# 策略: {strategy}
# 原因: {reason}

def add(a, b):
    \"\"\"返回两数之和。\"\"\"
    return a + b
"""
