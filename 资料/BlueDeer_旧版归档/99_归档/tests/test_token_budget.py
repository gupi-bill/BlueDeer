"""TokenBudget 单测。"""

from __future__ import annotations

from core.token_budget import TokenBudget


def make_budget() -> TokenBudget:
    budget = TokenBudget()
    budget.set_agent_budget("agent-1", daily_token_limit=1000, per_task_token_limit=200)
    budget.set_agent_budget("agent-2", daily_token_limit=500)
    return budget


def test_record_and_stats() -> None:
    budget = make_budget()
    rec = budget.record("agent-1", "task-1", tokens_in=100, tokens_out=50)
    assert rec.agent_id == "agent-1"
    assert rec.task_id == "task-1"
    assert rec.tokens_in == 100
    assert rec.tokens_out == 50

    stats = budget.get_agent_stats("agent-1")
    assert stats["total_tokens_in"] == 100
    assert stats["total_tokens_out"] == 50
    assert stats["record_count"] == 1


def test_daily_limit_alert() -> None:
    budget = make_budget()
    budget.record("agent-1", "task-1", tokens_in=600, tokens_out=300)
    alerts = budget.check_alerts()
    assert len(alerts) == 1
    assert alerts[0]["agent_id"] == "agent-1"
    assert alerts[0]["type"] == "daily_budget"


def test_per_task_limit() -> None:
    budget = make_budget()
    budget.set_agent_budget("agent-1", daily_token_limit=10000, per_task_token_limit=100)
    rec = budget.record("agent-1", "task-1", tokens_in=60, tokens_out=60)
    assert rec.tokens_in == 60
    assert rec.tokens_out == 60


def test_reset_agent() -> None:
    budget = make_budget()
    budget.record("agent-1", "task-1", tokens_in=800, tokens_out=100)
    budget.reset_agent("agent-1")
    stats = budget.get_agent_stats("agent-1")
    assert stats["used_today"] == 0
    assert stats["total_tokens_in"] == 800


def test_get_all_stats() -> None:
    budget = make_budget()
    budget.record("agent-1", "task-1", tokens_in=100, tokens_out=50)
    budget.record("agent-2", "task-2", tokens_in=200, tokens_out=100)
    all_stats = budget.get_all_stats()
    assert "agent-1" in all_stats
    assert "agent-2" in all_stats


def test_check_budget_passes_without_limit() -> None:
    budget = TokenBudget()
    allowed, _reason = budget.check_budget("agent-1")
    assert allowed is True


def test_check_budget_passes_under_limit() -> None:
    budget = TokenBudget()
    budget.set_agent_budget("agent-1", daily_token_limit=1000)
    budget.record("agent-1", "task-1", tokens_in=100, tokens_out=50)
    allowed, _reason = budget.check_budget("agent-1")
    assert allowed is True


def test_check_budget_fails_over_limit() -> None:
    budget = TokenBudget()
    budget.set_agent_budget("agent-1", daily_token_limit=100)
    budget.record("agent-1", "task-1", tokens_in=60, tokens_out=50)
    allowed, reason = budget.check_budget("agent-1")
    assert allowed is False
    assert "daily budget exceeded" in reason
