"""任务审计日志链。

记录每个任务从创建到完成的完整生命周期事件，
支持按 task_id / agent / action / 时间范围查询。
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any

logger = logging.getLogger("bluedeer.audit")

_AUDIT_FILE = "logs/audit.jsonl"
_MAX_LINES = 10_000


@dataclass
class AuditEntry:
    task_id: str
    action: str
    ts: float = field(default_factory=time.time)
    agent: str = ""
    detail: str = ""
    old_status: str = ""
    new_status: str = ""
    attempt: int = 0
    trace_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "action": self.action,
            "ts": self.ts,
            "agent": self.agent,
            "detail": self.detail,
            "old_status": self.old_status,
            "new_status": self.new_status,
            "attempt": self.attempt,
            "trace_id": self.trace_id,
        }


class AuditLog:
    def __init__(self, path: str = _AUDIT_FILE, archive_path: str = "") -> None:
        self._path = path
        self._archive_path = archive_path or (path.replace(".jsonl", "_archive.jsonl") if path else "logs/audit_archive.jsonl")
        self._buffer: list[AuditEntry] = []

    def record(self, entry: AuditEntry) -> None:
        self._buffer.append(entry)
        self._flush()

    def record_simple(
        self,
        task_id: str,
        action: str,
        agent: str = "",
        detail: str = "",
        old_status: str = "",
        new_status: str = "",
        attempt: int = 0,
        trace_id: str = "",
    ) -> AuditEntry:
        entry = AuditEntry(
            task_id=task_id,
            action=action,
            agent=agent,
            detail=detail,
            old_status=old_status,
            new_status=new_status,
            attempt=attempt,
            trace_id=trace_id,
        )
        self.record(entry)
        return entry

    # ---- 索引加速的时间范围搜索 ----

    def query_by_time(
        self,
        since: float,
        upto: float,
        action: str | None = None,
        agent: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """基于时间范围的索引搜索（要求文件按 ts 有序）。"""
        if not os.path.exists(self._path):
            return []
        result: list[dict[str, Any]] = []
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    ts = entry.get("ts", 0)
                    if ts < since:
                        continue
                    if ts > upto:
                        # 由于文件按 ts 有序，后面都 > upto，可提前终止
                        break
                    if action and entry.get("action") != action:
                        continue
                    if agent and entry.get("agent") != agent:
                        continue
                    result.append(entry)
        except OSError as e:
            logger.warning("审计日志时间搜索失败: %s", e)
        result.sort(key=lambda e: e.get("ts", 0), reverse=True)
        return result[offset:offset + limit]

    # ---- 归档策略 ----

    def archive(self, before: float) -> int:
        """将 before 时间戳之前的审计记录移至归档存储。

        Returns:
            归档的记录数。
        """
        if not os.path.exists(self._path):
            return 0
        remaining: list[dict[str, Any]] = []
        archived: list[dict[str, Any]] = []
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        remaining.append({"raw": line})
                        continue
                    ts = entry.get("ts", 0)
                    if ts < before:
                        archived.append(entry)
                    else:
                        remaining.append(entry)
        except OSError as e:
            logger.warning("审计日志归档读取失败: %s", e)
            return 0
        # 写回剩余记录
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                for entry in remaining:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("审计日志归档写回失败: %s", e)
            return 0
        # 追加到归档文件
        if archived:
            try:
                os.makedirs(os.path.dirname(self._archive_path) or ".", exist_ok=True)
                with open(self._archive_path, "a", encoding="utf-8") as f:
                    for entry in archived:
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except OSError as e:
                logger.warning("审计日志归档写入失败: %s", e)
                return 0
        logger.info("审计日志归档: %d 条移至 %s", len(archived), self._archive_path)
        return len(archived)

    def _flush(self) -> None:
        if not self._buffer:
            return
        try:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as f:
                for entry in self._buffer:
                    f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
            self._buffer.clear()
        except OSError as e:
            logger.warning("审计日志写入失败: %s", e)

    def query(
        self,
        task_id: str | None = None,
        action: str | None = None,
        agent: str | None = None,
        since: float = 0,
        upto: float | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if not os.path.exists(self._path):
            return []

        result: list[dict[str, Any]] = []
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue

                    ts = entry.get("ts", 0)
                    if since and ts < since:
                        continue
                    if upto and ts > upto:
                        continue
                    if task_id and entry.get("task_id") != task_id:
                        continue
                    if action and entry.get("action") != action:
                        continue
                    if agent and entry.get("agent") != agent:
                        continue
                    result.append(entry)

        except OSError as e:
            logger.warning("审计日志读取失败: %s", e)

        result.sort(key=lambda e: e.get("ts", 0), reverse=True)
        return result[offset:offset + limit]

    def summary(self) -> dict[str, Any]:
        entries = self.query(limit=500)
        total = len(entries)
        by_action: dict[str, int] = {}
        by_agent: dict[str, int] = {}
        for e in entries[:500]:
            act = e.get("action", "?")
            by_action[act] = by_action.get(act, 0) + 1
            ag = e.get("agent", "?")
            by_agent[ag] = by_agent.get(ag, 0) + 1
        return {
            "total": total,
            "by_action": by_action,
            "by_agent": by_agent,
            "latest_ts": entries[0]["ts"] if entries else 0,
        }


# 全局单例
_audit_log: AuditLog | None = None


def get_audit_log() -> AuditLog:
    global _audit_log
    if _audit_log is None:
        _audit_log = AuditLog()
    return _audit_log