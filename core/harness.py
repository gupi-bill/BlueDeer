"""BlueDeer Harness（忧郁鹿总经理）：全局统筹调度器。

008-3 拆分：原 785 行单体拆为三个模块（职责分离）：
- core/task_board.py: TaskBoardMixin —— 任务看板数据/汇总/清理/持久化
- core/task_dispatcher.py: TaskDispatcherMixin —— 任务分发/回执/DAG 级联/结算/并发执行
- core/circuit_breaker.py: CircuitBreakerMixin —— 熔断/重试/负载均衡/Token 超限回调

本文件保留为薄壳，Harness 组合三 mixin，对外 API 完全兼容：
from core.harness import Harness, HarnessResult 不受影响。

P0 修复（融合 50 项目）：
- 任务卡死熔断：超时自动转 FAILED 并触发重分配（项目8 DeerFlow、项目12 RufloLabs、项目47 OpenMAS）
- 负载均衡：least-load 选 assignee（项目12 RufloLabs 负载流光）
- 异常重分配：FAILED 任务可重分配给其他 Agent（项目8 DeerFlow 故障熔断）
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from core.circuit_breaker import CircuitBreakerMixin
from core.event_bus import EventBus
from core.reward import RewardSystem
from core.scene import CEOOffice
from core.task import RESULT_TOPIC
from core.task_board import TaskBoardMixin
from core.task_dispatcher import TaskDispatcherMixin
from core.token_auditor import TokenAuditor
from core.tracer import Tracer

if TYPE_CHECKING:
    from core.context import ContextManager

logger = logging.getLogger("bluedeer.harness")


class Harness(TaskBoardMixin, TaskDispatcherMixin, CircuitBreakerMixin):
    """忧郁鹿总经理 / 全局统筹调度器。

    职责：
    1. submit_task：经事件总线将任务分发到指派 Agent 的 topic。
    2. aggregate：汇总各 TaskResult，返回任务看板状态。
    3. 维护内存任务看板（dict[task_id, TaskResult]）。
    4. P0 修复：任务卡死熔断 + 负载均衡 + 异常重分配。
    """

    def __init__(
        self,
        event_bus: EventBus,
        tracer: Tracer | None = None,
        token_auditor: TokenAuditor | None = None,
        reward_system: RewardSystem | None = None,
        context: ContextManager | None = None,
        scene: CEOOffice | None = None,
    ) -> None:
        self._bus = event_bus
        self._tracer = tracer
        self._token_auditor = token_auditor
        self._reward_system = reward_system
        # P0 修复：ContextManager 引用（用于 Token 超限自动清理任务临时上下文）
        self._context = context
        # P6 审计日志
        from core.audit import get_audit_log

        self._audit = get_audit_log()
        # DAG 任务依赖图（Plan C）
        self._dag: Any = None
        self._webhook: Any = None
        self._task_event_cb: Any = None

        # 初始化 mixin 数据字段
        self._board_init()
        self._breaker_init()

        # P0 修复：Token 超限自动清理任务临时上下文
        if self._token_auditor is not None and self._context is not None:
            self._token_auditor.set_overload_callback(self._on_token_overload)

        # 订阅结果 topic
        self._bus.subscribe(RESULT_TOPIC, self._on_result)

        # 注册总经理办公室场景
        self._scene = scene or CEOOffice()

    @property
    def scene(self) -> CEOOffice:
        """获取总经理办公室场景。"""
        return self._scene

    def set_dag(self, dag: Any) -> None:
        """绑定 DAG 依赖图。"""
        self._dag = dag

    def set_webhook(self, webhook: Any) -> None:
        """绑定 Webhook 调度器（用于 DAG 事件推送）。"""
        self._webhook = webhook

    def set_task_event_cb(self, cb: Any) -> None:
        """绑定任务事件回调（用于 WebSocket 实时推送）。"""
        self._task_event_cb = cb


__all__ = ["Harness", "HarnessResult"]
