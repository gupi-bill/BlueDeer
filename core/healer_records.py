"""BlueDeer 修复记录：FixRecord（历史记录）+ FixResult（单次修复结果）。

P2-1 拆分自 core/healer.py。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from core.healer_strategies import FixStrategy


@dataclass
class FixRecord:
    """修复记录。"""

    timestamp: float
    test_id: str
    strategy: str
    success: bool
    target_file: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FixResult:
    """单次修复结果。"""

    strategy: FixStrategy
    applied: bool = False  # 是否应用了修复
    detail: str = ""  # 修复详情
    target_file: str = ""
    success: bool = False  # 验证是否通过

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "applied": self.applied,
            "detail": self.detail,
            "target_file": self.target_file,
            "success": self.success,
        }
