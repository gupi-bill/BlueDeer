"""戒备猬技能包：安全扫描。"""

from __future__ import annotations

import logging
from typing import Any

from core.task import Task
from tools.registry import ToolRegistry

logger = logging.getLogger("bluedeer.hedgehog.skills")


class SecurityScanSkill:
    """安全扫描技能：调 SecurityScanTool 对代码/路径/文本做扫描。"""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tools = tool_registry

    async def scan_code(self, code: str) -> dict[str, Any]:
        """扫描代码字符串。"""
        return await self._tools.call("security_scan", {"code": code})

    async def scan_file(self, path: str) -> dict[str, Any]:
        """扫描文件内容。"""
        return await self._tools.call("security_scan", {"path": path})

    async def scan_text(self, text: str) -> dict[str, Any]:
        """扫描任意文本。"""
        return await self._tools.call("security_scan", {"text": text})

    async def scan_task(self, task: Task) -> dict[str, Any]:
        """根据 task.payload 决定扫描对象。"""
        payload = task.payload
        if "code" in payload:
            return await self.scan_code(str(payload["code"]))
        if "path" in payload:
            return await self.scan_file(str(payload["path"]))
        if "text" in payload:
            return await self.scan_text(str(payload["text"]))
        raise ValueError("hedgehog 任务 payload 必须包含 code / path / text 之一")


_SCAN_HISTORY: list[dict[str, Any]] = []


def record_scan(target: str, risk_level: str, threat_count: int) -> None:
    _SCAN_HISTORY.append(
        {
            "target": target,
            "risk_level": risk_level,
            "threat_count": threat_count,
            "timestamp": __import__("time").time(),
        }
    )
    if len(_SCAN_HISTORY) > 100:
        _SCAN_HISTORY.pop(0)


def scan_history() -> list[dict[str, Any]]:
    return list(_SCAN_HISTORY)


def scan_stats() -> dict[str, Any]:
    total = len(_SCAN_HISTORY)
    high = sum(1 for s in _SCAN_HISTORY if s["risk_level"] == "high")
    return {"total": total, "high_risk": high}
