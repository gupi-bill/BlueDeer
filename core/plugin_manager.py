"""BlueDeer 插件管理器：发现、加载、生命周期管理。"""

from __future__ import annotations

import importlib
import json
import logging
import os
import sys
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from packaging.version import Version

from core.exceptions import PluginLoadError
from core.plugin import PluginBase, PluginContext

if TYPE_CHECKING:

    from core.event_bus import EventBus

logger = logging.getLogger("bluedeer.plugin_manager")

_DEFAULT_PLUGIN_DIR = "plugins"
_STATE_FILE = "data/plugin_state.json"


class VersionConflict(Exception):
    pass


import enum


class LifecycleStage(enum.Enum):
    CREATED = "created"
    INIT = "init"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


LIFECYCLE_ORDER: list[LifecycleStage] = [
    LifecycleStage.CREATED,
    LifecycleStage.INIT,
    LifecycleStage.STARTING,
    LifecycleStage.RUNNING,
    LifecycleStage.STOPPING,
    LifecycleStage.STOPPED,
]


class LazyPlugin:
    def __init__(self, name: str, path: Path, manager: PluginManager) -> None:
        self._name = name
        self._path = path
        self._manager = manager
        self._plugin: PluginBase | None = None

    @property
    def resolved(self) -> bool:
        return self._plugin is not None

    async def get(self) -> PluginBase:
        if self._plugin is None:
            self._plugin = await self._manager._do_load(self._name)
        return self._plugin


