"""BlueDeer Metrics Collector: agent performance metrics and observability."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("bluedeer.metrics")


@dataclass
class TaskMetrics:
    task_type: str
    agent_id: str
    status: str
    duration_ms: float
    tokens_in: int = 0
    tokens_out: int = 0
    retries: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentMetrics:
    agent_id: str
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_duration_ms: float = 0.0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, tm: TaskMetrics) -> None:
        with self._lock:
            if tm.status == "success":
                self.tasks_completed += 1
            else:
                self.tasks_failed += 1
            self.total_duration_ms += tm.duration_ms
            self.total_tokens_in += tm.tokens_in
            self.total_tokens_out += tm.tokens_out

    def avg_duration_ms(self) -> float:
        total = self.tasks_completed + self.tasks_failed
        if total == 0:
            return 0.0
        return self.total_duration_ms / total

    def success_rate(self) -> float:
        total = self.tasks_completed + self.tasks_failed
        if total == 0:
            return 0.0
        return self.tasks_completed / total


class MetricsCollector:
    """Central metrics collector for all agents."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._entries: list[TaskMetrics] = []
        self._agent_metrics: dict[str, AgentMetrics] = {}
        self._max_entries = max_entries
        self._lock = threading.Lock()

    def record_task(self, tm: TaskMetrics) -> None:
        with self._lock:
            self._entries.append(tm)
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries :]
            am = self._agent_metrics.get(tm.agent_id)
            if am is None:
                am = AgentMetrics(agent_id=tm.agent_id)
                self._agent_metrics[tm.agent_id] = am
            am.record(tm)
        logger.debug(
            "Recorded task %s for agent %s: status=%s, duration=%.2fms",
            tm.task_type,
            tm.agent_id,
            tm.status,
            tm.duration_ms,
        )

    def get_agent_metrics(self, agent_id: str) -> AgentMetrics | None:
        with self._lock:
            return self._agent_metrics.get(agent_id)

    def get_all_agent_metrics(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            result = {}
            for aid, am in self._agent_metrics.items():
                result[aid] = {
                    "tasks_completed": am.tasks_completed,
                    "tasks_failed": am.tasks_failed,
                    "avg_duration_ms": am.avg_duration_ms(),
                    "success_rate": am.success_rate(),
                    "total_tokens_in": am.total_tokens_in,
                    "total_tokens_out": am.total_tokens_out,
                }
            return result

    def get_recent_tasks(self, count: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            recent = self._entries[-count:]
        return [
            {
                "task_type": t.task_type,
                "agent_id": t.agent_id,
                "status": t.status,
                "duration_ms": t.duration_ms,
                "tokens_in": t.tokens_in,
                "tokens_out": t.tokens_out,
                "timestamp": t.timestamp,
            }
            for t in recent
        ]

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            total_tasks = len(self._entries)
            success_tasks = sum(1 for e in self._entries if e.status == "success")
            return {
                "total_tasks": total_tasks,
                "success_count": success_tasks,
                "failure_count": total_tasks - success_tasks,
                "success_rate": (success_tasks / total_tasks)
                if total_tasks > 0
                else 0.0,
                "agents_tracked": len(self._agent_metrics),
            }


_global_metrics: MetricsCollector | None = None
_metrics_lock = threading.Lock()


def get_metrics_collector() -> MetricsCollector:
    global _global_metrics
    if _global_metrics is None:
        with _metrics_lock:
            if _global_metrics is None:
                _global_metrics = MetricsCollector()
    return _global_metrics


__all__ = [
    "AgentMetrics",
    "MetricsCollector",
    "TaskMetrics",
    "get_metrics_collector",
]
