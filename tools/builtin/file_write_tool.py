"""BlueDeer 文件写入工具：MUTATE 级，带路径遍历防护。"""

from __future__ import annotations

import os
from typing import Any

from tools.base_tool import BaseTool, ToolCategory


class FileWriteTool(BaseTool):
    """文件写入工具。

    category=MUTATE，写入文件并自动创建父目录。
    内置路径遍历防护：禁止包含 .. 的路径。
    """

    @property
    def name(self) -> str:
        return "file_write"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.MUTATE

    async def execute(self, params: dict[str, Any]) -> Any:
        """写入文件。

        Args:
            params: 必须包含 path（文件路径）和 content（文件内容）。

        Returns:
            {"path": 写入路径, "bytes": 写入字节数}

        Raises:
            ValueError: 路径包含 .. 或参数缺失。
            OSError: 文件写入失败。
        """
        path = params.get("path")
        content = params.get("content")

        if not path:
            raise ValueError("file_write 缺少参数: path")
        if content is None:
            raise ValueError("file_write 缺少参数: content")

        # 路径遍历防护
        normalized = os.path.normpath(str(path))
        if ".." in normalized.split(os.sep):
            raise ValueError(f"路径遍历被拦截: {path}")

        # 自动创建父目录
        parent = os.path.dirname(normalized)
        if parent:
            os.makedirs(parent, exist_ok=True)

        data = content.encode("utf-8") if isinstance(content, str) else content
        with open(normalized, "wb") as f:
            f.write(data)

        return {"path": normalized, "bytes": len(data)}
