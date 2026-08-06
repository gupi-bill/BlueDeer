"""BlueDeer 梦境模型：质量分级 + 梦境日志 + 记忆条目 + 噩梦告警 + 梦境报告。

P2-1 拆分自 core/dream.py，供 DreamSystem 使用。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.config import get_config


class DreamQuality(Enum):
    """梦境记忆质量等级。"""

    NORMAL = "normal"  # 普通记忆
    HIGH = "high"  # 高质量（代码行数 > cfg.quality_high_code_lines 或 token < cfg.quality_high_token）
    LEGENDARY = "legendary"  # 传奇（代码行数 > cfg.quality_legendary_code_lines 且 token < cfg.quality_legendary_token）


@dataclass
class DreamLog:
    """跟踪梦境随时间变化的日志。"""

    entries: list[dict[str, Any]] = field(default_factory=list)

    def record(self, phase: str, summary: str, details: dict | None = None) -> None:
        self.entries.append(
            {
                "timestamp": time.time(),
                "phase": phase,
                "summary": summary,
                "details": details or {},
            }
        )

    def recent(self, n: int = 10) -> list[dict[str, Any]]:
        return self.entries[-n:]

    def count_phases(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self.entries:
            counts[e["phase"]] = counts.get(e["phase"], 0) + 1
        return counts


@dataclass(slots=True)
class DreamMemory:
    """梦境记忆条目：从任务结果中提取的有价值方案。"""

    source_task_id: str
    agent_id: str
    task_type: str
    content: str
    quality: DreamQuality = DreamQuality.NORMAL
    metadata: dict[str, Any] = field(default_factory=dict)
    # P3 扩容：生命周期字段
    created_at: float = field(default_factory=time.time)
    archived: bool = False

    @property
    def is_high_quality(self) -> bool:
        return self.quality in (DreamQuality.HIGH, DreamQuality.LEGENDARY)

    @property
    def is_pinned(self) -> bool:
        """P3 扩容：LEGENDARY 记忆自动置顶。"""
        return self.quality == DreamQuality.LEGENDARY

    @property
    def is_expired(self) -> bool:
        """是否过期（超过 30 天）。"""
        return (time.time() - self.created_at) > get_config().dream.memory_archive_ttl

    @property
    def is_fragment(self) -> bool:
        """是否低价值碎片（内容过短且普通质量）。"""
        return (
            len(self.content) < get_config().dream.fragile_min_len
            and self.quality == DreamQuality.NORMAL
        )


@dataclass(slots=True)
class NightmareAlert:
    """噩梦告警：同类失败重复出现。"""

    error_pattern: str
    occurrences: int
    task_ids: list[str]


@dataclass(slots=True)
class DreamReport:
    """梦境报告：一次完整梦境的产出。"""

    phase: str = "complete"
    memories_extracted: int = 0
    memories_optimized: int = 0
    memories_persisted: int = 0
    optimized_memories: list[DreamMemory] = field(default_factory=list)
    nightmares: list[NightmareAlert] = field(default_factory=list)
    quality_counts: dict[str, int] = field(
        default_factory=lambda: {
            "normal": 0,
            "high": 0,
            "legendary": 0,
        }
    )
    total_token_saved: int = 0  # 本轮梦境节省的 Token

    @property
    def high_quality_count(self) -> int:
        """高质量记忆数（HIGH + LEGENDARY）。"""
        return self.quality_counts.get("high", 0) + self.quality_counts.get(
            "legendary", 0
        )

    def summary(self) -> str:
        """生成报告摘要。"""
        lines = [
            f"梦境阶段: {self.phase}",
            f"提取记忆: {self.memories_extracted}",
            f"优化记忆: {self.memories_optimized}",
            f"固化记忆: {self.memories_persisted}",
            f"质量分布: 普通={self.quality_counts.get('normal', 0)} "
            f"高质量={self.quality_counts.get('high', 0)} "
            f"传奇={self.quality_counts.get('legendary', 0)}",
            f"本轮节省 Token: {self.total_token_saved}",
        ]
        if self.nightmares:
            lines.append(f"噩梦告警: {len(self.nightmares)} 条")
            for nm in self.nightmares:
                lines.append(
                    f"  - 错误模式: {nm.error_pattern} (出现 {nm.occurrences} 次)"
                )
        else:
            lines.append("噩梦告警: 无")
        return "\n".join(lines)
