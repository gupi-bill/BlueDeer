"""BlueDeer 测试运行工具：READ 级，封装 TestRunner。"""

from __future__ import annotations

from typing import Any

from core.test_runner import TestRunner, TestType
from tools.base_tool import BaseTool, ToolCategory


class TestRunTool(BaseTool):
    """测试运行工具。

    category=READ，封装 TestRunner.run。
    参数：test_path（测试文件或目录）。
    P7 扩容：支持 test_type 参数（unit/integration/security/art_spec/commit_lint）。
    """

    # 抑制 pytest 收集警告
    __test__ = False

    def __init__(self, runner: TestRunner | None = None) -> None:
        self._runner = runner or TestRunner()

    @property
    def name(self) -> str:
        return "test_run"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.READ

    async def execute(self, params: dict[str, Any]) -> Any:
        """运行测试。

        Args:
            params: {"test_path": str, "test_type"?: str}

        Returns:
            TestRunResult.to_dict()
        """
        test_path = params.get("test_path")
        if not test_path:
            raise ValueError("test_run 需要 test_path 参数")
        # P7 扩容：解析 test_type（兼容字符串与枚举）
        test_type_str = params.get("test_type")
        test_type = TestType.UNIT
        if test_type_str:
            try:
                test_type = TestType(test_type_str)
            except ValueError:
                # 未知类型降级为 UNIT
                test_type = TestType.UNIT
        result = self._runner.run(str(test_path), test_type=test_type)
        return result.to_dict()
