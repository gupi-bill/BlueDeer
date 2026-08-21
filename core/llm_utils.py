"""BlueDeer LLM 工具函数库。

集中管理各 Agent Loop 中重复的 prompt 构建、模型调用与响应解析逻辑。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from core.task import TokenUsage

logger = logging.getLogger("bluedeer.llm_utils")


def build_prompt(*parts: str, separator: str = "\n\n") -> str:
    """将多个 prompt 片段拼接为完整 prompt。

    Args:
        *parts: prompt 片段。
        separator: 片段分隔符。

    Returns:
        拼接后的完整 prompt 字符串。
    """
    return separator.join(p.strip() for p in parts if p.strip())


def parse_tasks_from_json(
    content: str, default_type: str = "auto"
) -> list[dict[str, Any]]:
    """从模型响应中解析任务列表（JSON 数组）。

    Args:
        content: 模型原始响应内容。
        default_type: 当 JSON 中缺少 type 字段时使用的默认值。

    Returns:
        解析后的任务字典列表，每个字典至少包含 id/description/type。
    """
    tasks: list[dict[str, Any]] = []
    try:
        data = json.loads(content)
        if isinstance(data, list):
            tasks = [
                {
                    "id": f"t{i}",
                    "description": item.get("description", ""),
                    "type": item.get("type", default_type),
                }
                for i, item in enumerate(data)
                if item.get("description")
            ]
    except (json.JSONDecodeError, TypeError):
        logger.debug("无法从响应解析 JSON 任务列表: %s", content[:100])
    return tasks


def parse_numbered_tasks(content: str) -> list[dict[str, Any]]:
    """从模型响应中解析编号任务列表（格式：1. 任务描述）。

    Args:
        content: 模型原始响应内容。

    Returns:
        解析后的任务字典列表。
    """
    tasks: list[dict[str, Any]] = []
    for line in content.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if line[0].isdigit() and ". " in line:
            desc = line.split(". ", 1)[1].strip()
            if desc:
                tasks.append(
                    {"id": f"t{len(tasks)}", "description": desc, "type": "auto"}
                )
    return tasks


def safe_get(data: dict[str, Any], key: str, default: Any = None) -> Any:
    """安全地从字典中获取值。

    Args:
        data: 源字典。
        key: 要获取的键。
        default: 键不存在时的默认值。

    Returns:
        对应的值或默认值。
    """
    if isinstance(data, dict):
        return data.get(key, default)
    return default


def extract_token_usage(response: Any) -> TokenUsage:
    """从模型响应中提取 token 使用情况。

    Args:
        response: 模型响应对象，期望包含 tokens_in/tokens_out 属性。

    Returns:
        TokenUsage 对象。
    """
    try:
        return TokenUsage(
            tokens_in=getattr(response, "tokens_in", 0),
            tokens_out=getattr(response, "tokens_out", 0),
        )
    except Exception:
        logger.debug("提取 TokenUsage 失败，返回默认值", exc_info=True)
        return TokenUsage()
