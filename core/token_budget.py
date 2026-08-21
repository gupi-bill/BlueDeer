"""BlueDeer Token Budget：per-Agent Token 预算监控。

对标 Google / PyAgent / OpenAI Production Guide 的成本归因能力。
功能：
- per-Agent / per-Task token 统计
- Token 预算上限告警
- 成本归因（token_in / token_out / 估算 $）
- 预算耗尽时可触发回调

用法：
    budget = TokenBudget()
    budget.set_agent_budget("deer-001", daily_token_limit=1_000_000)
    record = budget.record("deer-001", "task-001", tokens_in=100, tokens_out=200)
    alerts = budget.check_alerts()
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.observability import Observability

logger = logging.getLogger("bluedeer.token_budget")


@dataclass(slots=True)
class TokenRecord:
    """单次 token 消耗记录。"""

    agent_id: str
    task_id: str
    tokens_in: int = 0
    tokens_out: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    cost_usd: float = 0.0


@dataclass(slots=True)
class AgentBudget:
    """Agent 级别预算配置。"""

    agent_id: str
    daily_token_limit: int | None = None
    per_task_token_limit: int | None = None
    cost_per_1k_tokens_in: float = 0.0
    cost_per_1k_tokens_out: float = 0.0
    alert_threshold: float = 0.8
    _used_today: int = 0
    _last_reset: str = field(default_factory=lambda: datetime.now(timezone.utc).date().isoformat())

    def maybe_reset(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        if today != self._last_reset:
            self._used_today = 0
            self._last_reset = today


class TokenBudget:
    """Token 预算管理器。

    线程安全；支持预算耗尽回调。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._budgets: dict[str, AgentBudget] = {}
        self._records: list[TokenRecord] = []
        self._max_records: int = 100_000
        self._alert_callbacks: list[Callable[[TokenRecord, AgentBudget], None]] = []

    def set_agent_budget(
        self,
        agent_id: str,
        daily_token_limit: int | None = None,
        per_task_token_limit: int | None = None,
        cost_per_1k_tokens_in: float = 0.0,
        cost_per_1k_tokens_out: float = 0.0,
        alert_threshold: float = 0.8,
    ) -> None:
        """设置 Agent 预算。"""
        with self._lock:
            existing = self._budgets.get(agent_id)
            if existing is None:
                existing = AgentBudget(agent_id=agent_id)
                self._budgets[agent_id] = existing
            existing.daily_token_limit = daily_token_limit
            existing.per_task_token_limit = per_task_token_limit
            existing.cost_per_1k_tokens_in = cost_per_1k_tokens_in
            existing.cost_per_1k_tokens_out = cost_per_1k_tokens_out
            existing.alert_threshold = alert_threshold

    def record(
        self,
        agent_id: str,
        task_id: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> TokenRecord:
        """记录一次 token 消耗。"""
        budget = self._budgets.get(agent_id)
        cost = 0.0
        if budget:
            cost = (tokens_in / 1000.0) * budget.cost_per_1k_tokens_in + (
                tokens_out / 1000.0
            ) * budget.cost_per_1k_tokens_out
        record = TokenRecord(
            agent_id=agent_id, task_id=task_id, tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost
        )
        with self._lock:
            self._records.append(record)
            if len(self._records) > self._max_records:
                self._records = self._records[-self._max_records :]
            if budget:
                budget.maybe_reset()
                budget._used_today += tokens_in + tokens_out
        Observability.span(
            "token_budget.record",
            agent_id=agent_id,
            task_id=task_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=round(cost, 6),
        )
        return record

    def check_alerts(self) -> list[dict[str, Any]]:
        """检查所有 Agent 预算告警。"""
        alerts: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        with self._lock:
            for agent_id, budget in self._budgets.items():
                budget.maybe_reset()
                if budget.daily_token_limit is None:
                    continue
                ratio = budget._used_today / budget.daily_token_limit
                if ratio >= budget.alert_threshold:
                    alert = {
                        "agent_id": agent_id,
                        "type": "daily_budget",
                        "used": budget._used_today,
                        "limit": budget.daily_token_limit,
                        "ratio": round(ratio, 4),
                        "timestamp": now.isoformat(),
                    }
                    alerts.append(alert)
                    logger.warning(
                        "Agent %s Token 预算告警: %d / %d (%.1f%%)",
                        agent_id,
                        budget._used_today,
                        budget.daily_token_limit,
                        ratio * 100,
                    )
        return alerts

    def on_alert(self, callback: Callable[[TokenRecord, AgentBudget], None]) -> None:
        """注册预算告警回调。"""
        self._alert_callbacks.append(callback)

    def get_agent_stats(self, agent_id: str) -> dict[str, Any]:
        """获取 Agent token 统计。"""
        with self._lock:
            agent_records = [r for r in self._records if r.agent_id == agent_id]
            total_in = sum(r.tokens_in for r in agent_records)
            total_out = sum(r.tokens_out for r in agent_records)
            total_cost = sum(r.cost_usd for r in agent_records)
            budget = self._budgets.get(agent_id)
            daily_limit = budget.daily_token_limit if budget else None
            used_today = budget._used_today if budget else 0
        return {
            "agent_id": agent_id,
            "total_tokens_in": total_in,
            "total_tokens_out": total_out,
            "total_tokens": total_in + total_out,
            "total_cost_usd": round(total_cost, 6),
            "daily_limit": daily_limit,
            "used_today": used_today,
            "remaining_today": (daily_limit - used_today) if daily_limit else None,
            "record_count": len(agent_records),
        }

    def get_all_stats(self) -> dict[str, Any]:
        """获取所有 Agent 统计汇总。"""
        with self._lock:
            agents = sorted({r.agent_id for r in self._records})
        return {
            agent_id: self.get_agent_stats(agent_id) for agent_id in agents
        }

    def reset_agent(self, agent_id: str) -> None:
        """重置 Agent 当日统计。"""
        with self._lock:
            budget = self._budgets.get(agent_id)
            if budget:
                budget._used_today = 0
                budget._last_reset = datetime.now(timezone.utc).date().isoformat()

    def check_budget(self, agent_id: str, estimated_tokens: int = 0) -> tuple[bool, str]:
        """任务前预算硬检查。

        Args:
            agent_id: Agent ID。
            estimated_tokens: 预估 token 消耗。

        Returns:
            (allowed, reason)
        """
        with self._lock:
            budget = self._budgets.get(agent_id)
            if budget is None:
                return True, "ok"
            budget.maybe_reset()
            if budget.daily_token_limit is not None and budget._used_today + estimated_tokens >= budget.daily_token_limit:
                return (
                    False,
                    f"daily budget exceeded: {budget._used_today} / {budget.daily_token_limit}",
                )
            if budget.per_task_token_limit is not None and estimated_tokens > budget.per_task_token_limit:
                return (
                    False,
                    f"per-task budget exceeded: {estimated_tokens} / {budget.per_task_token_limit}",
                )
            return True, "ok"

    @property
    def record_count(self) -> int:
        with self._lock:
            return len(self._records)
