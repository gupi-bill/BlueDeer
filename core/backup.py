"""BlueDeer 数据备份与恢复。

能力：
    - 备份整个 data/ 和 logs/ 到 ZIP
    - 恢复从 ZIP 解压
    - 支持选择性备份（仅数据库 / 仅日志）
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("bluedeer.backup")

BACKUP_DIR = "backups"


@dataclass
class BackupManifest:
    created_at: float = field(default_factory=time.time)
    version: str = "1.0"
    files: list[str] = field(default_factory=list)
    size_bytes: int = 0
    db_only: bool = False


def create_backup(name: str = "", db_only: bool = False) -> str:
    """创建备份 ZIP 文件。返回备份文件路径。"""
    ts = time.strftime("%Y%m%d_%H%M%S")
    slug = name or f"bluedeer_backup_{ts}"
    filename = f"{slug}.zip"
    os.makedirs(BACKUP_DIR, exist_ok=True)
    path = os.path.join(BACKUP_DIR, filename)

    manifest = BackupManifest(db_only=db_only)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        # data/ 目录
        data_dir = Path("data")
        if data_dir.is_dir():
            for f in data_dir.rglob("*"):
                if f.is_file():
                    arcname = str(f)
                    zf.write(str(f), arcname)
                    manifest.files.append(arcname)

        if not db_only:
            # 只备份关键 JSON/JSONL 日志
            logs_dir = Path("logs")
            if logs_dir.is_dir():
                for f in logs_dir.rglob("*"):
                    if f.suffix in (".json", ".jsonl") and f.is_file():
                        arcname = str(f)
                        zf.write(str(f), arcname)
                        manifest.files.append(arcname)

        # 写 manifest
        zf.writestr(
            "backup_manifest.json",
            json.dumps(
                {
                    "created_at": manifest.created_at,
                    "version": manifest.version,
                    "files": manifest.files,
                    "db_only": manifest.db_only,
                    "name": slug,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

    manifest.size_bytes = os.path.getsize(path)
    logger.info(
        "备份完成: %s (%.1f MB, %d 个文件)",
        path,
        manifest.size_bytes / 1024 / 1024,
        len(manifest.files),
    )
    return path


def restore_backup(zip_path: str, dry_run: bool = False) -> list[str]:
    """从 ZIP 恢复备份。返回恢复的文件列表。"""
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"备份文件不存在: {zip_path}")

    restored: list[str] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.filename == "backup_manifest.json":
                continue
            if info.filename.endswith("/"):
                continue
            if dry_run:
                restored.append(info.filename)
                continue
            target = Path(info.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(str(target), "wb") as dst:
                shutil.copyfileobj(src, dst)
            restored.append(info.filename)

    logger.info("恢复完成: %s (%d 个文件)", zip_path, len(restored))
    return restored


def list_backups() -> list[dict[str, Any]]:
    """列出所有备份文件。"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    backups: list[dict[str, Any]] = []
    for f in sorted(
        Path(BACKUP_DIR).iterdir(), key=lambda p: p.stat().st_mtime, reverse=True
    ):
        if f.suffix == ".zip":
            manifest = None
            try:
                with zipfile.ZipFile(str(f), "r") as zf:
                    if "backup_manifest.json" in zf.namelist():
                        manifest = json.loads(zf.read("backup_manifest.json"))
            except Exception:
                pass
            backups.append(
                {
                    "filename": f.name,
                    "path": str(f),
                    "size_bytes": f.stat().st_size,
                    "created_at": f.stat().st_mtime,
                    "manifest": manifest,
                }
            )
    return backups


def delete_backup(filename: str) -> bool:
    """删除备份文件。"""
    path = Path(BACKUP_DIR) / filename
    if path.exists():
        try:
            path.unlink()
        except Exception:
            try:
                os.remove(str(path))
            except Exception:
                with open(str(path), "w") as f:
                    f.truncate(0)
                return False
        return True
    return False


# ============== 增量备份 ==============

_CHECKSUM_FILE = "data/backup_checksums.json"


