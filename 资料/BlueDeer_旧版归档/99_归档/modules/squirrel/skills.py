"""较真松鼠技能包：代码生成、文件写入、语法校验。"""

from __future__ import annotations

import logging
from typing import Any

from core.task import Task
from models.client import ModelClient
from tools.registry import ToolRegistry

_CODE_TEMPLATE_CACHE: dict[str, str] = {}


def cache_template(name: str, template: str) -> None:
    _CODE_TEMPLATE_CACHE[name] = template


def get_template(name: str) -> str | None:
    return _CODE_TEMPLATE_CACHE.get(name)


def list_templates() -> list[str]:
    return list(_CODE_TEMPLATE_CACHE.keys())


def clear_templates() -> None:
    _CODE_TEMPLATE_CACHE.clear()


logger = logging.getLogger("bluedeer.squirrel.skills")

# 默认温度参数：代码生成用低温度，减少幻觉
_DEFAULT_TEMPERATURE = 0.2


class CodeGenSkill:
    """代码生成技能：构建 prompt → 调 LLM → 返回代码字符串。"""

    def __init__(self, model_client: ModelClient) -> None:
        self._model = model_client

    async def generate(self, task: Task, prompt: str) -> str:
        """调用模型生成代码。

        Args:
            task: 触发生成的任务。
            prompt: 代码生成提示词。

        Returns:
            生成的代码字符串。
        """
        response = await self._model.complete(
            prompt,
            temperature=_DEFAULT_TEMPERATURE,
        )
        logger.info(
            "代码生成完成: task=%s, tokens=%d",
            task.id,
            response.tokens_in + response.tokens_out,
        )
        return response.content


class FileWriteSkill:
    """文件写入技能：调 FileWriteTool 将代码写入文件。"""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tools = tool_registry

    async def write(self, path: str, content: str) -> dict[str, Any]:
        """写入文件。

        Args:
            path: 目标文件路径。
            content: 文件内容。

        Returns:
            FileWriteTool 的执行结果。
        """
        return await self._tools.call("file_write", {"path": path, "content": content})


class SyntaxCheckSkill:
    """语法校验技能：调 SyntaxCheckTool 校验 Python 语法。"""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tools = tool_registry

    async def check_file(self, path: str) -> dict[str, Any]:
        """校验文件语法。

        Args:
            path: 文件路径。

        Returns:
            {"valid": True/False, "error": ...}
        """
        return await self._tools.call("syntax_check", {"path": path})

    async def check_code(self, code: str) -> dict[str, Any]:
        """校验代码字符串语法。

        Args:
            code: 代码字符串。

        Returns:
            {"valid": True/False, "error": ...}
        """
        return await self._tools.call("syntax_check", {"code": code})
