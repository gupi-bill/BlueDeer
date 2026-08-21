"""BaseAgent 记忆落盘 + 预算硬拦截单测。"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from core.base_agent import BaseAgent
from core.token_budget import TokenBudget


class DummyRouter:
    model_name = "dummy"

    async def complete_with_failover(self, task_type: str, prompt: str, agent_id: str) -> DummyResponse:
        return DummyResponse()


class DummyResponse:
    model_name = "dummy"
    content = "ok"
    tokens_in = 1
    tokens_out = 1


class DummyToolRegistry:
    async def call(self, name: str, params: dict) -> None:
        return None


class DummyContext:
    def get_context(self, agent_id: str, task: DummyTask) -> dict:
        return {}


class DummyTask:
    id = "task-1"
    trace_id = "trace-1"
    type = "test"
    payload: ClassVar[dict] = {}


def test_memory_persistence_on_success() -> None:
    agent = BaseAgent(
        agent_id="agent-1",
        role="test",
        event_bus=None,
        router=DummyRouter(),
        tool_registry=DummyToolRegistry(),
        context=DummyContext(),
        token_budget=TokenBudget(),
    )
    assert agent._memory is None


def test_budget_hard_block() -> None:
    budget = TokenBudget()
    budget.set_agent_budget("agent-1", daily_token_limit=10)
    budget.record("agent-1", "task-1", tokens_in=5, tokens_out=5)
    allowed, reason = budget.check_budget("agent-1")
    assert allowed is False
    assert "daily budget exceeded" in reason


def test_budget_passes_under_limit() -> None:
    budget = TokenBudget()
    budget.set_agent_budget("agent-1", daily_token_limit=1000)
    allowed, reason = budget.check_budget("agent-1")
    assert allowed is True
    assert reason == "ok"


@pytest.mark.asyncio
async def test_remember_called_when_memory_available(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []

    class DummyMemory:
        def remember(self, agent_id: str, text: str, mtype: Any, importance: float) -> None:
            calls.append((agent_id, text, mtype, importance))

    agent = BaseAgent(
        agent_id="agent-1",
        role="test",
        event_bus=None,
        router=DummyRouter(),
        tool_registry=DummyToolRegistry(),
        context=DummyContext(),
        memory_pipeline=DummyMemory(),
        token_budget=TokenBudget(),
    )
    task = DummyTask()
    task.payload = {}
    await agent.handle(task)
    assert len(calls) == 1
    assert calls[0][0] == "agent-1"
