"""Tests for P1 modules: memory_extractor, memory_consolidator, hitl_manager."""

from __future__ import annotations

import time

from core.hitl_manager import HitlManager, HitlStatus, HitlTask
from core.memory_consolidator import MemoryConsolidator, MemoryEntry
from core.memory_extractor import MemoryExtractor


class TestMemoryExtractor:
    def test_extract_entities(self):
        extractor = MemoryExtractor()
        output = {"message": "Hello Alice and Bob"}
        result = extractor.extract("task-1", {"project": "BlueDeer"}, output)
        names = [e["name"] for e in result["entities"]]
        assert "Alice" in names
        assert "Bob" in names
        assert any("Blue" in n or "Deer" in n for n in names)

    def test_extract_preferences(self):
        extractor = MemoryExtractor()
        payload = {"preferences": {"theme": "dark", "language": "zh"}}
        output = {"summary": "user likes dark mode"}
        result = extractor.extract("task-2", payload, output)
        rels = result["relations"]
        assert len(rels) == 2
        assert any(r["predicate"] == "prefers_theme" for r in rels)

    def test_extract_summary_fact(self):
        extractor = MemoryExtractor()
        output = {"summary": "this is a very long summary " + "x" * 200}
        result = extractor.extract("task-3", {}, output)
        assert len(result["facts"]) == 1
        assert result["facts"][0]["category"] == "summary"

    def test_extract_empty_output(self):
        extractor = MemoryExtractor()
        result = extractor.extract("task-4", {}, {})
        assert result["extracted_at"]


class TestMemoryConsolidator:
    def test_add_and_get_top(self):
        consolidator = MemoryConsolidator()
        consolidator.add(MemoryEntry(content="alpha", category="fact", importance=0.9))
        consolidator.add(MemoryEntry(content="beta", category="fact", importance=0.3))
        top = consolidator.get_top(category="fact", limit=1)
        assert len(top) == 1
        assert top[0].content == "alpha"

    def test_consolidate_merge_similar(self):
        consolidator = MemoryConsolidator(similarity_threshold=0.5)
        consolidator.add(MemoryEntry(content="hello world", category="chat", importance=0.5))
        consolidator.add(MemoryEntry(content="hello world!", category="chat", importance=0.6))
        merged = consolidator.consolidate()
        categories = [e.category for e in merged]
        assert categories.count("chat") == 1

    def test_expire_old(self):
        consolidator = MemoryConsolidator()
        consolidator.add(MemoryEntry(content="old", category="fact", ttl=1))
        time.sleep(1.1)
        merged = consolidator.consolidate()
        assert all(e.content != "old" for e in merged)

    def test_max_entries(self):
        consolidator = MemoryConsolidator(max_entries=5)
        for i in range(20):
            consolidator.add(MemoryEntry(content=f"item-{i}", importance=i))
        assert consolidator.entry_count <= 5

    def test_entry_count(self):
        consolidator = MemoryConsolidator()
        assert consolidator.entry_count == 0
        consolidator.add(MemoryEntry(content="x"))
        assert consolidator.entry_count == 1


class TestHitlManager:
    def test_submit_and_pending(self):
        manager = HitlManager(default_timeout=10)
        task = HitlTask(task_id="ht-1", agent_id="deer", payload={}, reason="sensitive")
        manager.submit(task)
        pending = manager.get_pending()
        assert len(pending) == 1
        assert pending[0].status == HitlStatus.PENDING

    def test_approve(self):
        manager = HitlManager()
        manager.submit(HitlTask(task_id="ht-2", agent_id="deer", payload={}))
        task = manager.approve("ht-2", approver="admin", comment="ok")
        assert task is not None
        assert task.status == HitlStatus.APPROVED
        assert task.approver == "admin"
        assert len(manager.get_pending()) == 0

    def test_reject(self):
        manager = HitlManager()
        manager.submit(HitlTask(task_id="ht-3", agent_id="deer", payload={}))
        task = manager.reject("ht-3", approver="admin", comment="nope")
        assert task is not None
        assert task.status == HitlStatus.REJECTED
        assert task.comment == "nope"

    def test_timeout(self):
        manager = HitlManager(default_timeout=1)
        manager.submit(HitlTask(task_id="ht-4", agent_id="deer", payload={}))
        time.sleep(1.1)
        timed_out = manager.check_timeouts()
        assert len(timed_out) == 1
        assert timed_out[0].status == HitlStatus.TIMEOUT

    def test_stats(self):
        manager = HitlManager()
        manager.submit(HitlTask(task_id="ht-5", agent_id="deer", payload={}))
        manager.approve("ht-5")
        stats = manager.get_stats()
        assert stats.get("approved", 0) == 1
        assert stats.get("pending", 0) == 0

    def test_escalate(self):
        manager = HitlManager()
        manager.submit(HitlTask(task_id="ht-6", agent_id="deer", payload={}))
        task = manager.escalate("ht-6")
        assert task is not None
        assert task.status == HitlStatus.ESCALATED
