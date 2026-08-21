"""BlueDeer Session Store：Agent 会话持久化。

对标 OpenAI Agents SDK Session 后端（SQLite / Redis / SQLAlchemy）。
本实现优先走 SQLite（零依赖），可选 Redis。

用法：
    store = SessionStore("sqlite:///sessions.db")
    await store.create_session("deer-001")
    await store.append_message("deer-001", {"role": "user", "content": "hi"})
    history = await store.get_history("deer-001")
    await store.clear_session("deer-001")
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("bluedeer.session_store")


@dataclass(slots=True)
class SessionMessage:
    """会话中的单条消息。"""

    session_id: str
    role: str
    content: Any
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Session:
    """Agent 会话元数据。"""

    session_id: str
    agent_id: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)
    message_count: int = 0


class SessionStore:
    """SQLite -backed Agent 会话持久化。

    线程安全；async 接口便于在 asyncio 事件循环中直接调用。
    """

    def __init__(self, dsn: str = "sqlite:///bluedeer_sessions.db") -> None:
        self._dsn = dsn
        self._lock = threading.Lock()
        self._conn = self._connect(dsn)
        self._init_schema()

    def _connect(self, dsn: str) -> sqlite3.Connection:
        if not dsn.startswith("sqlite:///"):
            raise ValueError(f"不支持的 DSN: {dsn}")
        path = dsn[len("sqlite:///"):]
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    agent_id   TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata   TEXT NOT NULL DEFAULT '{}',
                    message_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id  TEXT NOT NULL,
                    role        TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    timestamp   TEXT NOT NULL,
                    metadata    TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                );
                CREATE INDEX IF NOT EXISTS idx_messages_session
                    ON messages(session_id, timestamp);
                """
            )

    async def create_session(
        self,
        session_id: str,
        agent_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> Session:
        """创建新会话。已存在则静默返回现有会话。"""
        now = datetime.now(timezone.utc).isoformat()
        meta = json.dumps(metadata or {}, ensure_ascii=False)
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO sessions
                    (session_id, agent_id, created_at, updated_at, metadata, message_count)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (session_id, agent_id, now, now, meta),
            )
        return await self.get_session(session_id)

    async def get_session(self, session_id: str) -> Session | None:
        """获取会话元数据。"""
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return Session(
            session_id=row["session_id"],
            agent_id=row["agent_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=json.loads(row["metadata"]),
            message_count=row["message_count"],
        )

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: Any,
        metadata: dict[str, Any] | None = None,
    ) -> SessionMessage:
        """追加消息到会话。"""
        now = datetime.now(timezone.utc).isoformat()
        content_str = json.dumps(content, ensure_ascii=False, default=str)
        meta = json.dumps(metadata or {}, ensure_ascii=False)
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO messages (session_id, role, content, timestamp, metadata)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, content_str, now, meta),
            )
            self._conn.execute(
                """
                UPDATE sessions
                SET updated_at = ?, message_count = message_count + 1
                WHERE session_id = ?
                """,
                (now, session_id),
            )
        return SessionMessage(
            session_id=session_id, role=role, content=content, timestamp=now, metadata=metadata or {}
        )

    async def get_history(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SessionMessage]:
        """获取会话历史（按时间正序）。"""
        with self._lock, self._conn:
            rows = self._conn.execute(
                """
                SELECT role, content, timestamp, metadata
                FROM messages
                WHERE session_id = ?
                ORDER BY timestamp ASC
                LIMIT ? OFFSET ?
                """,
                (session_id, limit, offset),
            ).fetchall()
        return [
            SessionMessage(
                session_id=session_id,
                role=row["role"],
                content=json.loads(row["content"]),
                timestamp=row["timestamp"],
                metadata=json.loads(row["metadata"]),
            )
            for row in rows
        ]

    async def get_recent(
        self,
        session_id: str,
        n: int = 10,
    ) -> list[SessionMessage]:
        """获取最近 n 条消息。"""
        return await self.get_history(session_id, limit=n, offset=max(0, self._message_count(session_id) - n))

    async def clear_session(self, session_id: str) -> bool:
        """清空会话消息并重置计数。"""
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            if cur.rowcount == 0:
                return False
            self._conn.execute(
                "UPDATE sessions SET message_count = 0 WHERE session_id = ?",
                (session_id,),
            )
        return True

    async def delete_session(self, session_id: str) -> bool:
        """删除会话及其所有消息。"""
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            self._conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        return cur.rowcount > 0

    async def list_sessions(self, agent_id: str | None = None) -> list[Session]:
        """列出所有会话，可按 agent_id 过滤。"""
        query = "SELECT * FROM sessions"
        params: tuple[Any, ...] = ()
        if agent_id is not None:
            query += " WHERE agent_id = ?"
            params = (agent_id,)
        with self._lock, self._conn:
            rows = self._conn.execute(query, params).fetchall()
        return [
            Session(
                session_id=row["session_id"],
                agent_id=row["agent_id"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                metadata=json.loads(row["metadata"]),
                message_count=row["message_count"],
            )
            for row in rows
        ]

    async def session_exists(self, session_id: str) -> bool:
        """检查会话是否存在。"""
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return row is not None

    async def update_metadata(self, session_id: str, metadata: dict[str, Any]) -> Session | None:
        """更新会话元数据（合并而非覆盖）。"""
        session = await self.get_session(session_id)
        if session is None:
            return None
        session.metadata.update(metadata)
        meta = json.dumps(session.metadata, ensure_ascii=False)
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE sessions SET metadata = ?, updated_at = ? WHERE session_id = ?",
                (meta, now, session_id),
            )
        return session

    def close(self) -> None:
        """关闭数据库连接。"""
        with self._lock:
            self._conn.close()

    def _message_count(self, session_id: str) -> int:
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT COUNT(*) AS cnt FROM messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return row["cnt"] if row else 0
