import logging
logger = logging.getLogger(__name__)
from typing import Any

from tools.base_tool import BaseTool, ToolCategory


class GreetTool(BaseTool):
    """问候工具。"""

    @property
    def name(self) -> str:
        return "greet"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.READ

    async def execute(self, params: dict[str, Any]) -> Any:
        name = params.get("name", "World")
        return {"message": f"Hello, {name}!"}
