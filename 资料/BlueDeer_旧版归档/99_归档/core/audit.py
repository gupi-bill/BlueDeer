"""不可篡改审计日志（企业版）。

- 写入独立 data/audit_log.db（SQLite）
- 每行带 SHA-256 哈希链：hash_i = sha256(prev_hash || payload_i)
- 提供校验命令 verify_chain()
- 保留旧兼容接口：AuditLog / record_simple / query / summary / get_audit_log
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any

logger = logging.getLogger("bluedeer.audit")

_DB_FILE = "data/audit_log.db"


def _chain_hash(payload: str, prev_hash: str = "") -> str:
    return hashlib.sha256(f"{prev_hash}\x00{payload}".encode()).hexdigest()


class AuditLog:
    def __init__(self, path: str = _DB_FILE) -> None:
        self._path = path
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS audit_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL DEFAULT '',
                    action TEXT NOT NULL DEFAULT '',
                    ts REAL NOT NULL,
                    agent TEXT NOT NULL DEFAULT '',
                    username TEXT NOT NULL DEFAULT '',
                    ip TEXT NOT NULL DEFAULT '',
                    detail TEXT NOT NULL DEFAULT '',
                    old_status TEXT NOT NULL DEFAULT '',
                    new_status TEXT NOT NULL DEFAULT '',
                    attempt INTEGER NOT NULL DEFAULT 0,
                    trace_id TEXT NOT NULL DEFAULT '',
                    prev_hash TEXT NOT NULL DEFAULT '',
                    hash TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_audit_task ON audit_entries(task_id);
                CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_entries(action);
                CREATE INDEX IF NOT EXISTS idx_audit_agent ON audit_entries(agent);
                CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_entries(ts);
                """
            )

    def _last_hash(self) -> str:
        row = self._conn.execute(
            "SELECT hash FROM audit_entries ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row["hash"] if row else ""

    def record(self, entry_dict: dict[str, Any]) -> dict[str, Any]:
        """记录一条审计，自动计算哈希链。"""
        now = time.time()
        prev_hash = self._last_hash()
        payload = json.dumps(
            {
                "task_id": entry_dict.get("task_id", ""),
                "action": entry_dict.get("action", ""),
                "ts": now,
                "agent": entry_dict.get("agent", ""),
                "username": entry_dict.get("username", ""),
                "ip": entry_dict.get("ip", ""),
                "detail": entry_dict.get("detail", ""),
                "old_status": entry_dict.get("old_status", ""),
                "new_status": entry_dict.get("new_status", ""),
                "attempt": entry_dict.get("attempt", 0),
                "trace_id": entry_dict.get("trace_id", ""),
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        row_hash = _chain_hash(payload, prev_hash)
        with self._lock, self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO audit_entries
                (task_id, action, ts, agent, username, ip, detail, old_status,
                 new_status, attempt, trace_id, prev_hash, hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_dict.get("task_id", ""),
                    entry_dict.get("action", ""),
                    now,
                    entry_dict.get("agent", ""),
                    entry_dict.get("username", ""),
                    entry_dict.get("ip", ""),
                    entry_dict.get("detail", ""),
                    entry_dict.get("old_status", ""),
                    entry_dict.get("new_status", ""),
                    entry_dict.get("attempt", 0),
                    entry_dict.get("trace_id", ""),
                    prev_hash,
                    row_hash,
                ),
            )
            new_id = cur.lastrowid
        return {"id": new_id, "hash": row_hash}

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
        username: str = "",
        ip: str = "",
        **_: Any,
    ) -> dict[str, Any]:
        """兼容旧签名，返回记录信息。"""
        return self.record(
            {
                "task_id": task_id,
                "action": action,
                "agent": agent,
                "detail": detail,
                "old_status": old_status,
                "new_status": new_status,
                "attempt": attempt,
                "trace_id": trace_id,
                "username": username,
                "ip": ip,
            }
        )

    def query(
        self,
        task_id: str | None = None,
        action: str | None = None,
        agent: str | None = None,
        username: str | None = None,
        since: float = 0,
        upto: float | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM audit_entries WHERE 1=1"
        params: list[Any] = []
        if task_id:
            sql += " AND task_id=?"
            params.append(task_id)
        if action:
            sql += " AND action=?"
            params.append(action)
        if agent:
            sql += " AND agent=?"
            params.append(agent)
        if username:
            sql += " AND username=?"
            params.append(username)
        if since:
            sql += " AND ts>=?"
            params.append(since)
        if upto:
            sql += " AND ts<=?"
            params.append(upto)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([max(1, min(limit, 1000)), offset])
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def summary(self) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT COUNT(*) AS c, MAX(ts) AS last_ts FROM audit_entries"
        ).fetchone()
        actions = self._conn.execute(
            "SELECT action, COUNT(*) AS c FROM audit_entries GROUP BY action"
        ).fetchall()
        return {
            "total": row["c"] if row else 0,
            "last_ts": row["last_ts"] if row else 0,
            "actions": {a["action"]: a["c"] for a in actions},
        }

    def verify_chain(self) -> tuple[bool, str]:
        """校验哈希链，返回 (是否完整, 说明)。"""
        rows = self._conn.execute(
            "SELECT * FROM audit_entries ORDER BY id ASC"
        ).fetchall()
        prev = ""
        for r in rows:
            payload = json.dumps(
                {
                    "task_id": r["task_id"],
                    "action": r["action"],
                    "ts": r["ts"],
                    "agent": r["agent"],
                    "username": r["username"],
                    "ip": r["ip"],
                    "detail": r["detail"],
                    "old_status": r["old_status"],
                    "new_status": r["new_status"],
                    "attempt": r["attempt"],
                    "trace_id": r["trace_id"],
                },
                sort_keys=True,
                ensure_ascii=False,
            )
            expected = _chain_hash(payload, prev)
            if expected != r["hash"]:
                return False, f"哈希链断裂于 id={r['id']}"
            prev = expected
        return True, f"哈希链完整，共 {len(rows)} 条"

    def close(self) -> None:
        self._conn.close()


_audit_log: AuditLog | None = None
_audit_lock = threading.Lock()


def get_audit_log() -> AuditLog:
    global _audit_log
    with _audit_lock:
        if _audit_log is None:
            _audit_log = AuditLog()
        return _audit_log
