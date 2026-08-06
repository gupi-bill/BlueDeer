"""BlueDeer 安全扫描工具：READ 级，对代码/参数/路径做安全校验。"""

from __future__ import annotations

import os
from typing import Any

from core.security import SecurityReport, SecurityScanner
from tools.base_tool import BaseTool, ToolCategory


class SecurityScanTool(BaseTool):
    """安全扫描工具。

    category=READ，封装 SecurityScanner.scan_all。
    支持扫描代码字符串 / 文件路径 / 任意文本。
    """

    def __init__(self, scanner: SecurityScanner | None = None) -> None:
        self._scanner = scanner or SecurityScanner()

    @property
    def name(self) -> str:
        return "security_scan"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.READ

    async def execute(self, params: dict[str, Any]) -> Any:
        """扫描代码/路径/文本的安全威胁。

        Args:
            params: 可包含 code / path / text 三选一。
                    code：扫描代码字符串
                    path：扫描指定文件内容
                    text：扫描任意文本

        Returns:
            SecurityReport.to_dict()
        """
        code = params.get("code")
        path = params.get("path")
        text = params.get("text")

        if path:
            return self._scan_file(str(path))
        if code is not None:
            return self._scanner.scan_all(str(code), target="code").to_dict()
        if text is not None:
            return self._scanner.scan_all(str(text), target="text").to_dict()
        raise ValueError("security_scan 需要 code / path / text 之一")

    def _scan_file(self, path: str) -> dict[str, Any]:
        """扫描文件内容。"""
        if not os.path.exists(path):
            return SecurityReport(
                target=path,
                threats=[],
                scanned_at=0.0,
            ).to_dict()
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            return SecurityReport(
                target=path,
                threats=[],
                scanned_at=0.0,
            ).to_dict()
        report = self._scanner.scan_all(content, target=f"file:{path}")
        return report.to_dict()
