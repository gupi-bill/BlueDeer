"""狡黠狐狸技能包：测试运行 + 修复。

P7 扩容：按测试类型拆分技能（单元/安全/美术规范）。
"""

from __future__ import annotations

import logging
from typing import Any

from core.healer import Healer
from core.test_runner import TestType
from tools.registry import ToolRegistry

logger = logging.getLogger("bluedeer.fox.skills")


class TestRunSkill:
    """测试运行技能：调 TestRunTool 跑测试。

    P7 扩容：支持 test_type 参数，按测试类型选择 pytest 标记。
    """

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tools = tool_registry

    async def run_tests(
        self,
        test_path: str,
        test_type: TestType = TestType.UNIT,
    ) -> dict[str, Any]:
        """运行指定路径的测试。

        Args:
            test_path: 测试文件或目录。
            test_type: 测试类型（P7 扩容）。默认 UNIT。
        """
        return await self._tools.call(
            "test_run",
            {
                "test_path": test_path,
                "test_type": test_type.value,
            },
        )


class SecurityTestSkill:
    """安全扫描测试技能（P7 扩容）。

    调 TestRunTool 跑 security 标记测试。
    """

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tools = tool_registry

    async def run_tests(self, test_path: str) -> dict[str, Any]:
        """运行安全扫描测试。"""
        return await self._tools.call(
            "test_run",
            {
                "test_path": test_path,
                "test_type": TestType.SECURITY.value,
            },
        )


class ArtSpecTestSkill:
    """美术素材规范校验技能（P7 扩容）。

    调 TestRunTool 跑 art_spec 标记测试。
    """

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tools = tool_registry

    async def run_tests(self, test_path: str) -> dict[str, Any]:
        """运行美术规范校验测试。"""
        return await self._tools.call(
            "test_run",
            {
                "test_path": test_path,
                "test_type": TestType.ART_SPEC.value,
            },
        )


class HealSkill:
    """修复技能：封装 Healer 完整闭环。"""

    def __init__(self, healer: Healer) -> None:
        self._healer = healer

    async def heal(
        self, test_path: str, target_file: str | None = None
    ) -> dict[str, Any]:
        """执行完整修复闭环。

        Args:
            test_path: 测试路径。
            target_file: 修复目标文件。

        Returns:
            heal() 结果字典。
        """
        # Healer.heal 是同步方法（subprocess），用 to_thread 包一下
        import asyncio

        return await asyncio.to_thread(
            self._healer.heal,
            test_path,
            target_file,
        )


_SKILL_REGISTRY: dict[str, Any] = {}


def register_skill(name: str, skill: Any) -> None:
    _SKILL_REGISTRY[name] = skill


def get_skill(name: str) -> Any:
    return _SKILL_REGISTRY.get(name)


def list_skills() -> list[str]:
    return list(_SKILL_REGISTRY.keys())