def _file_checksum(path: str) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _load_checksums() -> dict[str, str]:
    try:
        with open(_CHECKSUM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_checksums(checksums: dict[str, str]) -> None:
    os.makedirs(os.path.dirname(_CHECKSUM_FILE) or ".", exist_ok=True)
    with open(_CHECKSUM_FILE, "w", encoding="utf-8") as f:
        json.dump(checksums, f, ensure_ascii=False, indent=2)


def incremental_backup(name: str = "", db_only: bool = False) -> str:
    """增量备份：只备份 checksum 变化的文件。"""
    ts = time.strftime("%Y%m%d_%H%M%S")
    slug = name or f"bluedeer_incr_{ts}"
    filename = f"{slug}.zip"
    os.makedirs(BACKUP_DIR, exist_ok=True)
    path = os.path.join(BACKUP_DIR, filename)

    old_checksums = _load_checksums()
    new_checksums: dict[str, str] = {}
    changed_files: list[str] = []

    data_dir = Path("data")
    if data_dir.is_dir():
        for f in data_dir.rglob("*"):
            if f.is_file():
                cs = _file_checksum(str(f))
                new_checksums[str(f)] = cs
                if old_checksums.get(str(f)) != cs:
                    changed_files.append(str(f))

    if not db_only:
        logs_dir = Path("logs")
        if logs_dir.is_dir():
            for f in logs_dir.rglob("*"):
                if f.suffix in (".json", ".jsonl") and f.is_file():
                    cs = _file_checksum(str(f))
                    new_checksums[str(f)] = cs
                    if old_checksums.get(str(f)) != cs:
                        changed_files.append(str(f))

    if not changed_files:
        logger.info("增量备份: 无变更文件，跳过")
        return ""

    manifest = BackupManifest(db_only=db_only)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in changed_files:
            zf.write(file_path, file_path)
            manifest.files.append(file_path)
        zf.writestr(
            "backup_manifest.json",
            json.dumps(
                {
                    "created_at": manifest.created_at,
                    "version": manifest.version,
                    "files": manifest.files,
                    "db_only": manifest.db_only,
                    "name": slug,
                    "mode": "incremental",
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

    manifest.size_bytes = os.path.getsize(path)
    _save_checksums(new_checksums)

    logger.info(
        "增量备份完成: %s (%d 个变更文件, %.1f MB)",
        path,
        len(changed_files),
        manifest.size_bytes / 1024 / 1024,
    )
    return path


# ============== 定时备份策略 ==============

import threading


class SchedulePolicy:
    """定时备份策略：支持 cron 表达式驱动的自动备份。"""

    def __init__(
        self, cron_expr: str = "0 0 2 * * *", backup_dir: str = BACKUP_DIR
    ) -> None:
        self._cron = cron_expr
        self._backup_dir = backup_dir
        self._timer: threading.Timer | None = None
        self._running = False

    def start(self) -> None:
        """启动定时备份守护（最小轮询间隔 60s）。"""
        if self._running:
            return
        self._running = True
        self._schedule_next()

    def stop(self) -> None:
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _schedule_next(self) -> None:
        if not self._running:
            return
        now = time.localtime()
        parts = self._cron.strip().split()
        if len(parts) != 6:
            logger.warning("定时备份 cron 格式错误: %s", self._cron)
            return
        target_sec = int(parts[0])
        target_min = int(parts[1])
        target_hour = int(parts[2])
        seconds_until = (
            (target_hour - now.tm_hour) * 3600
            + (target_min - now.tm_min) * 60
            + (target_sec - now.tm_sec)
        ) % 86400
        if seconds_until <= 0:
            seconds_until += 86400
        self._timer = threading.Timer(seconds_until, self._run_backup)
        self._timer.daemon = True
        self._timer.start()

    def _run_backup(self) -> None:
        logger.info("定时备份触发")
        try:
            create_backup(name=f"auto_{time.strftime('%Y%m%d_%H%M%S')}")
        except Exception as e:
            logger.error("定时备份失败: %s", e)
        self._schedule_next()
