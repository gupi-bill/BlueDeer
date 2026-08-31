"""BlueDeer 内置 mock 工具：EchoTool，用于 P1 验证链路。"""

from __future__ import annotations

from typing import Any

from tools.base_tool import BaseTool, ToolCategory


class EchoTool(BaseTool):
    """回显工具，将输入参数原样返回。

    category=READ，无副作用，用于 P1 验证工具调用链路。
    """

    @property
    def name(self) -> str:
        return "echo"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.READ

    async def execute(self, params: dict[str, Any]) -> Any:
        """回显参数。"""
        return {"echoed": params}
