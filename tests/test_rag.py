"""Tests for core.rag module."""

from __future__ import annotations

from core.rag import (
    SCOPE_AGENT,
    SCOPE_GLOBAL,
    SCOPE_TASK,
    RAGSystem,
)


class TestRAGSystem:
    def test_scope_constants(self):
        assert SCOPE_GLOBAL == "global"
        assert SCOPE_AGENT == "agent"
        assert SCOPE_TASK == "task"

    def test_ingest_and_retrieve(self):
        rag = RAGSystem()
        rag.ingest(SCOPE_GLOBAL, "doc1", "hello world")
        results = rag.retrieve("hello", SCOPE_GLOBAL)
        assert isinstance(results, list)
