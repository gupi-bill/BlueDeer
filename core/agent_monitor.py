"""Agent 健康监控：成功率、平均耗时、错误列表。

数据来源：从 Tracer 的 trace.log 中解析 span 记录，
配合 Harness 的 task_results 计算 per-agent 健康指标。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("bluedeer.agent_monitor")

_TRACE_LOG = "logs/trace.log"


@dataclass
class AgentHealth:
    agent_id: str
    role: str = ""
    total_runs: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_duration_ms: float = 0.0
    min_duration_ms: float = 0.0
    max_duration_ms: float = 0.0
    last_run_at: float = 0.0
    last_error: str = ""
    errors: list[dict] = field(default_factory=list)
    recent_runs: list[dict] = field(default_factory=list)


@dataclass
class AgentsHealthSummary:
    agents: list[AgentHealth] = field(default_factory=list)
    total_agents: int = 0
    total_runs: int = 0
    total_failures: int = 0
    global_success_rate: float = 0.0


class AgentMonitor:
    """Agent 健康监控器。

    从 trace.log 文件读取 span 记录，
    每个 span 如果是 agent.xxx 组件，就统计到对应 Agent。
    """

    def __init__(self, trace_log: str = _TRACE_LOG) -> None:
        self._trace_log = trace_log
        self._agent_map: dict[str, dict] = {}
        self._agent_roles: dict[str, str] = {}

    def register_agent(self, agent_id: str, role: str = "") -> None:
        self._agent_roles[agent_id] = role or agent_id

    def _parse_line(self, line: str) -> dict | None:
        line = line.strip()
        if not line or line.startswith("#"):
            return None
        try:
            record = json.loads(line)
            return record if isinstance(record, dict) else None
        except (json.JSONDecodeError, ValueError):
            return None

    def _is_agent_span(self, record: dict) -> bool:
        component = record.get("component", "")
        return component.startswith("agent.")

    def get_health(
        self,
        *,
        agent_id: str | None = None,
        max_errors: int = 5,
        max_recent: int = 10,
        since: float = 0.0,
        upto: float | None = None,
    ) -> AgentHealth | list[AgentHealth]:
        """查询一个或全部 Agent 的健康状态。

        Args:
            agent_id: 指定 Agent，None 则返回全部。
            max_errors: 每个 Agent 返回的最大错误数。
            max_recent: 每个 Agent 返回的最近执行数。
            since: 仅统计该时间戳之后的记录（默认不限）。
            upto: 仅统计该时间戳之前的记录。
        """
        stats: dict[str, dict] = {}
        for aid in self._agent_roles:
            stats[aid] = {
                "agent_id": aid,
                "role": self._agent_roles[aid],
                "total_runs": 0,
                "success_count": 0,
                "failure_count": 0,
                "durations": [],
                "last_run_at": 0.0,
                "last_error": "",
                "errors": [],
                "recent_runs": [],
            }

        if not os.path.exists(self._trace_log):
            if agent_id:
                info = stats.get(agent_id)
                if info:
                    return self._to_health(info)
                return AgentHealth(agent_id=agent_id)
            return [self._to_health(v) for v in stats.values()] if stats else []

        try:
            with open(self._trace_log, "r", encoding="utf-8") as f:
                for line in f:
                    record = self._parse_line(line)
                    if record is None:
                        continue

                    ts = record.get("ts", 0)
                    if since and ts < since:
                        continue
                    if upto and ts > upto:
                        continue

                    if not self._is_agent_span(record):
                        continue

                    span = record.get("span", "")
                    aid = record.get("agent_id", "")
                    if not aid:
                        component = record.get("component", "")
                        aid = component.split(".", 1)[1] if "." in component else span

                    if aid not in stats:
                        stats[aid] = {
                            "agent_id": aid,
                            "role": self._agent_roles.get(aid, ""),
                            "total_runs": 0,
                            "success_count": 0,
                            "failure_count": 0,
                            "durations": [],
                            "last_run_at": 0.0,
                            "last_error": "",
                            "errors": [],
                            "recent_runs": [],
                        }

                    s = stats[aid]
                    s["total_runs"] += 1

                    is_error = record.get("level") == "ERROR" or bool(
                        record.get("error")
                    )
                    duration = record.get("duration_ms", 0) or 0

                    if is_error:
                        s["failure_count"] += 1
                        err_text = record.get("error") or record.get("message", "")
                        s["last_error"] = err_text
                        if len(s["errors"]) < max_errors:
                            s["errors"].append(
                                {
                                    "ts": ts,
                                    "span": span,
                                    "error": err_text[:200],
                                    "trace_id": record.get("trace_id", ""),
                                }
                            )
                    else:
                        s["success_count"] += 1

                    if duration > 0:
                        s["durations"].append(duration)

                    s["last_run_at"] = max(s["last_run_at"], ts)

                    if len(s["recent_runs"]) < max_recent:
                        s["recent_runs"].append(
                            {
                                "ts": ts,
                                "span": span,
                                "trace_id": record.get("trace_id", ""),
                                "duration_ms": duration,
                                "error": record.get("error", ""),
                                "level": record.get("level", "INFO"),
                            }
                        )
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("读取 trace 日志失败: %s", e)

        if agent_id:
            info = stats.get(agent_id)
            if info:
                return self._to_health(info)
            return AgentHealth(agent_id=agent_id)
        return [self._to_health(v) for v in stats.values()]

    @staticmethod
    def _to_health(info: dict) -> AgentHealth:
        durations = info.get("durations", [])
        avg_d = sum(durations) / len(durations) if durations else 0.0
        return AgentHealth(
            agent_id=info["agent_id"],
            role=info.get("role", ""),
            total_runs=info["total_runs"],
            success_count=info["success_count"],
            failure_count=info["failure_count"],
            avg_duration_ms=round(avg_d, 1),
            min_duration_ms=round(min(durations), 1) if durations else 0.0,
            max_duration_ms=round(max(durations), 1) if durations else 0.0,
            last_run_at=info["last_run_at"],
            last_error=info.get("last_error", ""),
            errors=info.get("errors", []),
            recent_runs=info.get("recent_runs", []),
        )

    def health_check(self) -> dict[str, Any]:
        """快速健康检查。返回状态字典。"""
        agents = self.get_health()
        if isinstance(agents, AgentHealth):
            agents = [agents]
        total = sum(a.total_runs for a in agents)
        fails = sum(a.failure_count for a in agents)
        return {
            "healthy": fails == 0 or (total > 0 and fails / total < 0.2),
            "total_agents": len(agents),
            "total_runs": total,
            "total_failures": fails,
            "success_rate": round((total - fails) / total * 100, 1) if total else 100.0,
            "agents_with_errors": [a.agent_id for a in agents if a.failure_count > 0],
        }

    def get_alert_history(self) -> list[dict]:
        """获取所有告警历史，按时间倒序。"""
        agents = self.get_health()
        if isinstance(agents, AgentHealth):
            agents = [agents]
        alerts = []
        for a in agents:
            for err in a.errors:
                alerts.append(
                    {
                        "agent_id": a.agent_id,
                        "ts": err.get("ts", 0),
                        "error": err.get("error", ""),
                        "trace_id": err.get("trace_id", ""),
                    }
                )
        alerts.sort(key=lambda x: x["ts"], reverse=True)
        return alerts

    def check_threshold(self, metric: str, max_val: float) -> list[dict]:
        """检查指标是否超过阈值。返回违规列表。"""
        agents = self.get_health()
        if isinstance(agents, AgentHealth):
            agents = [agents]
        violations = []
        for a in agents:
            val = None
            if metric == "failure_count":
                val = a.failure_count
            elif metric == "avg_duration_ms":
                val = a.avg_duration_ms
            elif metric == "total_runs":
                val = a.total_runs
            if val is not None and val > max_val:
                violations.append(
                    {
                        "agent_id": a.agent_id,
                        "metric": metric,
                        "value": val,
                        "threshold": max_val,
                    }
                )
        return violations

    def summary(self) -> AgentsHealthSummary:
        agents = self.get_health()
        if isinstance(agents, AgentHealth):
            agents = [agents]
        total_runs = sum(a.total_runs for a in agents)
        total_failures = sum(a.failure_count for a in agents)
        return AgentsHealthSummary(
            agents=agents,
            total_agents=len(agents),
            total_runs=total_runs,
            total_failures=total_failures,
            global_success_rate=(
                round((total_runs - total_failures) / total_runs * 100, 1)
                if total_runs
                else 100.0
            ),
        )
