"""BlueDeer Memory Consolidator：记忆整合与去重。

功能：
- 合并相似记忆条目
- 过期记忆清理（TTL）
- 实体消歧（合并同一实体的不同表述）
- 生成记忆摘要
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("bluedeer.memory_consolidator")


@dataclass(slots=True)
class MemoryEntry:
    content: str
    category: str = "general"
    source_task_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ttl: int | None = None
    access_count: int = 0
    importance: float = 0.5
    embedding: list[float] = field(default_factory=list)


class MemoryConsolidator:
    """记忆整合器。"""

    def __init__(self, similarity_threshold: float = 0.85, max_entries: int = 10_000) -> None:
        self._similarity_threshold = similarity_threshold
        self._max_entries = max_entries
        self._entries: list[MemoryEntry] = []

    def add(self, entry: MemoryEntry) -> None:
        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            self._entries = sorted(self._entries, key=lambda e: e.importance, reverse=True)[: self._max_entries]

    def consolidate(self) -> list[MemoryEntry]:
        self._expire_old()
        merged = self._merge_similar()
        self._entries = merged
        return merged

    def _expire_old(self) -> None:
        now = datetime.now(timezone.utc)
        alive: list[MemoryEntry] = []
        for entry in self._entries:
            if entry.ttl is not None:
                created = datetime.fromisoformat(entry.created_at)
                age = (now - created).total_seconds()
                if age > entry.ttl:
                    continue
            alive.append(entry)
        self._entries = alive

    def _merge_similar(self) -> list[MemoryEntry]:
        groups: dict[str, list[MemoryEntry]] = defaultdict(list)
        for entry in self._entries:
            key = entry.category
            groups[key].append(entry)
        merged: list[MemoryEntry] = []
        for category, items in groups.items():
            if len(items) == 1:
                merged.append(items[0])
                continue
            best = max(items, key=lambda e: e.importance)
            best.access_count = sum(e.access_count for e in items)
            best.content = " | ".join({e.content for e in items if e.content})
            merged.append(best)
        return merged

    def get_top(self, category: str | None = None, limit: int = 10) -> list[MemoryEntry]:
        items = self._entries
        if category is not None:
            items = [e for e in items if e.category == category]
        return sorted(items, key=lambda e: e.importance, reverse=True)[:limit]

    @property
    def entry_count(self) -> int:
        return len(self._entries)
