"""任务 Gantt 图数据生成器。

从 trace.log + scheduler + harness 聚合时间线数据。
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("bluedeer.gantt")

_TRACE_LOG = "logs/trace.log"


@dataclass
class GanttEntry:
    id: str
    label: str
    start: float
    end: float
    duration_sec: float
    status: str
    agent: str
    layer: int
    dependencies: list[str] = field(default_factory=list)


@dataclass
class GanttData:
    entries: list[GanttEntry] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    total_span_sec: float = 0.0

    def add_dependency(self, task_a: str, task_b: str) -> None:
        """添加任务依赖：task_a 依赖 task_b。"""
        for e in self.entries:
            if e.id == task_a and task_b not in e.dependencies:
                e.dependencies.append(task_b)
                return

    def add_milestone(self, name: str, date: float) -> None:
        """添加里程碑节点。"""
        self.entries.append(GanttEntry(
            id=f"ms_{name}",
            label=f"◆ {name}",
            start=date,
            end=date,
            duration_sec=0,
            status="milestone",
            agent="",
            layer=len(self.entries),
        ))

    def critical_path(self) -> list[GanttEntry]:
        """计算关键路径（最长路径）。返回关键路径上的条目列表。"""
        if not self.entries:
            return []
        deps = {e.id: list(e.dependencies) for e in self.entries}
        durations = {e.id: e.duration_sec for e in self.entries}
        visited = set()
        topo = []
        def _dfs(n):
            if n in visited:
                return
            visited.add(n)
            for d in deps.get(n, []):
                if d in deps:
                    _dfs(d)
            topo.append(n)
        for eid in deps:
            _dfs(eid)
        dist = {eid: 0 for eid in deps}
        prev = {eid: None for eid in deps}
        for eid in topo:
            for d in deps.get(eid, []):
                if d in dist:
                    nd = dist[eid] + durations.get(eid, 0)
                    if nd > dist[d]:
                        dist[d] = nd
                        prev[d] = eid
        end_id = max(dist, key=lambda k: dist[k])
        path_ids = []
        cur = end_id
        while cur is not None:
            path_ids.append(cur)
            cur = prev[cur]
        path_ids.reverse()
        entry_map = {e.id: e for e in self.entries}
        return [entry_map[pid] for pid in path_ids if pid in entry_map]


class GanttGenerator:
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

    def generate(
        self,
        *,
        harness_aggregate: dict[str, Any] | None = None,
        scheduler_jobs: dict[str, Any] | None = None,
        since: float = 0.0,
        upto: float | None = None,
    ) -> GanttData:
        entries: list[GanttEntry] = []
        seen: set[str] = set()
        tid_counter = 0

        if not os.path.exists(self._trace_log):
            return GanttData()

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

                    action = record.get("action", "")
                    comp = record.get("component", "")
                    task_id = record.get("task_id", "")
                    duration = float(record.get("duration_ms", 0)) / 1000.0

                    if action in ("handle_start", "task_start", "handle_success", "handle_failed") and task_id:
                        status = "running" if "start" in action else ("success" if "success" in action else "failed")

                        if task_id not in seen:
                            seen.add(task_id)
                            tid_counter += 1
                            entries.append(GanttEntry(
                                id=task_id,
                                label=f"{comp}/{task_id[:8]}",
                                start=ts,
                                end=ts + max(duration, 1),
                                duration_sec=max(duration, 1),
                                status=status,
                                agent=comp,
                                layer=tid_counter,
                            ))
                        else:
                            existing = next((e for e in entries if e.id == task_id), None)
                            if existing:
                                if "start" in action:
                                    existing.start = ts
                                existing.end = ts + max(duration, 1)
                                existing.duration_sec = max(duration, 1)
                                existing.status = status

                    elif action == "model_complete" and comp and not task_id:
                        model_key = f"model_{comp}_{ts}"
                        entries.append(GanttEntry(
                            id=model_key,
                            label=f"{comp} ML",
                            start=ts,
                            end=ts + max(duration, 1),
                            duration_sec=max(duration, 1),
                            status="success",
                            agent=comp,
                            layer=len(entries) + 1,
                        ))

        except (OSError, json.JSONDecodeError) as e:
            logger.warning("读取 trace 日志失败: %s", e)

        if harness_aggregate:
            tasks = harness_aggregate.get("tasks", {})
            for tid, tdata in tasks.items():
                if tid not in seen:
                    seen.add(tid)
                    entries.append(GanttEntry(
                        id=tid,
                        label=f"任务/{tid[:8]}",
                        start=time.time() - 60,
                        end=time.time(),
                        duration_sec=60,
                        status=tdata.get("status", "unknown"),
                        agent=tdata.get("agent_id", "?"),
                        layer=len(entries) + 1,
                    ))

        if scheduler_jobs:
            for jid, jdata in scheduler_jobs.items():
                entries.append(GanttEntry(
                    id=f"sched_{jid}",
                    label=f"⏰ {jid}",
                    start=time.time(),
                    end=time.time() + 10,
                    duration_sec=10,
                    status="scheduled",
                    agent="Scheduler",
                    layer=len(entries) + 1,
                    dependencies=[f"dag_{d}" for d in jdata.get("depends_on", [])] if isinstance(jdata, dict) else [],
                ))

        if not entries:
            return GanttData()

        entries.sort(key=lambda e: e.start)
        start_t = min(e.start for e in entries)
        end_t = max(e.end for e in entries)

        return GanttData(
            entries=entries,
            start_time=start_t,
            end_time=end_t,
            total_span_sec=max(end_t - start_t, 1),
        )


class GanttFormatter:
    @staticmethod
    def to_chart_data(gantt: GanttData, max_bars: int = 50) -> dict[str, Any]:
        entries = gantt.entries[:max_bars]
        span = gantt.total_span_sec
        now = time.time()

        bars = [
            {
                "id": e.id,
                "label": e.label,
                "start_pct": max(0, (e.start - gantt.start_time) / span * 100),
                "width_pct": max(1, (e.end - e.start) / span * 100),
                "status": e.status,
                "agent": e.agent,
                "start_str": time.strftime("%H:%M:%S", time.localtime(e.start)),
                "duration_str": f"{e.duration_sec:.1f}s",
            }
            for e in entries
        ]

        return {
            "bars": bars,
            "total_entries": len(entries),
            "total_all": len(gantt.entries),
            "start_time": gantt.start_time,
            "end_time": gantt.end_time,
            "span_sec": round(span, 1),
            "now": now,
        }