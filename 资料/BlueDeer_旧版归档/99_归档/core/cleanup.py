"""BlueDeer 数据清理与维护。

能力:
    - 清理过期的 trace.log / audit.jsonl / alerts.jsonl
    - 压缩 SQLite 数据库 (VACUUM)
    - 统计各存储的磁盘用量
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("bluedeer.cleanup")


def get_storage_stats() -> dict[str, Any]:
    """返回各存储文件的磁盘用量统计。"""
    stats: dict[str, Any] = {"files": [], "total_bytes": 0}
    roots = ["data", "logs", "backups"]
    exts = {".json", ".jsonl", ".db", ".zip"}
    for root in roots:
        p = Path(root)
        if not p.is_dir():
            continue
        for f in sorted(p.rglob("*"), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.suffix in exts or f.name.endswith(".db"):
                sz = f.stat().st_size
                stats["files"].append(
                    {
                        "path": str(f),
                        "size_bytes": sz,
                        "size_str": _fmt_size(sz),
                        "modified": f.stat().st_mtime,
                    }
                )
                stats["total_bytes"] += sz
    stats["total_str"] = _fmt_size(stats["total_bytes"])
    return stats


@dataclass
class CleanupResult:
    removed: int = 0
    freed_bytes: int = 0
    db_vacuumed: bool = False
    errors: list[str] = field(default_factory=list)


def run_cleanup(dry_run: bool = False, max_days: int = 14) -> CleanupResult:
    """清理超过 max_days 的日志 / 数据文件。"""
    result = CleanupResult()
    cutoff = time.time() - max_days * 86400

    # JSONL 日志清理（逐行判断时间戳）
    for log_file in ["logs/trace.log", "logs/audit.jsonl", "logs/alerts.jsonl"]:
        _clean_jsonl(log_file, cutoff, result, dry_run)

    # SQLite VACUUM
    db_path = "data/bluedeer.db"
    if os.path.exists(db_path) and not dry_run:
        try:
            import sqlite3

            conn = sqlite3.connect(db_path)
            conn.execute("VACUUM")
            conn.close()
            result.db_vacuumed = True
            logger.info("数据库 VACUUM 完成")
        except Exception as e:
            result.errors.append(f"VACUUM 失败: {e}")

    return result


def _clean_jsonl(
    path: str, cutoff: float, result: CleanupResult, dry_run: bool
) -> None:
    if not os.path.exists(path):
        return
    kept: list[str] = []
    removed = 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    ts = (
                        obj.get("timestamp")
                        or obj.get("created_at")
                        or obj.get("time")
                        or 0
                    )
                    if isinstance(ts, str):
                        try:
                            from datetime import datetime

                            ts = datetime.fromisoformat(ts).timestamp()
                        except Exception:
                            logger.debug("时间戳解析失败，设为 0", exc_info=True)
                            ts = 0
                    if ts < cutoff:
                        removed += 1
                        continue
                except json.JSONDecodeError:
                    logger.exception("Exception in block")
                kept.append(line)
    except Exception as e:
        result.errors.append(f"读取 {path} 失败: {e}")
        return

    if not dry_run and removed > 0:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(kept) + ("\n" if kept else ""))
        logger.info("清理 %s: 移除 %d 行", path, removed)
    result.removed += removed
    result.freed_bytes += removed * 120  # approximate


def _fmt_size(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1024 * 1024:
        return f"{b / 1024:.1f} KB"
    return f"{b / 1024 / 1024:.1f} MB"


# ============== 优先级排序 ==============

PRIORITY_MAP: dict[str, int] = {
    "alerts": 1,
    "audit": 2,
    "trace": 3,
    "jsonl": 4,
    "json": 5,
    "db": 6,
    "zip": 7,
}


def _file_priority(filename: str) -> int:
    for key, pri in PRIORITY_MAP.items():
        if key in filename.lower():
            return pri
    return 10


def run_cleanup_priority(
    dry_run: bool = False,
    max_days: int = 14,
    max_files: int = 0,
) -> CleanupResult:
    """按优先级排序清理（告警 > 审计 > 跟踪 > 其他）。"""
    result = CleanupResult()
    cutoff = time.time() - max_days * 86400

    candidates: list[tuple[int, str]] = []
    for log_file in ["logs/trace.log", "logs/audit.jsonl", "logs/alerts.jsonl"]:
        if os.path.exists(log_file):
            candidates.append((_file_priority(log_file), log_file))

    candidates.sort(key=lambda x: x[0])

    processed = 0
    for _, log_file in candidates:
        if max_files and processed >= max_files:
            break
        before = result.removed
        _clean_jsonl(log_file, cutoff, result, dry_run)
        if result.removed > before:
            processed += 1

    db_path = "data/bluedeer.db"
    if os.path.exists(db_path) and not dry_run:
        try:
            import sqlite3

            conn = sqlite3.connect(db_path)
            conn.execute("VACUUM")
            conn.close()
            result.db_vacuumed = True
        except Exception as e:
            result.errors.append(f"VACUUM 失败: {e}")

    return result


# ============== 增量清理模式 ==============

_STATE_FILE = "data/cleanup_last_run.json"


def _load_last_run() -> float:
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("last_run", 0.0)
    except Exception:
        return 0.0


def _save_last_run() -> None:
    os.makedirs(os.path.dirname(_STATE_FILE) or ".", exist_ok=True)
    try:
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"last_run": time.time()}, f)
    except Exception:
        logger.warning("清理状态文件失败", exc_info=True)


def run_cleanup_incremental(
    dry_run: bool = False,
    max_days: int = 14,
) -> CleanupResult:
    """增量模式：只清理上次运行后修改过的文件。"""
    last_run = _load_last_run()
    if last_run == 0.0:
        last_run = time.time() - 86400

    result = CleanupResult()
    cutoff = time.time() - max_days * 86400

    for log_file in ["logs/trace.log", "logs/audit.jsonl", "logs/alerts.jsonl"]:
        if not os.path.exists(log_file):
            continue
        file_mtime = os.path.getmtime(log_file)
        if file_mtime < last_run:
            logger.debug("跳过 %s（上次运行后未修改）", log_file)
            continue
        _clean_jsonl(log_file, cutoff, result, dry_run)

    if not dry_run:
        _save_last_run()

    return result
