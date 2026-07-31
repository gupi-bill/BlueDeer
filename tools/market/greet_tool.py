from tools.base_tool import BaseTool, ToolCategory
from typing import Any
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