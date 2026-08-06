"""Agent 间通信日志查看器。

从 trace.log 中按 trace_id 分组，展示 agent 之间的消息传递链。
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass

logger = logging.getLogger("bluedeer.comm_log")

_TRACE_LOG = "logs/trace.log"


@dataclass
class CommEntry:
    trace_id: str
    ts: float
    ts_str: str
    component: str
    action: str
    level: str
    message: str
    duration_ms: float
    error: str
    raw: dict


@dataclass
class CommChain:
    trace_id: str
    agents: list[str]
    entries: list[CommEntry]
    start_ts: float
    end_ts: float
    duration_sec: float
    entry_count: int
    error_count: int
    agent_count: int


@dataclass
class CommLogResult:
    chains: list[CommChain]
    total_chains: int
    total_entries: int
    agent_list: list[str]


class CommLog:
    def __init__(self, trace_log: str = _TRACE_LOG) -> None:
        self._trace_log = trace_log

    def _parse_line(self, line: str) -> dict | None:
        line = line.strip()
        if not line or line.startswith("#"):
            return None
        try:
            return json.loads(line)
        except (json.JSONDecodeError, ValueError):
            return None

    def _ts_str(self, ts: float) -> str:
        return time.strftime("%H:%M:%S", time.localtime(ts))

    def query(
        self,
        *,
        trace_id: str | None = None,
        agent: str | None = None,
        action: str | None = None,
        since: float = 0.0,
        upto: float | None = None,
        max_chains: int = 50,
    ) -> CommLogResult:
        if not os.path.exists(self._trace_log):
            return CommLogResult(
                chains=[], total_chains=0, total_entries=0, agent_list=[]
            )

        entries_by_trace: dict[str, list[dict]] = defaultdict(list)
        all_agents: set[str] = set()

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

                    comp = record.get("component", "")
                    tid = record.get("trace_id", "")
                    act = record.get("action", "")

                    if trace_id and trace_id not in tid:
                        continue
                    if agent and agent not in comp:
                        continue
                    if action and action != act:
                        continue

                    if comp:
                        all_agents.add(comp)
                    if tid:
                        entries_by_trace[tid].append(record)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("读取 trace 日志失败: %s", e)

        chains: list[CommChain] = []
        total_entries = 0

        for tid, records in entries_by_trace.items():
            records.sort(key=lambda r: r.get("ts", 0))

            agents_in_chain: set[str] = set()
            chain_entries: list[CommEntry] = []
            error_count = 0

            for r in records:
                comp = r.get("component", "")
                act = r.get("action", "")
                ts = r.get("ts", 0)
                err = r.get("error", "")

                if comp:
                    agents_in_chain.add(comp)
                if err:
                    error_count += 1

                chain_entries.append(
                    CommEntry(
                        trace_id=tid,
                        ts=ts,
                        ts_str=self._ts_str(ts),
                        component=comp,
                        action=act,
                        level=r.get("level", "INFO"),
                        message=r.get("message", err or act),
                        duration_ms=float(r.get("duration_ms", 0)),
                        error=err,
                        raw=r,
                    )
                )

            if not chain_entries:
                continue

            total_entries += len(chain_entries)

            chain = CommChain(
                trace_id=tid,
                agents=sorted(agents_in_chain),
                entries=chain_entries,
                start_ts=chain_entries[0].ts,
                end_ts=chain_entries[-1].ts,
                duration_sec=round(chain_entries[-1].ts - chain_entries[0].ts, 2),
                entry_count=len(chain_entries),
                error_count=error_count,
                agent_count=len(agents_in_chain),
            )
            chains.append(chain)

        chains.sort(key=lambda c: c.start_ts, reverse=True)
        chains = chains[:max_chains]

        return CommLogResult(
            chains=chains,
            total_chains=len(chains),
            total_entries=total_entries,
            agent_list=sorted(all_agents),
        )

    def search(self, query: str) -> list[CommEntry]:
        """按内容或发送者搜索通信条目。"""
        result = self.query(max_chains=1000)
        q = query.lower()
        matches = []
        for chain in result.chains:
            for entry in chain.entries:
                if q in entry.message.lower() or q in entry.component.lower():
                    matches.append(entry)
        return matches

    def filter_by_date(self, since: float, until: float | None = None) -> CommLogResult:
        """按时间范围过滤通信记录。"""
        return self.query(since=since, upto=until, max_chains=1000)


class CommLogViewer:
    @staticmethod
    def summary(comm_log: CommLog) -> dict:
        result = comm_log.query(max_chains=1000)
        return {
            "total_chains": result.total_chains,
            "total_entries": result.total_entries,
            "agent_count": len(result.agent_list),
            "agents": result.agent_list,
        }
