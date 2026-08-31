"""BlueDeer SQLite 数据库管理器：连接池 + 异步上下文。

用法：
    db = Database()
    async with db as conn:
        conn.execute(...)

    或同步：
    with db.conn() as conn:
        conn.execute(...)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from typing import Any

from typing_extensions import Self

from core.exceptions import StorageConnectionError

logger = logging.getLogger("bluedeer.database")

_DB_PATH = "data/bluedeer.db"
_POOL_SIZE = 5
_CONN_TIMEOUT = 10.0


class _PooledConnection:
    __slots__ = ("conn", "created_at", "in_use")

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.created_at = time.monotonic()
        self.in_use = False


class Database:
    """SQLite 数据库管理器，连接池 + 线程安全。"""

    _instance: Database | None = None
    _lock = threading.Lock()

    def __new__(cls, db_path: str = _DB_PATH, pool_size: int = _POOL_SIZE) -> Self:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init(db_path, pool_size)
        return cls._instance

    def _init(self, db_path: str, pool_size: int) -> None:
        self._db_path = db_path
        self._pool_size = max(1, pool_size)
        self._pool: list[_PooledConnection] = []
        self._pool_lock = threading.RLock()
        self._total_conns = 0
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._create_tables()
        logger.info("数据库已初始化: %s (pool=%d)", db_path, self._pool_size)

    def _new_conn(self) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(self._db_path, timeout=_CONN_TIMEOUT)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            self._total_conns += 1
            return conn
        except sqlite3.Error as e:
            raise StorageConnectionError(f"数据库连接失败 {self._db_path}: {e}") from e

    @contextmanager
    def conn(self) -> Generator[sqlite3.Connection, None, None]:
        with self._pool_lock:
            pc = self._acquire()
        try:
            yield pc.conn
        finally:
            with self._pool_lock:
                self._release(pc)

    def _acquire(self) -> _PooledConnection:
        time.monotonic()
        for pc in self._pool:
            if not pc.in_use:
                pc.in_use = True
                return pc
        if len(self._pool) < self._pool_size:
            c = self._new_conn()
            pc = _PooledConnection(c)
            pc.in_use = True
            self._pool.append(pc)
            return pc
        oldest = min(self._pool, key=lambda p: p.created_at)
        logger.warning("连接池耗尽，复用最旧连接")
        oldest.in_use = True
        return oldest

    def _release(self, pc: _PooledConnection) -> None:
        pc.in_use = False

    @asynccontextmanager
    async def async_conn(self) -> AsyncGenerator[sqlite3.Connection, None]:
        with self.conn() as c:
            yield c

    # ---- 建表 ----

    def _create_tables(self) -> None:
        with self.conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS scheduler_jobs (
                    id TEXT PRIMARY KEY,
                    cron TEXT NOT NULL,
                    task_type TEXT DEFAULT 'general',
                    task_payload TEXT DEFAULT '{}',
                    assignee TEXT DEFAULT '',
                    enabled INTEGER DEFAULT 1,
                    description TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS webhooks (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    events TEXT DEFAULT '[]',
                    enabled INTEGER DEFAULT 1,
                    secret TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    timeout_seconds REAL DEFAULT 10.0,
                    max_retries INTEGER DEFAULT 3
                );

                CREATE TABLE IF NOT EXISTS task_templates (
                    id TEXT PRIMARY KEY,
                    type TEXT DEFAULT 'general',
                    prompt_template TEXT DEFAULT '',
                    assignee TEXT DEFAULT '',
                    default_payload TEXT DEFAULT '{}',
                    tags TEXT DEFAULT '[]',
                    description TEXT DEFAULT '',
                    timeout_seconds REAL DEFAULT 0.0
                );

                CREATE TABLE IF NOT EXISTS task_results (
                    task_id TEXT PRIMARY KEY,
                    trace_id TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending',
                    task_type TEXT DEFAULT '',
                    agent_id TEXT DEFAULT '',
                    error TEXT DEFAULT '',
                    tokens_in INTEGER DEFAULT 0,
                    tokens_out INTEGER DEFAULT 0,
                    created_at REAL DEFAULT 0,
                    completed_at REAL DEFAULT 0,
                    result_text TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS task_pending (
                    task_id TEXT PRIMARY KEY,
                    trace_id TEXT DEFAULT '',
                    created_at REAL DEFAULT 0,
                    task_type TEXT DEFAULT 'general',
                    assignee TEXT DEFAULT '',
                    priority INTEGER DEFAULT 0,
                    context_ref TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS plugin_state (
                    name TEXT PRIMARY KEY,
                    enabled INTEGER DEFAULT 1,
                    data TEXT DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS dag_nodes (
                    id TEXT PRIMARY KEY,
                    depends_on TEXT DEFAULT '[]',
                    description TEXT DEFAULT '',
                    metadata TEXT DEFAULT '{}'
                );
            """)

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)

    # ====== 调度任务 ======

    def save_scheduler_jobs(self, jobs: dict[str, dict[str, Any]]) -> None:
        with self.conn() as conn:
            conn.execute("DELETE FROM scheduler_jobs")
            for jid, j in jobs.items():
                conn.execute(
                    "INSERT OR REPLACE INTO scheduler_jobs VALUES (?,?,?,?,?,?,?)",
                    (
                        jid,
                        j.get("cron", ""),
                        j.get("task_type", "general"),
                        json.dumps(j.get("task_payload", {}), ensure_ascii=False),
                        j.get("assignee", ""),
                        1 if j.get("enabled", True) else 0,
                        j.get("description", ""),
                    ),
                )

    def load_scheduler_jobs(self) -> list[dict[str, Any]]:
        with self.conn() as conn:
            rows = conn.execute("SELECT * FROM scheduler_jobs").fetchall()
            result = []
            for r in rows:
                d = self._row_to_dict(r)
                d["task_payload"] = json.loads(d.get("task_payload", "{}"))
                d["enabled"] = bool(d["enabled"])
                result.append(d)
            return result

    # ====== Webhook ======

    def save_webhooks(self, hooks: dict[str, dict[str, Any]]) -> None:
        with self.conn() as conn:
            conn.execute("DELETE FROM webhooks")
            for hid, h in hooks.items():
                conn.execute(
                    "INSERT OR REPLACE INTO webhooks VALUES (?,?,?,?,?,?,?,?)",
                    (
                        hid,
                        h.get("url", ""),
                        json.dumps(h.get("events", []), ensure_ascii=False),
                        1 if h.get("enabled", True) else 0,
                        h.get("secret", ""),
                        h.get("description", ""),
                        h.get("timeout_seconds", 10.0),
                        h.get("max_retries", 3),
                    ),
                )

    def load_webhooks(self) -> list[dict[str, Any]]:
        with self.conn() as conn:
            rows = conn.execute("SELECT * FROM webhooks").fetchall()
            result = []
            for r in rows:
                d = self._row_to_dict(r)
                d["events"] = json.loads(d.get("events", "[]"))
                d["enabled"] = bool(d["enabled"])
                result.append(d)
            return result

    # ====== 任务模板 ======

    def save_task_templates(self, templates: dict[str, dict[str, Any]]) -> None:
        with self.conn() as conn:
            conn.execute("DELETE FROM task_templates")
            for tid, t in templates.items():
                conn.execute(
                    "INSERT OR REPLACE INTO task_templates VALUES (?,?,?,?,?,?,?,?)",
                    (
                        tid,
                        t.get("type", "general"),
                        t.get("prompt_template", ""),
                        t.get("assignee", ""),
                        json.dumps(t.get("default_payload", {}), ensure_ascii=False),
                        json.dumps(t.get("tags", []), ensure_ascii=False),
                        t.get("description", ""),
                        t.get("timeout_seconds", 0.0),
                    ),
                )

    def load_task_templates(self) -> list[dict[str, Any]]:
        with self.conn() as conn:
            rows = conn.execute("SELECT * FROM task_templates").fetchall()
            result = []
            for r in rows:
                d = self._row_to_dict(r)
                d["default_payload"] = json.loads(d.get("default_payload", "{}"))
                d["tags"] = json.loads(d.get("tags", "[]"))
                result.append(d)
            return result

    # ====== 任务结果 ======

    def save_task_results(self, board: dict[str, dict[str, Any]]) -> None:
        with self.conn() as conn:
            for tid, r in board.items():
                conn.execute(
                    """INSERT OR REPLACE INTO task_results
                       (task_id, trace_id, status, task_type, agent_id,
                        error, tokens_in, tokens_out, created_at, completed_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        tid,
                        r.get("trace_id", ""),
                        r.get("status", "pending"),
                        r.get("task_type", ""),
                        r.get("agent_id", ""),
                        r.get("error", ""),
                        r.get("tokens_in", 0),
                        r.get("tokens_out", 0),
                        r.get("created_at", 0.0),
                        r.get("completed_at", 0.0),
                    ),
                )

    def load_task_results(self) -> list[dict[str, Any]]:
        with self.conn() as conn:
            rows = conn.execute("SELECT * FROM task_results").fetchall()
            return [self._row_to_dict(r) for r in rows]

    def save_task_pending(self, pending: dict[str, dict[str, Any]]) -> None:
        with self.conn() as conn:
            conn.execute("DELETE FROM task_pending")
            for tid, t in pending.items():
                conn.execute(
                    "INSERT OR REPLACE INTO task_pending VALUES (?,?,?,?,?,?,?)",
                    (
                        tid,
                        t.get("trace_id", ""),
                        t.get("created_at", 0.0),
                        t.get("type", "general"),
                        t.get("assignee", ""),
                        t.get("priority", 0),
                        t.get("context_ref", ""),
                    ),
                )

    def load_task_pending(self) -> list[dict[str, Any]]:
        with self.conn() as conn:
            rows = conn.execute("SELECT * FROM task_pending").fetchall()
            return [self._row_to_dict(r) for r in rows]

    # ====== 插件状态 ======

    def save_plugin_states(self, plugins: dict[str, dict[str, Any]]) -> None:
        with self.conn() as conn:
            for name, p in plugins.items():
                conn.execute(
                    "INSERT OR REPLACE INTO plugin_state VALUES (?,?,?)",
                    (
                        name,
                        1 if p.get("enabled", True) else 0,
                        json.dumps(p.get("data", {}), ensure_ascii=False),
                    ),
                )

    def load_plugin_states(self) -> list[dict[str, Any]]:
        with self.conn() as conn:
            rows = conn.execute("SELECT * FROM plugin_state").fetchall()
            result = []
            for r in rows:
                d = self._row_to_dict(r)
                d["enabled"] = bool(d["enabled"])
                d["data"] = json.loads(d.get("data", "{}"))
                result.append(d)
            return result

    def save_plugin_states_bool(self, states: dict[str, bool]) -> None:
        with self.conn() as conn:
            conn.execute("DELETE FROM plugin_state")
            for name, enabled in states.items():
                conn.execute(
                    "INSERT OR REPLACE INTO plugin_state VALUES (?,?,?)",
                    (name, 1 if enabled else 0, "{}"),
                )

    def load_plugin_states_bool(self) -> dict[str, bool]:
        with self.conn() as conn:
            rows = conn.execute("SELECT * FROM plugin_state").fetchall()
            return {r["name"]: bool(r["enabled"]) for r in rows}

    # ====== DAG 节点 ======

    def save_dag_nodes(self, nodes: list[dict[str, Any]]) -> None:
        with self.conn() as conn:
            conn.execute("DELETE FROM dag_nodes")
            for n in nodes:
                conn.execute(
                    "INSERT OR REPLACE INTO dag_nodes VALUES (?,?,?,?)",
                    (
                        n["id"],
                        json.dumps(n.get("depends_on", []), ensure_ascii=False),
                        n.get("description", ""),
                        json.dumps(n.get("metadata", {}), ensure_ascii=False),
                    ),
                )

    def load_dag_nodes(self) -> list[dict[str, Any]]:
        with self.conn() as conn:
            rows = conn.execute("SELECT * FROM dag_nodes").fetchall()
            result = []
            for r in rows:
                d = self._row_to_dict(r)
                d["depends_on"] = json.loads(d.get("depends_on", "[]"))
                d["metadata"] = json.loads(d.get("metadata", "{}"))
                result.append(d)
            return result
