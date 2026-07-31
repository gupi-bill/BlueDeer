"""BlueDeer mock 模型客户端，用于 P1/P2 验证路由与审计链路。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from models.client import ModelClient, ModelResponse

# 代码生成 mock 模板：返回有效 Python 代码
_CODE_MOCK_TEMPLATE = """\
# 由 MockClient 生成的模板代码
# 真实模式下将由 Doubao-Seed-Code 生成

def add(a, b):
    \"\"\"返回两数之和。\"\"\"
    return a + b
"""


@dataclass
class Scenario:
    name: str
    expected_requests: list[dict[str, Any]] = field(default_factory=list)
    responses: list[dict[str, Any]] = field(default_factory=list)
    current_index: int = 0

    def add_step(self, request_match: dict[str, Any], response: dict[str, Any]) -> None:
        self.expected_requests.append(request_match)
        self.responses.append(response)


class MockClient(ModelClient):
    """mock 模型客户端。

    返回固定/模板响应，附带模拟 token 计数（基于 prompt 长度）。
    P2+ 将被真实 Doubao API 客户端替换。

    当模型名包含 "Code" 时，返回有效 Python 代码模板（便于 P2 语法校验链路验证）。
    """

    def __init__(self, name: str = "mock") -> None:
        self._name = name
        self._scenarios: dict[str, Scenario] = {}
        self._active_scenario: str | None = None

    def register_scenario(self, name: str, scenario: Scenario) -> None:
        self._scenarios[name] = scenario

    def use_scenario(self, name: str) -> None:
        if name not in self._scenarios:
            raise ValueError(f"场景 '{name}' 未注册")
        self._active_scenario = name

    @property
    def model_name(self) -> str:
        return self._name

    async def complete(self, prompt: str, **kwargs: object) -> ModelResponse:
        """返回模板响应，模拟 token 计数。"""
        tokens_in = max(1, len(prompt) // 4)

        if self._active_scenario:
            scenario = self._scenarios[self._active_scenario]
            if scenario.current_index < len(scenario.responses):
                resp_data = scenario.responses[scenario.current_index]
                scenario.current_index += 1
                content = resp_data.get("content", "")
            else:
                content = f"[Scenario:{self._active_scenario}] 已无更多响应"
        elif "Code" in self._name:
            content = _CODE_MOCK_TEMPLATE
        else:
            content = f"[MockClient:{self._name}] 已接收 prompt（{len(prompt)} 字符），模拟推理完成。"

        tokens_out = max(1, len(content) // 4)
        return ModelResponse(content=content, tokens_in=tokens_in, tokens_out=tokens_out)
