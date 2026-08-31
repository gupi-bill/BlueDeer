"""MemoryPipeline 单测。"""

from __future__ import annotations

import pytest

from memory_archive.pipeline import MemoryPipeline
from memory_archive.schemas import MemoryEntry, MemoryType


def test_consolidate_respects_similarity_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """consolidate 应过滤掉低于 similarity_threshold 的候选项。"""
    pipeline = MemoryPipeline(data_dir="memory_archive/data")
    pipeline._similarity_threshold = 0.9

    class FakeStore:
        def search(self, query: str, top_k: int = 5) -> list:
            return [
                type("R", (), {"entry": MemoryEntry(id="old", agent_id="a", memory_type=MemoryType.EPISODIC, content="old", importance=0.5), "score": 0.95})(),
                type("R", (), {"entry": MemoryEntry(id="far", agent_id="a", memory_type=MemoryType.EPISODIC, content="far", importance=0.5), "score": 0.50})(),
            ]

    pipeline._store = FakeStore()  # type: ignore[assignment]
    existing = pipeline.consolidate(
        MemoryEntry(id="new", agent_id="a", memory_type=MemoryType.EPISODIC, content="new", importance=0.5)
    )
    assert len(existing) == 1
    assert existing[0].id == "old"


def test_remember_marks_superseded() -> None:
    pipeline = MemoryPipeline(data_dir="memory_archive/data")

    class FakeStore:
        def __init__(self) -> None:
            self.entries: dict[str, MemoryEntry] = {}

        def search(self, query: str, top_k: int = 5) -> list:
            return []

        def add(self, entry: MemoryEntry) -> None:
            self.entries[entry.id] = entry

    pipeline._store = FakeStore()  # type: ignore[assignment]
    old = MemoryEntry(id="old", agent_id="a", memory_type=MemoryType.EPISODIC, content="old content", importance=0.5)
    pipeline._store.add(old)  # type: ignore[union-attr]
    pipeline._store.search = lambda *a, **kw: [  # type: ignore[method-assign]
        type("R", (), {"entry": old, "score": 0.99})()
    ]
    entry = pipeline.remember("a", "old content", MemoryType.EPISODIC, importance=0.5)
    assert entry is not None
    assert old.metadata.get("superseded_by") == entry.id
