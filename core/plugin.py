"""BlueDeer 插件系统：基类、声明式元数据、插件上下文、事件系统。

一个插件可以携带：工具、Agent 类型、事件监听器、CLI 命令、配置项。
插件的生命周期由 PluginManager 管理（见 plugin_manager.py）。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from tools.base_tool import BaseTool
    from modules.base_agent import BaseAgent
    from core.event_bus import EventBus


@dataclass
class PluginMeta:
    """插件声明式元数据（精简版）。"""
    name: str
    version: str
    author: str = ""
    description: str = ""


@dataclass
class PluginManifest:
    """插件声明式元数据（完整版）。"""
    name: str
    version: str
    description: str = ""
    author: str = ""
    homepage: str = ""
    dependencies: list[str] = field(default_factory=list)
    min_bluedeer_version: str = "0.1.0"


class PluginEventSystem:
    """轻量级插件事件系统。

    用法：
        events = PluginEventSystem()
        events.subscribe("task.completed", handler)
        events.emit("task.completed", task_id="123")
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = {}

    def subscribe(self, event: str, handler: Callable) -> None:
        """订阅事件。"""
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(handler)

    def unsubscribe(self, event: str, handler: Callable) -> None:
        """取消订阅。"""
        handlers = self._handlers.get(event, [])
        if handler in handlers:
            handlers.remove(handler)

    def emit(self, event: str, **data) -> None:
        """触发事件，调用所有订阅者。"""
        for handler in self._handlers.get(event, []):
            try:
                handler(**data)
            except Exception:
                logging.getLogger("bluedeer.plugin.event").exception(
                    "事件 %s 处理器 %s 异常", event, handler.__name__
                )

    def clear(self) -> None:
        self._handlers.clear()


class PluginContext:
    """插件运行时上下文，供插件与框架交互。"""

    def __init__(
        self,
        *,
        manifest: PluginManifest,
        tool_registry: Any = None,
        agent_registry: Any = None,
        event_bus: EventBus | None = None,
        config: Any = None,
        data_dir: str = "",
    ) -> None:
        self.manifest = manifest
        self.tool_registry = tool_registry
        self.agent_registry = agent_registry
        self.event_bus = event_bus
        self.config = config
        self.data_dir = data_dir
        self.logger = logging.getLogger(f"bluedeer.plugin.{manifest.name}")
        self.events = PluginEventSystem()

    def register_tool(self, tool: BaseTool) -> None:
        if self.tool_registry is not None:
            self.tool_registry.register(tool)
            self.logger.info("注册工具: %s", tool.name)

    def register_agent(self, agent_cls: type[BaseAgent]) -> None:
        if self.agent_registry is not None:
            self.agent_registry.register(agent_cls)
            self.logger.info("注册 Agent: %s", agent_cls.__name__)

    def subscribe(self, topic: str, handler: Callable) -> None:
        if self.event_bus is not None:
            self.event_bus.subscribe(topic, handler)
            self.logger.info("订阅事件: %s", topic)

    def publish(self, topic: str, data: Any = None) -> None:
        if self.event_bus is not None:
            self.event_bus.publish(topic, data)


class PluginBase(ABC):
    """插件基类——所有插件必须继承并实现 manifest。"""

    @property
    @abstractmethod
    def manifest(self) -> PluginManifest:
        """插件元数据。"""

    @property
    def meta(self) -> PluginMeta:
        """精简元数据（从 manifest 派生）。"""
        m = self.manifest
        return PluginMeta(name=m.name, version=m.version, author=m.author, description=m.description)

    @property
    def config_schema(self) -> dict[str, Any] | None:
        """可选的 JSON Schema 配置校验。"""
        return None

    async def on_load(self, ctx: PluginContext) -> None:
        """插件加载时调用。在此注册工具、Agent、事件监听。"""

    async def on_enable(self) -> None:
        """插件启用时调用。"""

    async def on_disable(self) -> None:
        """插件禁用时调用。"""

    async def on_unload(self) -> None:
        """插件卸载时调用。清理资源。"""

    async def on_ready(self) -> None:
        """框架就绪后调用（所有插件已加载）。"""

    def get_tools(self) -> list[BaseTool]:
        return []

    def get_agents(self) -> list[type[BaseAgent]]:
        return []
