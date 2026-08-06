"""勤恳海狸技能包：构建 + Git 提交。"""

from __future__ import annotations

import logging
from typing import Any

from core.git_ops import GitOps
from tools.registry import ToolRegistry

logger = logging.getLogger("bluedeer.beaver.skills")


class BuildSkill:
    """构建技能：跑测试 + Git 提交。"""

    def __init__(self, tool_registry: ToolRegistry, git_ops: GitOps) -> None:
        self._tools = tool_registry
        self._git = git_ops

    async def run_tests(self, test_path: str) -> dict[str, Any]:
        """跑测试。"""
        return await self._tools.call("test_run", {"test_path": test_path})

    def git_status(self) -> dict[str, Any]:
        """查 Git 状态。"""
        return self._git.status().to_dict()

    def git_commit(self, message: str, add_all: bool = True) -> dict[str, Any]:
        """Git 提交。

        Args:
            message: commit message。
            add_all: 是否暂存所有改动。

        Returns:
            {"success": bool, "sha": str, "files": [...], "message": str}
        """
        if add_all:
            ok, files = self._git.add_all()
            if not ok:
                return {
                    "success": False,
                    "sha": "",
                    "files": [],
                    "message": "git add 失败",
                }
        else:
            files = []

        ok, sha_or_msg = self._git.commit(message)
        return {
            "success": ok,
            "sha": sha_or_msg if ok else "",
            "files": files,
            "message": sha_or_msg if not ok else "ok",
        }


_BUILD_CACHE: dict[str, dict[str, Any]] = {}


def cache_build_result(key: str, result: dict[str, Any]) -> None:
    _BUILD_CACHE[key] = result


def get_cached_build(key: str) -> dict[str, Any] | None:
    return _BUILD_CACHE.get(key)


def clear_build_cache() -> None:
    _BUILD_CACHE.clear()


def generate_commit_message(
    task_type: str,
    summary: str,
    scope: str = "",
) -> str:
    """生成约定式提交 message。

    格式：<type>(<scope>): <summary>

    Args:
        task_type: 任务类型 → commit type（code→feat, test→test, fix→fix, docs→docs）
        summary: 简述。

    Returns:
        commit message。
    """
    type_map = {
        "code": "feat",
        "architecture": "feat",
        "batch": "chore",
        "voice": "docs",
        "test": "test",
        "fix": "fix",
        "security": "fix",
    }
    commit_type = type_map.get(task_type, "chore")
    if scope:
        return f"{commit_type}({scope}): {summary}"
    return f"{commit_type}: {summary}"
