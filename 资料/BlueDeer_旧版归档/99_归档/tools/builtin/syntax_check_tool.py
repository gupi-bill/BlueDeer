"""BlueDeer 语法校验工具：READ 级，用 py_compile 校验 Python 语法。"""

from __future__ import annotations

import os
import py_compile
import tempfile
from typing import Any

from tools.base_tool import BaseTool, ToolCategory


class SyntaxCheckTool(BaseTool):
    """Python 语法校验工具。

    category=READ，用 py_compile.compile 校验语法。
    支持校验文件路径或直接校验代码字符串。
    """

    @property
    def name(self) -> str:
        return "syntax_check"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.READ

    async def execute(self, params: dict[str, Any]) -> Any:
        """校验 Python 语法。

        Args:
            params: 可包含 path（文件路径）或 code（代码字符串），二选一。

        Returns:
            {"valid": True/False, "error": 错误信息或 None}
        """
        path = params.get("path")
        code = params.get("code")

        if path:
            return self._check_file(str(path))
        elif code:
            return self._check_code(str(code))
        else:
            raise ValueError("syntax_check 需要 path 或 code 参数")

    def _check_file(self, path: str) -> dict[str, Any]:
        """校验文件语法。"""
        if not os.path.exists(path):
            return {"valid": False, "error": f"文件不存在: {path}"}
        try:
            py_compile.compile(path, doraise=True)
            return {"valid": True, "error": None}
        except py_compile.PyCompileError as e:
            return {"valid": False, "error": str(e)}

    def _check_code(self, code: str) -> dict[str, Any]:
        """校验代码字符串语法。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name
        try:
            return self._check_file(tmp_path)
        finally:
            os.unlink(tmp_path)
