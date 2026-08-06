"""BlueDeer Agent 注册中心（Agent Marketplace 底座）。

能力：
    - 注册 Agent 类（按模块来源分组）
    - 按名称、能力、标签搜索
    - 查询单个 Agent 的详细信息
    - 列出所有已注册 Agent
    - 热加载：监视插件目录，自动发现并注册新 Agent
"""

from __future__ import annotations

import importlib
import inspect
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.base_agent import BaseAgent
from typing import Any

logger = logging.getLogger("bluedeer.agent_registry")


@dataclass
class AgentInfo:
    name: str
    qualified_name: str
    module: str
    role: str
    description: str
    capabilities: list[str] = field(default_factory=list)
    base_class: str = ""
    version: str = "0.1.0"
    enabled: bool = True
    source: str = "builtin"
    source_url: str = ""
    tags: list[str] = field(default_factory=list)


class AgentRegistry:
    """Agent 注册中心。

    用法：
        registry = AgentRegistry()
        registry.register(FoxAgent)
        registry.register(SquirrelAgent)
        all_agents = registry.list_agents()
        fox_info = registry.get_agent("FoxAgent")
        results = registry.search("test")
    """

    def __init__(self) -> None:
        self._agents: dict[str, AgentInfo] = {}
        self._classes: dict[str, type[BaseAgent]] = {}

    def register(
        self,
        agent_cls: type,
        *,
        source: str = "builtin",
        source_url: str = "",
    ) -> None:
        name = agent_cls.__name__
        mod = inspect.getmodule(agent_cls)
        qual = f"{mod.__name__}.{name}" if mod else name

        role = getattr(agent_cls, "role", name.lower())
        doc = (agent_cls.__doc__ or "").strip()

        caps = []
        if hasattr(agent_cls, "capabilities"):
            caps = (
                list(agent_cls.capabilities)
                if isinstance(agent_cls.capabilities, (list, set))
                else []
            )

        base_cls = agent_cls.__bases__[0].__name__ if agent_cls.__bases__ else ""

        self._agents[name] = AgentInfo(
            name=name,
            qualified_name=qual,
            module=mod.__name__ if mod else "",
            role=role,
            description=doc,
            capabilities=caps,
            base_class=base_cls,
            enabled=True,
            source=source,
            source_url=source_url,
        )
        self._classes[name] = agent_cls
        logger.info("Agent 已注册: %s (%s)", name, qual)

    def unregister(self, name: str) -> bool:
        if name in self._agents:
            del self._agents[name]
            self._classes.pop(name, None)
            return True
        return False

    def list_agents(self) -> list[AgentInfo]:
        return list(self._agents.values())

    def get_agent(self, name: str) -> AgentInfo | None:
        return self._agents.get(name)

    def get_agent_class(self, name: str) -> type | None:
        return self._classes.get(name)

    def search(self, query: str) -> list[AgentInfo]:
        q = query.lower()
        results = []
        for info in self._agents.values():
            if q in info.name.lower():
                results.append(info)
                continue
            if q in info.description.lower():
                results.append(info)
                continue
            if q in info.role.lower():
                results.append(info)
                continue
            for cap in info.capabilities:
                if q in cap.lower():
                    results.append(info)
                    break
                continue
            for tag in info.tags:
                if q in tag.lower():
                    results.append(info)
                    break
        return results

    def get_by_module(self, module_name: str) -> list[AgentInfo]:
        return [a for a in self._agents.values() if a.module.startswith(module_name)]

    def set_enabled(self, name: str, enabled: bool) -> bool:
        info = self._agents.get(name)
        if info is None:
            return False
        info.enabled = enabled
        return True

    def scan_package(self, package: str) -> None:
        """扫描一个包，自动注册模块内所有 BaseAgent 子类。"""
        try:
            importlib.import_module(package)
        except ImportError:
            logger.warning("扫描包失败: %s", package)
            return
        for name, cls in inspect.getmembers(
            sys.modules[package],
            lambda o: inspect.isclass(o)
            and issubclass(o, object)
            and o.__module__.startswith(package)
            and "BaseAgent" in [b.__name__ for b in o.__mro__],
        ):
            self.register(cls)

    def auto_register(self, plugin_dir: str = "plugins") -> int:
        """自动发现并注册 plugin_dir 下的所有 Agent 类。

        Returns:
            新注册的 Agent 数量。
        """
        plugin_path = Path(plugin_dir)
        if not plugin_path.is_dir():
            logger.warning("插件目录不存在: %s", plugin_dir)
            return 0

        count = 0
        sys.path.insert(0, str(plugin_path.parent))
        try:
            for pyfile in sorted(plugin_path.glob("*.py")):
                if pyfile.name.startswith("_"):
                    continue
                mod_name = f"{plugin_path.name}.{pyfile.stem}"
                if mod_name in sys.modules:
                    continue
                try:
                    importlib.import_module(mod_name)
                    for _, cls in inspect.getmembers(
                        sys.modules[mod_name],
                        lambda o: inspect.isclass(o)
                        and "BaseAgent"
                        in [b.__name__ for b in getattr(o, "__mro__", [])],
                    ):
                        name = cls.__name__
                        if name not in self._agents:
                            self.register(cls, source="plugin")
                            count += 1
                except Exception:
                    logger.exception("加载插件模块失败: %s", mod_name)
        finally:
            sys.path.pop(0)
        logger.info("auto_register: 新注册 %d 个 Agent", count)
        return count

    def watch(
        self, plugin_dir: str = "plugins", interval: float = 5.0, stop_event: Any = None
    ) -> None:
        """热加载守护：轮询 plugin_dir，自动注册新 Agent。

        Args:
            plugin_dir: 插件目录。
            interval: 轮询间隔（秒）。
            stop_event: threading.Event，设置后停止。
        """
        logger.info(
            "热加载监视启动: plugin_dir=%s, interval=%.1fs", plugin_dir, interval
        )
        while not (stop_event and stop_event.is_set()):
            try:
                self.auto_register(plugin_dir)
            except Exception:
                logger.exception("watch 轮询异常")
            time.sleep(interval)
