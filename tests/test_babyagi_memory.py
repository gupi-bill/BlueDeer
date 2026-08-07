"""Tests for BabyAGI vector memory (P1-2)."""

from __future__ import annotations

import pytest

from core.babyagi_loop import BabyAGILoopAgent
from core.task import TaskResult, TaskStatus
from vector_db.persistence import load_from_disk
from vector_db.vector_store import VectorStore


@pytest.fixture()
def babyagi_agent():
    class DummyBus:
        def subscribe(self, *a, **kw):
            pass

        async def publish(self, *a, **kw):
            return None

        def unsubscribe(self, *a, **kw):
            return False

        async def request(self, task, assignee_topic, result_topic, timeout=None):
            return TaskResult(
                task_id=task.id,
                status=TaskStatus.SUCCESS,
                output={"ok": True},
                agent_id=task.assignee,
            )

    class DummyRouter:
        async def complete_with_failover(self, *a, **kw):
            class R:
                content = "ok"
                tokens_in = 1
                tokens_out = 1

            return R()

    class DummyTools:
        def list_tools(self):
            return []

    class DummyContext:
        def get_context(self, *a, **kw):
            return {}

    agent = BabyAGILoopAgent(
        agent_id="b1",
        role="general",
        event_bus=DummyBus(),
        router=DummyRouter(),
        tool_registry=DummyTools(),
        context=DummyContext(),
    )
    return agent


def test_memory_store_default(babyagi_agent):
    assert isinstance(babyagi_agent.memory_store, VectorStore)
    assert babyagi_agent.memory_store.size == 0


def test_remember_inserts(babyagi_agent):
    babyagi_agent._remember(
        "写测试",
        TaskResult(task_id="t1", status=TaskStatus.SUCCESS, output={"ok": True}),
    )
    assert babyagi_agent.memory_store.size == 1
    doc = babyagi_agent.memory_store.get("b1-mem-0")
    assert doc is not None
    assert "写测试" in doc.text


def test_recall_empty_returns_none(babyagi_agent):
    assert babyagi_agent._recall("任何查询") == []


def test_recall_finds_related(babyagi_agent):
    babyagi_agent._remember(
        "修复数据库连接超时问题",
        TaskResult(task_id="t1", status=TaskStatus.SUCCESS, output={"ok": True}),
    )
    hits = babyagi_agent._recall("数据库连接", top_k=1)
    assert len(hits) == 1
    assert "修复数据库连接" in hits[0]


def test_memory_path_persists(tmp_path):
    path = str(tmp_path / "babyagi_mem.json")

    class DummyBus:
        def subscribe(self, *a, **kw):
            pass

        async def publish(self, *a, **kw):
            return None

        def unsubscribe(self, *a, **kw):
            return False

        async def request(self, task, assignee_topic, result_topic, timeout=None):
            return TaskResult(
                task_id=task.id,
                status=TaskStatus.SUCCESS,
                output={"ok": True},
                agent_id=task.assignee,
            )

    class DummyRouter:
        async def complete_with_failover(self, *a, **kw):
            class R:
                content = "ok"
                tokens_in = 1
                tokens_out = 1

            return R()

    class DummyTools:
        def list_tools(self):
            return []

    class DummyContext:
        def get_context(self, *a, **kw):
            return {}

    deps = {
        "event_bus": DummyBus(),
        "router": DummyRouter(),
        "tool_registry": DummyTools(),
        "context": DummyContext(),
    }

    agent = BabyAGILoopAgent(agent_id="b2", role="general", memory_path=path, **deps)
    agent._remember(
        "记忆落盘验证",
        TaskResult(task_id="t1", status=TaskStatus.SUCCESS, output={"ok": True}),
    )
    agent.run = None  # 手动 flush：直接调用 run 的落盘逻辑
    from vector_db.persistence import save_to_disk

    save_to_disk(agent.memory_store, path)

    loaded = load_from_disk(path)
    assert loaded.size == 1
    doc = loaded.get("b2-mem-0")
    assert doc is not None and "记忆落盘验证" in doc.text
