"""BlueDeer 日志查看器：Web 端日志浏览、过滤、搜索。

支持按级别/组件/关键字过滤 trace 日志，
返回分页的结构化日志条目。
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("bluedeer.log_viewer")


@dataclass(slots=True)
class LogEntry:
    """单条日志条目。"""
    line_number: int
    raw: str
    timestamp: str = ""
    level: str = ""
    message: str = ""
    parsed: dict[str, Any] = field(default_factory=dict)


class LogViewer:
    """日志查看器。

    从 trace.log 文件读取并解析结构化日志，
    支持过滤、搜索、分页。
    """

    def __init__(self, log_dir: str = "logs", log_file: str = "trace.log") -> None:
        self._path = os.path.join(log_dir, log_file)
        self._entries: list[LogEntry] = []
        self._loaded = False

    def reload(self) -> int:
        """重新加载日志文件。

        Returns:
            加载的日志条数。
        """
        self._entries = []
        if not os.path.exists(self._path):
            self._loaded = True
            return 0

        with open(self._path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                entry = LogEntry(line_number=idx + 1, raw=line.rstrip())
                self._parse_entry(entry)
                self._entries.append(entry)

        self._loaded = True
        logger.info("日志查看器已加载 %d 条日志", len(self._entries))
        return len(self._entries)

    def _parse_entry(self, entry: LogEntry) -> None:
        raw = entry.raw
        # 解析标准格式: "2026-07-14 12:00:00 | INFO | {...}"
        m = re.match(r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+\|\s+(\w+)\s+\|\s+(.*)", raw)
        if m:
            entry.timestamp = m.group(1)
            entry.level = m.group(2)
            msg = m.group(3)
            # 尝试解析 JSON
            try:
                entry.parsed = json.loads(msg)
                entry.message = entry.parsed.get("action", msg[:80])
            except json.JSONDecodeError:
                entry.message = msg[:120]
        else:
            entry.message = raw[:120]

    # ---- 查询 ----

    def query(
        self,
        level: str = "",
        component: str = "",
        keyword: str = "",
        action: str = "",
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """查询日志条目。

        Args:
            level: 过滤级别（INFO / WARNING / ERROR）。
            component: 过滤组件名。
            keyword: 关键字搜索（匹配 message）。
            action: 过滤 action 字段。
            offset: 偏移量。
            limit: 每页条数。

        Returns:
            {total, filtered, entries: [{line_number, timestamp, level, message, parsed}]}
        """
        if not self._loaded:
            self.reload()

        filtered = self._entries
        if level:
            filtered = [e for e in filtered if e.level.upper() == level.upper()]
        if component:
            filtered = [e for e in filtered
                        if e.parsed.get("component", "").lower() == component.lower()]
        if action:
            filtered = [e for e in filtered
                        if e.parsed.get("action", "").lower() == action.lower()]
        if keyword:
            filtered = [e for e in filtered if keyword.lower() in e.message.lower()]

        page = filtered[offset:offset + limit]
        return {
            "total": len(self._entries),
            "filtered": len(filtered),
            "returned": len(page),
            "offset": offset,
            "limit": limit,
            "entries": [
                {
                    "line_number": e.line_number,
                    "timestamp": e.timestamp,
                    "level": e.level,
                    "message": e.message,
                    "parsed": e.parsed,
                }
                for e in page
            ],
        }

    def filter(self, level: str = "", module: str = "") -> list[dict]:
        """按级别和模块过滤日志条目。"""
        return self.query(level=level, component=module, limit=10**9)["entries"]

    def paginate(self, page: int, page_size: int = 50) -> dict[str, Any]:
        """分页访问日志条目。page 从 1 开始。"""
        offset = max(0, (page - 1) * page_size)
        return self.query(offset=offset, limit=page_size)

    def stats(self) -> dict[str, Any]:
        """日志统计。"""
        if not self._loaded:
            self.reload()

        level_counts: dict[str, int] = {}
        component_counts: dict[str, int] = {}
        for e in self._entries:
            level_counts[e.level] = level_counts.get(e.level, 0) + 1
            comp = e.parsed.get("component", "")
            if comp:
                component_counts[comp] = component_counts.get(comp, 0) + 1

        return {
            "total": len(self._entries),
            "levels": level_counts,
            "components": component_counts,
            "log_file": self._path,
            "exists": os.path.exists(self._path),
            "size_bytes": os.path.getsize(self._path) if os.path.exists(self._path) else 0,
        }
