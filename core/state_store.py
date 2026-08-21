"""BlueDeer StateStore：Agent 状态持久化抽象层。

提供：
- StateStore 抽象基类
- InMemoryStateStore：内存实现（适合单进程/测试）
- SQLiteStateStore：SQLite 实现（支持 TTL 清理）

用法：
    store = SQLiteStateStore("bluedeer_state.db")
    await store.save("task-001", {"status": "running"})
    data = await store.load("task-001")
    await store.cleanup(older_than=7 * 24 * 3600)
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("bluedeer.state_store")


class StateStore(ABC):
    """状态存储抽象。"""

    @abstractmethod
    async def save(self, key: str, value: dict[str, Any]) -> None:
        pass

    @abstractmethod
    async def load(self, key: str) -> dict[str, Any] | None:
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        pass

    @abstractmethod
    async def list_keys(self, prefix: str = "") -> list[str]:
        pass


class InMemoryStateStore(StateStore):
    """内存状态存储。"""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    async def save(self, key: str, value: dict[str, Any]) -> None:
        with self._lock:
            self._store[key] = value

    async def load(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            return self._store.get(key)

    async def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    async def list_keys(self, prefix: str = "") -> list[str]:
        with self._lock:
            return [k for k in self._store if k.startswith(prefix)]


class SQLiteStateStore(StateStore):
    """SQLite 状态存储。

    表结构：
        CREATE TABLE kv (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """

    def __init__(self, db_path: str = "bluedeer_state.db") -> None:
        self._db_path = db_path
        self._local = threading.local()
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kv (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    async def save(self, key: str, value: dict[str, Any]) -> None:
        def _save() -> None:
            conn = self._get_conn()
            conn.execute(
                "INSERT OR REPLACE INTO kv (key, value, updated_at) VALUES (?, ?, ?)",
                (key, json.dumps(value, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()

        await asyncio.to_thread(_save)

    async def load(self, key: str) -> dict[str, Any] | None:
        def _load() -> dict[str, Any] | None:
            conn = self._get_conn()
            row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
            if row is None:
                return None
            try:
                return json.loads(row["value"])
            except json.JSONDecodeError:
                return None

        return await asyncio.to_thread(_load)

    async def delete(self, key: str) -> None:
        def _delete() -> None:
            conn = self._get_conn()
            conn.execute("DELETE FROM kv WHERE key = ?", (key,))
            conn.commit()

        await asyncio.to_thread(_delete)

    async def list_keys(self, prefix: str = "") -> list[str]:
        def _list() -> list[str]:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT key FROM kv WHERE key LIKE ?", (f"{prefix}%",)
            ).fetchall()
            return [r["key"] for r in rows]

        return await asyncio.to_thread(_list)

    async def cleanup(self, older_than: float = 7 * 24 * 3600) -> int:
        """清理超过 older_than 秒未更新的记录，返回删除条数。"""
        cutoff = datetime.now(timezone.utc).timestamp() - older_than
        cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()

        def _cleanup() -> int:
            conn = self._get_conn()
            cur = conn.execute(
                "DELETE FROM kv WHERE updated_at < ?", (cutoff_iso,)
            )
            conn.commit()
            return cur.rowcount

        return await asyncio.to_thread(_cleanup)

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception as exc:
                logger.debug("SQLiteStateStore close 异常: %s", exc)
            self._local.conn = None
