"""数据库完整性检查（企业版）。

- 对 SQLite 执行 PRAGMA integrity_check
- 自动开启 WAL 模式
- 返回健康报告
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any


def enable_wal(db_path: str) -> bool:
    """开启 WAL 模式。"""
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            return True
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def check_db(db_path: str) -> dict[str, Any]:
    """执行 integrity_check，返回报告。"""
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            result = row[0] if row else "unknown"
            wal = conn.execute("PRAGMA journal_mode").fetchone()
            return {
                "db": db_path,
                "integrity": result,
                "healthy": result == "ok",
                "journal_mode": wal[0] if wal else "unknown",
                "checked_at": time.time(),
            }
        finally:
            conn.close()
    except sqlite3.Error as e:
        return {
            "db": db_path,
            "integrity": str(e),
            "healthy": False,
            "journal_mode": "unknown",
            "checked_at": time.time(),
        }


def check_all(dbs: list[str]) -> list[dict[str, Any]]:
    """批量检查多个数据库。"""
    return [check_db(db) for db in dbs]
