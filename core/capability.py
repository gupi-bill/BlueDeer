"""BlueDeer 能力沙箱：基于能力的访问控制（Capability-based Security）。

每个 Agent 声明其所需能力（capabilities），运行时 CapabilityEnforcer
拦截未授权操作。与 ToolCategory 层级互补：
- ToolCategory：工具本身的危险等级（0-7）
- Capability：Agent 被授权的操作类型
"""

from __future__ import annotations

import logging
from enum import Enum
from itertools import chain
from typing import Any

logger = logging.getLogger("bluedeer.capability")


class Capability(Enum):
    """能力类型枚举。

    每个 Agent 在创建时声明拥有的能力。
    """

    FILE_READ = "file.read"
    FILE_CREATE = "file.create"
    FILE_MODIFY = "file.modify"
    FILE_DELETE = "file.delete"
    DB_READWRITE = "db.readwrite"
    NETWORK_HTTP = "network.http"
    SYSTEM_SHELL = "system.shell"
    CODE_EXECUTE = "code.execute"
    SECURITY_SCAN = "security.scan"
    RAG_QUERY = "rag.query"
    RAG_INGEST = "rag.ingest"
    AGENT_COMMUNICATE = "agent.communicate"
    TOOL_MANAGE = "tool.manage"
    # 010 系列新增：大厂 Agent 能力映射（本地优先，云端可选）
    DESKTOP_CONTROL = "desktop.control"  # Anthropic Computer Use 思路
    BROWSER_WEB = "browser.web"          # Perplexity Comet 思路
    BACKGROUND_TASK = "background.task"  # Google Spark 思路
    SUBAGENT_SPAWN = "subagent.spawn"    # Google Antigravity 思路


_CAPABILITY_STR_MAP: dict[str, Capability] = {e.value: e for e in Capability}


def parse_capability(value: str) -> Capability:
    """将字符串解析为 Capability，未知值抛 ValueError。"""
    c = _CAPABILITY_STR_MAP.get(value)
    if c is not None:
        return c
    raise ValueError(f"未知能力: {value}")


def parse_capabilities(*values: str) -> set[Capability]:
    """批量解析能力字符串。"""
    return {parse_capability(v) for v in values}


class CapabilityViolation(Exception):
    """Agent 不具备所需能力时抛出。"""

    def __init__(
        self,
        agent_id: str,
        capability: Capability | set[Capability],
        detail: str = "",
    ) -> None:
        caps = capability if isinstance(capability, set) else {capability}
        cap_str = ", ".join(sorted(c.value for c in caps))
        msg = f"Agent '{agent_id}' 缺少能力 [{cap_str}]"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)
        self.agent_id = agent_id
        self.capabilities = caps


class CapabilityEnforcer:
    """能力执行器。

    在 Agent 和 ToolRegistry 中嵌入，拦截未授权的工具调用。
    """

    def __init__(
        self, agent_id: str, capabilities: set[Capability] | None = None
    ) -> None:
        self._agent_id = agent_id
        self._capabilities: set[Capability] = capabilities or set()

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def capabilities(self) -> frozenset[Capability]:
        return frozenset(self._capabilities)

    def add(self, *caps: Capability) -> None:
        self._capabilities.update(caps)

    def remove(self, *caps: Capability) -> None:
        for c in caps:
            self._capabilities.discard(c)

    def check(self, required: Capability | set[Capability]) -> bool:
        if isinstance(required, Capability):
            return required in self._capabilities
        return required.issubset(self._capabilities)

    def assert_capability(
        self, required: Capability | set[Capability], detail: str = ""
    ) -> None:
        if not self.check(required):
            raise CapabilityViolation(self._agent_id, required, detail)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self._agent_id,
            "capabilities": sorted(c.value for c in self._capabilities),
        }

    def validate(self, context: dict) -> bool:
        """检查 context 中要求的 capability 是否都具备。"""
        required = context.get("required_capabilities", [])
        for r in required:
            if isinstance(r, str):
                try:
                    r = parse_capability(r)
                except ValueError:
                    return False
            if not self.check(r):
                return False
        return True

    @staticmethod
    def compose(*capabilities: CapabilityEnforcer) -> CapabilityEnforcer:
        """合并多个 CapabilityEnforcer 的能力为新的 enforcer。"""
        combined = set(chain.from_iterable(c.capabilities for c in capabilities))
        agent_ids = "+".join(sorted({c.agent_id for c in capabilities}))
        return CapabilityEnforcer(agent_id=agent_ids, capabilities=combined)


# 预定义角色→能力映射（默认配置）
DEFAULT_ROLE_CAPABILITIES: dict[str, set[Capability]] = {
    "demo": parse_capabilities(
        "agent.communicate",
    ),
    "全栈代码开发": parse_capabilities(
        "file.read",
        "file.create",
        "file.modify",
        "file.delete",
        "rag.query",
        "rag.ingest",
        "agent.communicate",
        "subagent.spawn",
        "background.task",
    ),
    "测试质量": parse_capabilities(
        "file.read",
        "file.create",
        "file.modify",
        "rag.query",
        "rag.ingest",
        "agent.communicate",
    ),
    "构建部署": parse_capabilities(
        "file.read",
        "file.create",
        "file.modify",
        "rag.query",
        "rag.ingest",
        "network.http",
        "agent.communicate",
        "desktop.control",
        "browser.web",
        "background.task",
    ),
    "安全审计": parse_capabilities(
        "file.read",
        "security.scan",
        "rag.query",
        "rag.ingest",
        "agent.communicate",
    ),
    "状态播报": parse_capabilities(
        "file.read",
        "rag.query",
        "agent.communicate",
    ),
    "安全测试": parse_capabilities(
        "file.read",
        "security.scan",
        "rag.query",
        "rag.ingest",
        "agent.communicate",
    ),
    "美术规范测试": parse_capabilities(
        "file.read",
        "file.create",
        "rag.query",
        "rag.ingest",
        "agent.communicate",
    ),
    "静态扫描": parse_capabilities(
        "file.read",
        "security.scan",
        "rag.query",
        "agent.communicate",
    ),
    "运行时审计": parse_capabilities(
        "file.read",
        "security.scan",
        "rag.query",
        "rag.ingest",
        "agent.communicate",
    ),
    "密钥管理": parse_capabilities(
        "file.read",
        "security.scan",
        "rag.query",
        "agent.communicate",
    ),
}
