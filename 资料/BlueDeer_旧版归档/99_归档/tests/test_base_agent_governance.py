"""BaseAgent governance 集成单测。"""

from __future__ import annotations

from typing import ClassVar

from core.policy_engine import PolicyEngine
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


def test_policy_engine_available() -> None:
    engine = PolicyEngine()
    assert engine is not None


def test_token_budget_available() -> None:
    budget = TokenBudget()
    assert budget is not None


def test_token_budget_check_passes() -> None:
    budget = TokenBudget()
    budget.set_agent_budget("agent-1", daily_token_limit=1000)
    rec = budget.record("agent-1", "task-1", tokens_in=10, tokens_out=5)
    assert rec.tokens_in == 10


def test_token_budget_record_and_usage() -> None:
    budget = TokenBudget()
    budget.set_agent_budget("agent-1", daily_token_limit=1000)
    budget.record("agent-1", "task-1", tokens_in=100, tokens_out=50)
    stats = budget.get_agent_stats("agent-1")
    assert stats["total_tokens_in"] == 100
    assert stats["total_tokens_out"] == 50


def test_policy_engine_grant_and_check() -> None:
    engine = PolicyEngine()
    engine.create_role("tester", permissions={"tool-a"})
    engine.assign_role("agent-1", "tester")
    decision = engine.check_tool_access("agent-1", "tool-a")
    assert decision.allowed is True


def test_policy_engine_deny_tool_access() -> None:
    engine = PolicyEngine()
    decision = engine.check_tool_access("agent-1", "tool-a")
    assert decision.allowed is False


def test_policy_engine_hazardous_tool() -> None:
    engine = PolicyEngine()
    engine.allow_hazardous("danger-tool")
    decision = engine.check_tool_access("agent-1", "danger-tool")
    assert decision.allowed is True


def test_combined_governance_flow() -> None:
    engine = PolicyEngine()
    engine.create_role("tester", permissions={"tool-a"})
    engine.assign_role("agent-1", "tester")
    decision = engine.check_tool_access("agent-1", "tool-a")
    assert decision.allowed is True
    budget = TokenBudget()
    budget.set_agent_budget("agent-1", daily_token_limit=1000)
    rec = budget.record("agent-1", "task-1", tokens_in=50, tokens_out=25)
    assert rec.cost_usd == 0.0


def test_with_budget_check_context_manager() -> None:
    budget = TokenBudget()
    budget.set_agent_budget("agent-1", daily_token_limit=1000)
    rec = budget.record("agent-1", "task-1", tokens_in=10, tokens_out=5)
    assert rec.task_id == "task-1"
