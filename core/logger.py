"""BlueDeer 统一日志系统：轮转压缩 + 异步写入。

用法：
    from core.logger import get_logger, init_logging
    init_logging(level="INFO", log_dir="logs")
    logger = get_logger("my_module")
    logger.info("hello")
"""
from __future__ import annotations

import gzip
import logging
import os
import shutil
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from typing import Literal


DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class _CompressedRotatingHandler(RotatingFileHandler):
    """写满后自动轮转并 gzip 压缩旧文件。"""

    def doRollover(self) -> None:
        super().doRollover()
        base = self.baseFilename
        for i in range(self.backupCount, 0, -1):
            src = f"{base}.{i}"
            dst = f"{base}.{i}.gz"
            if os.path.exists(src) and not os.path.exists(dst):
                try:
                    with open(src, "rb") as fin:
                        with gzip.open(dst, "wb") as fout:
                            shutil.copyfileobj(fin, fout)
                    os.remove(src)
                except OSError:
                    pass


class _AsyncLogWriter:
    """后台线程异步写日志，不阻塞主线程。"""

    def __init__(self, handler: logging.Handler, max_queue: int = 1000) -> None:
        self._handler = handler
        self._queue: list[logging.LogRecord] = []
        self._lock = threading.Lock()
        self._flush_event = threading.Event()
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True, name="log-writer")
        self._thread.start()

    def emit(self, record: logging.LogRecord) -> None:
        with self._lock:
            if len(self._queue) < 1000:
                self._queue.append(record)
        self._flush_event.set()

    def _run(self) -> None:
        while not self._stop:
            self._flush_event.wait(0.5)
            self._flush_event.clear()
            self._flush()

    def _flush(self) -> None:
        with self._lock:
            batch = self._queue[:200]
            self._queue[:200] = []
        for rec in batch:
            try:
                self._handler.emit(rec)
            except Exception:
                pass

    def close(self) -> None:
        self._stop = True
        self._flush_event.set()
        self._thread.join(timeout=2)
        self._flush()


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"bluedeer.{name}")


def init_logging(
    level: str = "INFO",
    log_dir: str | None = None,
    fmt: str = DEFAULT_FORMAT,
    datefmt: str = DEFAULT_DATE_FORMAT,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    async_write: bool = True,
) -> None:
    level = level.upper().strip()
    numeric_level = getattr(logging, level, logging.INFO)

    handlers: list[logging.Handler] = []

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(numeric_level)
    handlers.append(sh)

    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        fh = _CompressedRotatingHandler(
            os.path.join(log_dir, "bluedeer.log"),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        fh.setLevel(numeric_level)
        if async_write:
            aw = _AsyncLogWriter(fh)
            fh.emit = aw.emit
            fh._async_writer = aw
        handlers.append(fh)

    logging.basicConfig(
        level=numeric_level,
        format=fmt,
        datefmt=datefmt,
        handlers=handlers,
        force=True,
    )