"""BlueDeer 梦境系统（向后兼容入口）。

P2-1 拆分为多个子模块：
- dream_models：DreamMemory / DreamQuality / DreamReport / NightmareAlert
- dream_engine：DreamSystem 主类（流水线 + 协同推演）
- dream_report：export_dream_report_md
- dream_lifecycle：archive_expired / clean_fragments / snapshot / restore_snapshot
- dream_replay：sort_memories_pinned / generate_dream / replay_memory / recent_memories
"""

from __future__ import annotations

# 向后兼容：所有原 core.dream 的公共 API 继续可从本模块导入
from core.dream_engine import DreamSystem
from core.dream_lifecycle import (
    archive_expired,
    clean_fragments,
    restore_snapshot,
    snapshot,
)
from core.dream_models import (
    DreamMemory,
    DreamQuality,
    DreamReport,
    NightmareAlert,
)
from core.dream_replay import (
    generate_dream,
    recent_memories,
    replay_memory,
    sort_memories_pinned,
)
from core.dream_report import export_dream_report_md

__all__ = [
    "DreamMemory",
    "DreamQuality",
    "DreamReport",
    "DreamSystem",
    "NightmareAlert",
    "archive_expired",
    "clean_fragments",
    "export_dream_report_md",
    "generate_dream",
    "recent_memories",
    "replay_memory",
    "restore_snapshot",
    "snapshot",
    "sort_memories_pinned",
]