class PluginManager:
    def __init__(
        self,
        plugin_dir: str = "",
        tool_registry: Any = None,
        agent_registry: Any = None,
        event_bus: EventBus | None = None,
        config: Any = None,
    ) -> None:
        self._plugin_dir = plugin_dir or _DEFAULT_PLUGIN_DIR
        self._tool_registry = tool_registry
        self._agent_registry = agent_registry
        self._event_bus = event_bus
        self._config = config

        self._plugins: dict[str, PluginBase] = {}
        self._contexts: dict[str, PluginContext] = {}
        self._states: dict[str, bool] = {}
        self._lazy: dict[str, LazyPlugin] = OrderedDict()
        self._lifecycles: dict[str, LifecycleStage] = {}
        self._load_state()

    @property
    def loaded_plugins(self) -> list[PluginBase]:
        return list(self._plugins.values())

    @property
    def plugin_names(self) -> list[str]:
        return list(self._plugins.keys())

    def discover(self) -> list[str]:
        pdir = Path(self._plugin_dir)
        if not pdir.is_dir():
            logger.info("插件目录 %s 不存在，跳过", self._plugin_dir)
            return []

        found: list[str] = []
        for entry in sorted(pdir.iterdir()):
            if entry.is_dir() and (entry / "__init__.py").is_file():
                found.append(entry.name)
            elif entry.is_file() and entry.suffix == ".py" and entry.stem != "__init__":
                found.append(entry.stem)

        for name in found:
            if name not in self._lazy and name not in self._plugins:
                self._lazy[name] = LazyPlugin(name, pdir, self)

        logger.info("发现 %d 个插件: %s", len(found), found)
        return found

    async def load_all(self, plugin_names: list[str] | None = None) -> list[str]:
        if plugin_names is None:
            plugin_names = list(self._lazy.keys()) or self.discover()

        loaded: list[str] = []
        for name in plugin_names:
            try:
                await self._load_single(name)
                loaded.append(name)
            except PluginLoadError as e:
                logger.error("插件 %s 加载失败: %s", name, e)

        return loaded

    async def load_one(self, name: str) -> bool:
        try:
            await self._load_single(name)
            return True
        except PluginLoadError as e:
            logger.error("插件 %s 加载失败: %s", name, e)
            return False

    # ============== 生命周期 ==============

    def get_lifecycle(self, name: str) -> LifecycleStage:
        return self._lifecycles.get(name, LifecycleStage.CREATED)

    async def init_plugin(self, name: str) -> bool:
        """初始化插件（不启动）。"""
        if name not in self._plugins:
            return False
        self._lifecycles[name] = LifecycleStage.INIT
        try:
            p = self._plugins[name]
            if hasattr(p, "on_init"):
                await p.on_init()
            logger.info("插件 %s 已初始化", name)
            return True
        except Exception as e:
            self._lifecycles[name] = LifecycleStage.FAILED
            logger.error("插件 %s 初始化异常: %s", name, e)
            return False

    async def start_plugin(self, name: str) -> bool:
        """启动插件。"""
        if name not in self._plugins:
            return False
        self._lifecycles[name] = LifecycleStage.STARTING
        try:
            p = self._plugins[name]
            if hasattr(p, "on_start"):
                await p.on_start()
            self._lifecycles[name] = LifecycleStage.RUNNING
            logger.info("插件 %s 已启动", name)
            return True
        except Exception as e:
            self._lifecycles[name] = LifecycleStage.FAILED
            logger.error("插件 %s 启动异常: %s", name, e)
            return False

    async def stop_plugin(self, name: str) -> bool:
        """停止插件。"""
        if name not in self._plugins:
            return False
        self._lifecycles[name] = LifecycleStage.STOPPING
        try:
            p = self._plugins[name]
            if hasattr(p, "on_stop"):
                await p.on_stop()
            self._lifecycles[name] = LifecycleStage.STOPPED
            logger.info("插件 %s 已停止", name)
            return True
        except Exception as e:
            self._lifecycles[name] = LifecycleStage.FAILED
            logger.error("插件 %s 停止异常: %s", name, e)
            return False

    async def ready_all(self) -> None:
        """通知所有已加载插件框架就绪。"""
        for name, plugin in self._plugins.items():
            if self._states.get(name, True):
                try:
                    await plugin.on_ready()
                    await self.init_plugin(name)
                    await self.start_plugin(name)
                except Exception as e:
                    logger.error("插件 %s on_ready 异常: %s", name, e)

    async def shutdown(self) -> None:
        """卸载所有插件。"""
        for name in list(self._plugins.keys()):
            try:
                await self.stop_plugin(name)
                plugin = self._plugins[name]
                await plugin.on_unload()
                logger.info("插件 %s 已卸载", name)
            except Exception as e:
                logger.error("插件 %s 卸载异常: %s", name, e)
        self._plugins.clear()
        self._contexts.clear()
        self._lifecycles.clear()
        self._save_state()

    # ============== 启停控制 ==============

    def enable(self, name: str) -> bool:
        if name not in self._plugins:
            return False
        self._states[name] = True
        self._save_state()
        logger.info("插件 %s 已启用", name)
        return True

    def disable(self, name: str) -> bool:
        if name not in self._plugins:
            return False
        self._states[name] = False
        self._save_state()
        logger.info("插件 %s 已禁用", name)
        return True

    def is_enabled(self, name: str) -> bool:
        return self._states.get(name, True)

    def get_status(self, name: str) -> dict[str, Any]:
        if name not in self._plugins:
            return {"status": "not_found"}
        ctx = self._contexts.get(name)
        return {
            "status": "loaded" if self._states.get(name, True) else "disabled",
            "lifecycle": self.get_lifecycle(name).value,
            "manifest": {
                "name": ctx.manifest.name if ctx else name,
                "version": ctx.manifest.version if ctx else "?",
                "description": ctx.manifest.description if ctx else "",
            },
            "enabled": self._states.get(name, True),
        }

    # ============== 内部 ==============

    async def _load_single(self, name: str) -> None:
        if name in self._plugins:
            logger.debug("插件 %s 已加载，跳过", name)
            return

        if not self._states.get(name, True):
            logger.info("插件 %s 已禁用，跳过加载", name)
            return

        if name in self._lazy:
            p = await self._lazy[name].get()
            self._plugins[name] = p
            return

        plugin = await self._do_load(name)
        self._plugins[name] = plugin

    async def _do_load(self, name: str) -> PluginBase:
        pdir = Path(self._plugin_dir)
        module: Any = None

        logger.info("加载插件: %s", name)

        sys.path.insert(0, str(pdir.parent))

        try:
            if (pdir / name / "__init__.py").is_file():
                module = importlib.import_module(f"{pdir.name}.{name}")
            elif (pdir / f"{name}.py").is_file():
                spec = importlib.util.spec_from_file_location(
                    f"_plugin_{name}",
                    str(pdir / f"{name}.py"),
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[spec.name] = module
                    spec.loader.exec_module(module)
                else:
                    raise PluginLoadError(f"无法加载 {pdir / name}.py")
            else:
                raise PluginLoadError(f"未找到插件 {name}")
        except Exception as e:
            raise PluginLoadError(f"导入失败: {e}") from e
        finally:
            if sys.path and sys.path[0] == str(pdir.parent):
                sys.path.pop(0)

        plugin_cls = self._find_plugin_class(module, name)
        if plugin_cls is None:
            raise PluginLoadError(f"{name} 中未找到 PluginBase 子类")

        plugin = plugin_cls()
        self._check_version_conflict(plugin)
        data_dir = str(Path(self._plugin_dir) / name / "data")

        ctx = PluginContext(
            manifest=plugin.manifest,
            tool_registry=self._tool_registry,
            agent_registry=self._agent_registry,
            event_bus=self._event_bus,
            config=self._config,
            data_dir=data_dir,
        )

        try:
            for tool in plugin.get_tools():
                ctx.register_tool(tool)
            for agent_cls in plugin.get_agents():
                ctx.register_agent(agent_cls)

            await plugin.on_load(ctx)
        except Exception as e:
            raise PluginLoadError(f"on_load 异常: {e}") from e

        self._contexts[name] = ctx
        logger.info(
            "插件 %s v%s 加载成功", plugin.manifest.name, plugin.manifest.version
        )
        return plugin

    def _check_version_conflict(self, plugin: PluginBase) -> None:
        v = Version(plugin.manifest.version)
        for existing in self._plugins.values():
            ev = Version(existing.manifest.version)
            if v.major != ev.major and v.minor != ev.minor:
                logger.warning(
                    "版本冲突: %s v%s vs %s v%s (major/minor 不匹配)",
                    plugin.manifest.name,
                    v,
                    existing.manifest.name,
                    ev,
                )
                raise VersionConflict(
                    f"{plugin.manifest.name} v{v} 与 {existing.manifest.name} v{ev} 冲突"
                )

    @staticmethod
    def version_conflict_check(
        plugin_a_name: str,
        plugin_a_version: str,
        plugin_b_name: str,
        plugin_b_version: str,
    ) -> dict[str, Any]:
        """静态版本冲突检测，返回冲突详情。"""
        va = Version(plugin_a_version)
        vb = Version(plugin_b_version)
        major_conflict = va.major != vb.major
        minor_conflict = va.minor != vb.minor
        return {
            "conflict": major_conflict or minor_conflict,
            "plugin_a": {"name": plugin_a_name, "version": plugin_a_version},
            "plugin_b": {"name": plugin_b_name, "version": plugin_b_version},
            "reasons": [],
        }

    def _find_plugin_class(self, module: Any, name: str) -> type[PluginBase] | None:
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if (
                isinstance(obj, type)
                and issubclass(obj, PluginBase)
                and obj is not PluginBase
            ):
                return obj
        return None

    def _load_state(self) -> None:
        try:
            from core.database import Database

            self._states = Database().load_plugin_states_bool()
        except Exception as e:
            logger.warning("从数据库加载插件状态失败: %s", e)
            self._states = {}
        # 回退 JSON
        if not self._states and os.path.exists(_STATE_FILE):
            try:
                with open(_STATE_FILE, "r", encoding="utf-8") as f:
                    self._states = json.load(f)
            except Exception as e:
                logger.warning("加载插件状态 JSON 回退失败: %s", e)

    def _save_state(self) -> None:
        try:
            from core.database import Database

            Database().save_plugin_states_bool(self._states)
        except Exception as e:
            logger.warning("保存插件状态到数据库失败: %s", e)
        # 向后兼容 JSON 写入
        try:
            os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
            with open(_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._states, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("保存插件状态 JSON 回退失败: %s", e)
