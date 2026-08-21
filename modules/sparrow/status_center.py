"""灵音雀状态查询中心：聚合全系统 7 大类实时状态数据。

7 大类：
1. 全局任务进度
2. 员工实时状态
3. 底层系统运行（模型路由/Token/RAG/梦境/MCP 工具）
4. 风控 & 自动化流水线
5. 预警提示汇总
6. Git 流水线
7. 模型路由

设计为被动查询模式：由灵音雀 Agent / 巡检播报器按需调用 collect() 拿到完整快照。
所有数据通过注入的各组件引用读取，不主动修改任何状态。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("bluedeer.sparrow.status")


# ============== 状态数据结构 ==============


@dataclass
class TaskProgressSnapshot:
    """全局任务进度快照。"""

    active_pipelines: int = 0  # 激活流水线数
    total_steps: int = 0  # 总步骤
    completed_steps: int = 0  # 已完成步骤
    estimated_remaining_seconds: float = 0.0  # 预估剩余耗时
    root_demand: str = ""  # 任务根需求
    related_agents: list[str] = field(default_factory=list)  # 关联岗位员工
    breakpoint_snapshot: str = ""  # 断点快照位置
    dream_inference_enabled: bool = False  # 是否开启梦境推演
    auto_heal_triggered: bool = False  # 是否触发自动修复
    git_commit_progress: str = ""  # Git 提交进度


@dataclass
class AgentStatusSnapshot:
    """单名员工实时状态。"""

    agent_id: str = ""
    role: str = ""
    status: str = "online"  # online/sleep/dream/broken/offline
    current_task: str = ""  # 当前处理任务
    backlog_count: int = 0  # 积压任务数
    affinity: int = 0  # 好感度
    coins: int = 0  # 金币
    recent_errors: int = 0  # 近期报错次数
    pass_rate: float = 0.0  # 产出通过率


@dataclass
class SystemRuntimeSnapshot:
    """底层系统运行状态。"""

    router_load: dict[str, int] = field(default_factory=dict)  # 模型名 → 负载
    token_rate: dict[str, float] = field(default_factory=dict)  # 模型名 → Token/秒
    context_occupancy: float = 0.0  # 上下文占用比例 0-1
    rag_throughput: float = 0.0  # RAG 读写吞吐量
    dream_stage_progress: dict[str, float] = field(
        default_factory=dict
    )  # 梦境阶段 → 进度 0-1
    mcp_call_frequency: float = 0.0  # MCP 工具调用频次/秒
    hazardous_blocked_count: int = 0  # 高危操作拦截数


@dataclass
class SecurityPipelineSnapshot:
    """风控 & 自动化流水线状态。"""

    scan_log_recent: list[str] = field(default_factory=list)  # 最近安全扫描日志
    blocked_threat_count: int = 0  # 漏洞拦截数
    heal_progress: float = 0.0  # 自动测试自愈进度 0-1
    fix_strategy_records: list[str] = field(default_factory=list)  # 修复策略执行记录
    github_push_progress: str = ""  # GitHub 提交/PR 进度
    deploy_snapshot_status: str = ""  # 部署快照打包状态


@dataclass
class AlertSummary:
    """预警提示汇总。"""

    token_overrun: bool = False  # Token 超限预警
    memory_high: bool = False  # 内存占用过高
    agent_stuck: list[str] = field(default_factory=list)  # 长时间卡死的员工
    nightmare_dream: bool = False  # 噩梦级低质量梦境
    secret_plaintext_risk: bool = False  # 密钥明文风险
    dependency_conflict: bool = False  # 依赖版本冲突
    custom_alerts: list[str] = field(default_factory=list)  # 自定义告警


@dataclass
class GitPipelineSnapshot:
    """Git 流水线状态。"""

    uncommitted_files: int = 0
    last_commit_hash: str = ""
    last_commit_message: str = ""
    branch: str = ""
    remote_synced: bool = False
    pending_pr_count: int = 0


@dataclass
class ModelRouterSnapshot:
    """模型路由状态。"""

    task_types: list[str] = field(default_factory=list)  # 支持的任务类型
    model_assignments: dict[str, str] = field(default_factory=dict)  # 任务类型 → 模型名
    degraded_models: list[str] = field(default_factory=list)  # 降级中的模型
    failure_counts: dict[str, int] = field(default_factory=dict)  # 模型 → 失败次数


@dataclass
class SystemSnapshot:
    """全系统状态快照（7 大类聚合）。"""

    collected_at: float = field(default_factory=time.time)
    task_progress: TaskProgressSnapshot = field(default_factory=TaskProgressSnapshot)
    agents: list[AgentStatusSnapshot] = field(default_factory=list)
    system_runtime: SystemRuntimeSnapshot = field(default_factory=SystemRuntimeSnapshot)
    security: SecurityPipelineSnapshot = field(default_factory=SecurityPipelineSnapshot)
    alerts: AlertSummary = field(default_factory=AlertSummary)
    git: GitPipelineSnapshot = field(default_factory=GitPipelineSnapshot)
    router: ModelRouterSnapshot = field(default_factory=ModelRouterSnapshot)

    def to_dict(self) -> dict[str, Any]:
        """转字典（用于持久化与 UI 渲染）。"""
        return {
            "collected_at": self.collected_at,
            "task_progress": self.__dataclass_to_dict(self.task_progress),
            "agents": [self.__dataclass_to_dict(a) for a in self.agents],
            "system_runtime": self.__dataclass_to_dict(self.system_runtime),
            "security": self.__dataclass_to_dict(self.security),
            "alerts": self.__dataclass_to_dict(self.alerts),
            "git": self.__dataclass_to_dict(self.git),
            "router": self.__dataclass_to_dict(self.router),
        }

    @staticmethod
    def __dataclass_to_dict(obj: Any) -> dict[str, Any]:
        """dataclass 实例转字典。"""
        if hasattr(obj, "__dataclass_fields__"):
            return {k: getattr(obj, k) for k in obj.__dataclass_fields__}
        return {}


# ============== 状态查询中心 ==============


class StatusCenter:
    """状态查询中心：聚合 7 大类系统数据。

    通过注入的各组件引用被动读取，不修改任何状态。
    若某组件未注入，对应数据返回空快照（不抛异常，保证巡检健壮性）。
    """

    def __init__(
        self,
        event_bus: Any | None = None,
        router: Any | None = None,
        tool_registry: Any | None = None,
        context: Any | None = None,
        healer: Any | None = None,
        agents: list[Any] | None = None,
        token_auditor: Any | None = None,
        rag_system: Any | None = None,
        dream_engine: Any | None = None,
        security_guard: Any | None = None,
        report_generator: Any | None = None,
    ) -> None:
        self._bus = event_bus
        self._router = router
        self._tools = tool_registry
        self._context = context
        self._healer = healer
        self._agents = agents or []
        self._token_auditor = token_auditor
        self._rag = rag_system
        self._dream = dream_engine
        self._guard = security_guard
        self._report_gen = report_generator

    # ============== 顶层入口 ==============

    def collect(self) -> SystemSnapshot:
        """采集全系统 7 大类状态快照。"""
        return SystemSnapshot(
            collected_at=time.time(),
            task_progress=self._collect_task_progress(),
            agents=self._collect_agent_statuses(),
            system_runtime=self._collect_system_runtime(),
            security=self._collect_security(),
            alerts=self._collect_alerts(),
            git=self._collect_git(),
            router=self._collect_router(),
        )

    def collect_category(self, category: str) -> Any:
        """按类别采集单类状态。

        Args:
            category: task_progress / agents / system_runtime /
                      security / alerts / git / router

        Returns:
            对应类别的快照对象。
        """
        collectors = {
            "task_progress": self._collect_task_progress,
            "agents": self._collect_agent_statuses,
            "system_runtime": self._collect_system_runtime,
            "security": self._collect_security,
            "alerts": self._collect_alerts,
            "git": self._collect_git,
            "router": self._collect_router,
        }
        collector = collectors.get(category)
        if collector is None:
            raise ValueError(
                f"未知状态类别: {category}，可选: {list(collectors.keys())}"
            )
        return collector()

    def list_categories(self) -> list[str]:
        """列出所有可查询的状态类别（7 个）。"""
        return [
            "task_progress",
            "agents",
            "system_runtime",
            "security",
            "alerts",
            "git",
            "router",
        ]

    # ============== 7 大类采集实现 ==============

    def _collect_task_progress(self) -> TaskProgressSnapshot:
        """1. 全局任务进度。"""
        snap = TaskProgressSnapshot()
        # 从 context 全局层读流水线信息（若存在）
        if self._context:
            snap.active_pipelines = int(
                self._context.get_global("active_pipelines", 0) or 0
            )
            snap.total_steps = int(self._context.get_global("total_steps", 0) or 0)
            snap.completed_steps = int(
                self._context.get_global("completed_steps", 0) or 0
            )
            snap.root_demand = str(self._context.get_global("root_demand", "") or "")
            snap.related_agents = list(
                self._context.get_global("related_agents", []) or []
            )
            snap.dream_inference_enabled = bool(
                self._context.get_global("dream_inference_enabled", False)
            )
            snap.auto_heal_triggered = bool(
                self._context.get_global("auto_heal_triggered", False)
            )
        return snap

    def _collect_agent_statuses(self) -> list[AgentStatusSnapshot]:
        """2. 员工实时状态。"""
        result: list[AgentStatusSnapshot] = []
        for agent in self._agents:
            snap = AgentStatusSnapshot(
                agent_id=getattr(agent, "agent_id", "unknown"),
                role=getattr(agent, "role", ""),
            )
            # 从 context 岗位私有层读员工运行数据
            if self._context:
                snap.status = str(
                    self._context.get_agent(snap.agent_id, "status", "online")
                )
                snap.current_task = str(
                    self._context.get_agent(snap.agent_id, "current_task", "")
                )
                snap.backlog_count = int(
                    self._context.get_agent(snap.agent_id, "backlog_count", 0) or 0
                )
                snap.affinity = int(
                    self._context.get_agent(snap.agent_id, "affinity", 0) or 0
                )
                snap.coins = int(
                    self._context.get_agent(snap.agent_id, "coins", 0) or 0
                )
                snap.recent_errors = int(
                    self._context.get_agent(snap.agent_id, "recent_errors", 0) or 0
                )
                snap.pass_rate = float(
                    self._context.get_agent(snap.agent_id, "pass_rate", 0.0) or 0.0
                )
            result.append(snap)
        return result

    def _collect_system_runtime(self) -> SystemRuntimeSnapshot:
        """3. 底层系统运行状态。"""
        snap = SystemRuntimeSnapshot()
        # 模型路由负载
        if self._router and hasattr(self._router, "list_task_types"):
            for tt in self._router.list_task_types():
                try:
                    client = self._router.route(tt)
                    snap.router_load[client.model_name] = (
                        snap.router_load.get(client.model_name, 0) + 1
                    )
                    snap.token_rate[client.model_name] = 0.0
                except Exception:  # noqa: S112
                    continue
        # 高危拦截数
        if self._guard and hasattr(self._guard, "has_pending_confirm_tokens"):
            snap.hazardous_blocked_count = 0  # 由 SecurityReportGenerator 提供
        # RAG 吞吐
        if self._rag and hasattr(self._rag, "size"):
            try:
                snap.rag_throughput = float(self._rag.size())
            except Exception:
                logger.warning("RAG 吞吐统计异常", exc_info=True)
        return snap

    def _collect_security(self) -> SecurityPipelineSnapshot:
        """4. 风控 & 自动化流水线状态。"""
        snap = SecurityPipelineSnapshot()
        # 月报生成器统计
        if self._report_gen and hasattr(self._report_gen, "stats"):
            try:
                stats = self._report_gen.stats()
                snap.blocked_threat_count = stats.get("blocked_count", 0)
            except Exception:
                logger.warning("安全报告统计异常", exc_info=True)
        # 修复引擎历史
        if self._healer and hasattr(self._healer, "_history"):
            try:
                history = self._healer._history
                snap.heal_progress = min(1.0, len(history) / 10.0) if history else 0.0
                snap.fix_strategy_records = [
                    f"{r.strategy}:{'success' if r.success else 'fail'}"
                    for r in history[-10:]
                ]
            except Exception:
                logger.warning("修复引擎历史统计异常", exc_info=True)
        return snap

    def _collect_alerts(self) -> AlertSummary:
        """5. 预警提示汇总。"""
        snap = AlertSummary()
        if self._context:
            snap.token_overrun = bool(
                self._context.get_global("alert_token_overrun", False)
            )
            snap.memory_high = bool(
                self._context.get_global("alert_memory_high", False)
            )
            snap.nightmare_dream = bool(
                self._context.get_global("alert_nightmare_dream", False)
            )
            snap.secret_plaintext_risk = bool(
                self._context.get_global("alert_secret_plaintext", False)
            )
            snap.dependency_conflict = bool(
                self._context.get_global("alert_dependency_conflict", False)
            )
            stuck_agents = self._context.get_global("alert_agent_stuck", [])
            if isinstance(stuck_agents, list):
                snap.agent_stuck = stuck_agents
        return snap

    def _collect_git(self) -> GitPipelineSnapshot:
        """6. Git 流水线状态。"""
        snap = GitPipelineSnapshot()
        try:
            import subprocess

            result = subprocess.run(  # noqa: PLW1510
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            snap.branch = result.stdout.strip() if result.returncode == 0 else ""
            result = subprocess.run(  # noqa: PLW1510
                ["git", "log", "-1", "--format=%H|%s"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0 and result.stdout:
                parts = result.stdout.strip().split("|", 1)
                snap.last_commit_hash = parts[0][:12]
                snap.last_commit_message = parts[1] if len(parts) > 1 else ""
            result = subprocess.run(  # noqa: PLW1510
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0:
                snap.uncommitted_files = len(
                    [line for line in result.stdout.splitlines() if line.strip()]
                )
        except Exception as e:
            logger.debug("Git 状态采集失败: %s", e)
        return snap

    def _collect_router(self) -> ModelRouterSnapshot:
        """7. 模型路由状态。"""
        snap = ModelRouterSnapshot()
        if self._router:
            if hasattr(self._router, "list_task_types"):
                snap.task_types = list(self._router.list_task_types())
            # 读取降级状态
            for tt in snap.task_types:
                try:
                    client = self._router.route(tt)
                    snap.model_assignments[tt] = client.model_name
                    if hasattr(self._router, "is_degraded") and self._router.is_degraded(client.model_name):
                            snap.degraded_models.append(client.model_name)
                    if hasattr(self._router, "model_failure_count"):
                        count = self._router.model_failure_count(client.model_name)
                        if count > 0:
                            snap.failure_counts[client.model_name] = count
                except Exception:  # noqa: S112
                    continue
        return snap


# ============== 状态聚合与告警回调 ==============


class StatusAggregator:
    """聚合多 agent 状态报告，支持条件告警回调。"""

    def __init__(self) -> None:
        self._snapshots: dict[str, SystemSnapshot] = {}
        self._callbacks: list[tuple[Any, Any]] = []

    def ingest(self, agent_id: str, snapshot: SystemSnapshot) -> None:
        self._snapshots[agent_id] = snapshot
        self._evaluate_callbacks()

    def aggregate_status(self, agents: list[Any]) -> dict[str, Any]:
        """合并所有 agent 的状态报告为汇总。"""
        result: dict[str, Any] = {
            "total": len(agents),
            "online": 0,
            "sleep": 0,
            "error": 0,
            "offline": 0,
            "total_tasks": 0,
            "total_errors": 0,
        }
        for a in agents:
            status = getattr(a, "status", "offline")
            if status in result:
                result[status] += 1
            else:
                result["offline"] += 1
            result["total_tasks"] += getattr(a, "backlog_count", 0)
            result["total_errors"] += getattr(a, "recent_errors", 0)
        return result

    def alert_on_status(self, condition: Any, callback: Any) -> None:
        """注册条件告警：condition(snapshot) → True 时调用 callback(snapshot)。"""
        self._callbacks.append((condition, callback))

    def _evaluate_callbacks(self) -> None:
        for snapshot in self._snapshots.values():
            for condition, callback in self._callbacks:
                try:
                    if condition(snapshot):
                        callback(snapshot)
                except Exception:  # noqa: S112
                    continue

    def clear_callbacks(self) -> None:
        self._callbacks.clear()

    @property
    def known_agents(self) -> list[str]:
        return list(self._snapshots.keys())
