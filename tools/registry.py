"""BlueDeer 统一工具注册表：注册、校验、执行、重试/熔断。

P1 扩容（A 级）：
- 权限分级 3 → 8 级（READ/FILE_CREATE/FILE_MODIFY/FILE_DELETE/DB_READWRITE/NETWORK_REQUEST/SYSTEM_TERMINAL/HAZARDOUS）
- 前置安全校验：NETWORK_REQUEST 及以上三级都校验（原仅 HAZARDOUS）
- 新增 list_by_category / category_stats 按等级查询工具
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
import time
from typing import Any

from core.capability import CapabilityEnforcer, parse_capability
from core.config import get_config
from core.exceptions import ToolExecutionError, ToolNotFoundError, ToolValidationError
from tools.base_tool import BaseTool, ToolCategory, category_level, needs_security_check

# ruff: noqa: F821

logger = logging.getLogger("bluedeer.tools")


class ToolRegistry:
    """统一工具注册表。

    所有工具执行必须走此入口：
    1. JSON schema 校验参数（P1 基础类型校验）
    2. NETWORK_REQUEST 及以上分级强制前置安全校验（P1 扩容：原仅 HAZARDOUS）
    3. 执行；失败重试 N 次 → 熔断 stub → 上报

    P1 扩容（A 级）：
    - 8 级权限分级（详见 tools.base_tool.ToolCategory）
    - list_by_category(category) 按等级筛选工具
    - category_stats() 返回各等级工具数量统计
    """

    def __init__(
        self,
        max_retries: int | None = None,
        on_hazardous: Any = None,
        capability_enforcer: CapabilityEnforcer | None = None,
    ) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._max_retries = (
            max_retries if max_retries is not None else get_config().tool.max_retries
        )
        # 高危工具前置安全校验 hook（P5 由戒备猬填充，P1 默认放行但记录日志）
        self._on_hazardous = on_hazardous or self._default_hazardous_check
        # 熔断状态：tool_name → 连续失败次数
        self._circuit_breaker: dict[str, int] = {}
        self._circuit_threshold = get_config().tool.circuit_threshold
        # 能力沙箱执行器（可选）
        self._capability_enforcer = capability_enforcer

    def register(self, tool: BaseTool) -> None:
        """注册工具。"""
        if tool.name in self._tools:
            logger.warning("工具 %s 已注册，将被覆盖", tool.name)
        self._tools[tool.name] = tool
        logger.info(
            "注册工具: %s (category=%s, level=%d)",
            tool.name,
            tool.category.value,
            category_level(tool.category),
        )

    def get(self, name: str) -> BaseTool:
        """获取已注册工具。"""
        if name not in self._tools:
            raise ToolNotFoundError(f"工具 '{name}' 未注册")
        return self._tools[name]

    def list_tools(self) -> list[str]:
        """列出所有已注册工具名。"""
        return list(self._tools.keys())

    def list_by_category(self, category: ToolCategory) -> list[str]:
        """P1 扩容：按权限分级筛选工具。

        Args:
            category: 工具分级。

        Returns:
            该分级下所有工具名列表。
        """
        return [name for name, t in self._tools.items() if t.category == category]

    def list_for_agent(
        self, agent_id: str, guard: HasAgentPermissions
    ) -> list[BaseTool]:
        """P0 修复：返回 agent 有权调用的工具子集。

        融合项目15 openclaw/skills 分层技能权限：根据 SecurityGuard.agent_permissions
        过滤出该 agent 有权限的工具。若权限表为空（未配置任何 agent），返回全部工具
        （兼容 SecurityGuard.check_permission 的"空表放行"语义）。

        Args:
            agent_id: 员工 ID。
            guard: SecurityGuard 实例，提供 agent_permissions 映射。

        Returns:
            该 agent 有权调用的 BaseTool 列表。
        """
        perms = guard.agent_permissions
        # 权限表为空 → 放行全部（与 check_permission 空表语义一致）
        if not perms:
            return list(self._tools.values())
        allowed = perms.get(agent_id, set())
        return [t for name, t in self._tools.items() if name in allowed]

    def category_stats(self) -> dict[ToolCategory, int]:
        """P1 扩容：各权限分级工具数量统计。"""
        stats: dict[ToolCategory, int] = {}
        for t in self._tools.values():
            stats[t.category] = stats.get(t.category, 0) + 1
        return stats

    def discover(
        self, auto_scan: bool = True, scan_dirs: list[str] | None = None
    ) -> list[str]:
        """扫描目录发现新工具并自动注册。

        Args:
            auto_scan: 是否自动扫描默认路径。
            scan_dirs: 自定义扫描目录列表。

        Returns:
            新注册的工具名列表。
        """
        discovered: list[str] = []
        if scan_dirs is None:
            scan_dirs = ["tools", "plugins/tools"]
        for d in scan_dirs:
            if not os.path.isdir(d):
                continue
            for fname in os.listdir(d):
                if not fname.endswith(".py") or fname.startswith("_"):
                    continue
                fpath = os.path.join(d, fname)
                mod_name = f"_discovered_{fname[:-3]}"
                try:
                    spec = importlib.util.spec_from_file_location(mod_name, fpath)
                    if spec is None or spec.loader is None:
                        continue
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[mod_name] = mod
                    spec.loader.exec_module(mod)
                    for attr in dir(mod):
                        obj = getattr(mod, attr)
                        if (
                            isinstance(obj, type)
                            and issubclass(obj, BaseTool)
                            and obj is not BaseTool
                        ):
                            inst = obj()
                            if inst.name not in self._tools:
                                self.register(inst)
                                discovered.append(inst.name)
                except Exception as e:
                    logger.debug("扫描工具 %s 失败: %s", fpath, e)
        return discovered

    _CACHE_TTL = 60

    def cached_lookup(self, name: str) -> BaseTool | None:
        """带 TTL 缓存的工具查找。"""
        now = time.time()
        cache = getattr(self, "_lookup_cache", {})
        cached = cache.get(name)
        if cached and cached[1] > now:
            return cached[0]
        tool = self._tools.get(name)
        if tool:
            if not hasattr(self, "_lookup_cache"):
                self._lookup_cache: dict[str, tuple[BaseTool, float]] = {}
            self._lookup_cache[name] = (tool, now + self._CACHE_TTL)
        return tool

    def get_tool(self, name: str, lazy_load: bool = True) -> BaseTool | None:
        """获取工具，支持懒加载。

        Args:
            name: 工具名。
            lazy_load: 未注册时是否尝试懒加载。

        Returns:
            BaseTool 实例，未找到返回 None。
        """
        tool = self.cached_lookup(name)
        if tool is not None:
            return tool
        if lazy_load:
            discovered = self.discover(auto_scan=True)
            if name in discovered:
                return self.cached_lookup(name)
        return None

    async def call(self, name: str, params: dict[str, Any]) -> Any:
        """调用工具。

        流程：校验参数 → NETWORK_REQUEST+ 前置校验 → 执行（失败重试）→ 熔断判断。

        Args:
            name: 工具名。
            params: 工具参数。

        Returns:
            工具执行结果。

        Raises:
            ToolNotFoundError: 工具未注册。
            ToolValidationError: 参数校验失败。
            ToolExecutionError: 执行失败且重试耗尽。
        """
        tool = self.get(name)

        # 熔断检查
        if self._circuit_breaker.get(name, 0) >= self._circuit_threshold:
            logger.error(
                "工具 %s 已熔断（连续失败 %d 次）", name, self._circuit_threshold
            )
            raise ToolExecutionError(f"工具 '{name}' 已熔断")

        # 参数基础校验
        if not isinstance(params, dict):
            raise ToolValidationError(
                f"参数必须是 dict，实际为 {type(params).__name__}"
            )

        # 能力沙箱校验
        if self._capability_enforcer is not None:
            cap_name = tool.required_capability
            if cap_name is not None:
                try:
                    required_cap = parse_capability(cap_name)
                    self._capability_enforcer.assert_capability(
                        required_cap,
                        detail=f"需要 '{cap_name}' 能力才能调用工具 '{name}'",
                    )
                except ValueError:
                    logger.warning(
                        "工具 %s 的 required_capability='%s' 无法解析，跳过沙箱",
                        name,
                        cap_name,
                    )

        # P1 扩容：NETWORK_REQUEST 及以上分级强制前置安全校验（原仅 HAZARDOUS）
        if needs_security_check(tool.category):
            await self._on_hazardous(name, params)

        # 执行 + 重试
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                result = await tool.execute(params)
                # 成功，重置熔断计数
                self._circuit_breaker[name] = 0
                logger.info("工具 %s 执行成功（第 %d 次尝试）", name, attempt)
                return result
            except Exception as e:
                last_error = e
                logger.warning(
                    "工具 %s 执行失败（第 %d/%d 次）: %s",
                    name,
                    attempt,
                    self._max_retries,
                    e,
                )

        # 重试耗尽
        self._circuit_breaker[name] = self._circuit_breaker.get(name, 0) + 1
        logger.error(
            "工具 %s 重试耗尽，熔断计数=%d",
            name,
            self._circuit_breaker[name],
        )
        raise ToolExecutionError(
            f"工具 '{name}' 执行失败（重试 {self._max_retries} 次）: {last_error}"
        )

    def reset_circuit(self, name: str) -> None:
        """重置工具熔断状态。"""
        self._circuit_breaker.pop(name, None)

    async def _default_hazardous_check(
        self, tool_name: str, params: dict[str, Any]
    ) -> None:
        """高危工具默认安全校验 stub。

        P1 仅记录日志，P5 由戒备猬安全风控模块替换。
        P1 扩容：同时覆盖 NETWORK_REQUEST / SYSTEM_TERMINAL / HAZARDOUS 三级。
        """
        logger.warning(
            "高危工具调用（P1 stub 放行）: tool=%s, params_keys=%s",
            tool_name,
            list(params.keys()),
        )
