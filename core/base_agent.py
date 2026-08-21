"""BlueDeer 基座 Agent：自主任务规划、结果自检、异常自愈。"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from types import TracebackType
from typing import Any, Self

from core.agent_health import get_health_monitor
from core.capability import DEFAULT_ROLE_CAPABILITIES, Capability, CapabilityEnforcer
from core.config import ResponseStyle, get_config
from core.context import ContextManager
from core.event_bus import EventBus
from core.input_validator import get_validator, validate_task_payload
from core.metrics_collector import TaskMetrics, get_metrics_collector
from core.observability import Observability
from core.policy_engine import PolicyEngine
from core.state_store import SQLiteStateStore, StateStore
from core.task import RESULT_TOPIC, Task, TaskResult, TaskStatus, TokenUsage
from core.token_budget import TokenBudget
from core.tracer import Tracer
from models.router import Router
from tools.registry import ToolRegistry

logger = logging.getLogger("bluedeer.agent")


class AgentState(Enum):
    """Agent 生命周期状态。"""

    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class BaseAgent:
    """基座 Agent 抽象。

    所有员工角色（较真松鼠、软耳兔等）将继承此类并覆盖 _build_prompt / _self_check。
    P1 直接使用基座实例（demo-agent）验证链路。

    职责：
    1. 订阅自身 topic，接收 Task
    2. 调 Router.complete_with_failover 模型推理（P0 修复：激活故障切换）
    3. 调 ToolRegistry 执行工具
    4. 自检 hook
    5. 发布 TaskResult 到 harness.result topic

    P0 修复：
    - 模型调用走 complete_with_failover，启用备用模型切换（融合项目43 ponytail 多模型路由）
    - _rebind_topic 统一处理子岗位改 agent_id 时的退订+订阅（融合项目6 AgentScope 定向消息）
    - _try_self_heal 默认做一次重试（融合项目17 autoresearch 自检闭环）
    """

    def __init__(
        self,
        agent_id: str,
        role: str,
        event_bus: EventBus,
        router: Router,
        tool_registry: ToolRegistry,
        context: ContextManager,
        tracer: Tracer | None = None,
        healer: BaseAgent | None = None,
        response_style: str = "default",
        memory_pipeline: Any = None,
        session_store: Any = None,
        guardrail_engine: Any = None,
        token_budget: TokenBudget | None = None,
        policy_engine: PolicyEngine | None = None,
        state_manager: StateStore | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.role = role
        self._bus = event_bus
        self._router = router
        self._tools = tool_registry
        self._context = context
        self._tracer = tracer
        self._healer = healer
        self._task_topic = f"agent.{agent_id}"
        self._response_style = self._resolve_style(response_style)
        self._capability_enforcer: CapabilityEnforcer | None = None
        self._state: AgentState = AgentState.CREATED
        self._msg_handler: Any = None
        self._health = get_health_monitor().register_agent(agent_id)
        self._metrics = get_metrics_collector()
        self._validator = get_validator()
        self._memory = memory_pipeline
        self._memory_manager: Any = None
        self._session_store = session_store
        self._guardrail_engine = guardrail_engine
        self._token_budget = token_budget or TokenBudget()
        self._policy_engine = policy_engine or PolicyEngine(owner=self)
        self._state_manager = state_manager
        if self._bus is not None:
            self._bus.subscribe(self._task_topic, self._on_task)
        self._cleanup_task: Any = None

    # ---- 生命周期 ----

    async def on_start(self) -> None:
        """启动 Agent。"""
        self._state = AgentState.RUNNING
        if isinstance(self._state_manager, SQLiteStateStore):
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Agent %s 已启动", self.agent_id)

    async def on_stop(self) -> None:
        """停止 Agent。"""
        self._state = AgentState.STOPPED
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        logger.info("Agent %s 已停止", self.agent_id)

    async def on_pause(self) -> None:
        """暂停 Agent。"""
        self._state = AgentState.PAUSED
        logger.info("Agent %s 已暂停", self.agent_id)

    async def on_resume(self) -> None:
        """恢复 Agent。"""
        self._state = AgentState.RUNNING
        logger.info("Agent %s 已恢复", self.agent_id)

    # ---- 消息 ----

    async def send_message(self, to: str, body: str) -> None:
        """发送消息给其他 Agent。"""
        await self._bus.publish(f"agent.{to}", {"from": self.agent_id, "body": body})

    def remember(
        self,
        raw_text: str,
        memory_type: Any = None,
        importance: float = 0.5,
    ) -> Any:
        """将经验写入长期记忆（opt-in，不侵入生命周期）。

        优先走 MemoryManager（全局单例），回退到构造时注入的 memory_pipeline。
        """
        from memory_archive.schemas import MemoryType
        mtype = memory_type or MemoryType.EPISODIC
        if self._memory_manager is not None:
            return self._memory_manager.remember(self.agent_id, raw_text, mtype, importance)
        if self._memory is not None:
            return self._memory.remember(self.agent_id, raw_text, mtype, importance)
        return None

    def recall(self, query: str, top_k: int = 5) -> list[Any]:
        """从长期记忆检索相关经验（opt-in）。"""
        if self._memory_manager is not None:
            return self._memory_manager.recall(self.agent_id, query, top_k=top_k)
        if self._memory is not None:
            return self._memory.retrieve(self.agent_id, query, top_k=top_k)
        return []

    def on_message(self, msg: Any) -> None:
        """消息钩子，子类可覆盖处理自定义消息。"""
        if self._msg_handler:
            self._msg_handler(msg)

    def get_status(self) -> AgentState:
        """返回当前生命周期状态。"""
        return self._state

    def enable_capability_sandbox(
        self, extra_capabilities: set[Capability] | None = None
    ) -> CapabilityEnforcer:
        """启用能力沙箱。

        按角色名从 DEFAULT_ROLE_CAPABILITIES 加载默认能力，
        与 extra_capabilities 合并后创建 CapabilityEnforcer，
        同时注入到关联的 ToolRegistry。

        Args:
            extra_capabilities: 额外授予的能力。

        Returns:
            创建的 CapabilityEnforcer 实例。
        """
        base = DEFAULT_ROLE_CAPABILITIES.get(self.role, set())
        merged = base | (extra_capabilities or set())
        enforcer = CapabilityEnforcer(self.agent_id, merged)
        self._capability_enforcer = enforcer
        return enforcer

    def _inject_enforcer_to_tools(self) -> None:
        """将当前能力执行器注入到 ToolRegistry（如果已启用）。"""
        if self._capability_enforcer is not None and hasattr(
            self._tools, "_capability_enforcer"
        ):
            self._tools._capability_enforcer = self._capability_enforcer

    @staticmethod
    def _resolve_style(style: str) -> ResponseStyle:
        try:
            return ResponseStyle(style.lower())
        except ValueError:
            logger.warning("未知 response_style=%s，降级为 default", style)
            return ResponseStyle.DEFAULT

    def _rebind_topic(self, new_id: str) -> None:
        """子岗位改 agent_id 时统一退订旧 topic + 订阅新 topic。

        融合项目6 AgentScope 跨 Agent 定向消息：避免子类同时监听父子两个 topic。
        """
        old_topic = self._task_topic
        self._bus.unsubscribe(old_topic, self._on_task)
        self.agent_id = new_id
        self._task_topic = f"agent.{new_id}"
        self._bus.subscribe(self._task_topic, self._on_task)

    def _trace_span(self, trace_id: str, action: str, **fields: Any) -> None:
        if self._tracer:
            self._tracer.span(
                trace_id, component=f"Agent:{self.agent_id}", action=action, **fields
            )

    @property
    def topic(self) -> str:
        """Agent 订阅的 topic。"""
        return self._task_topic

    async def _on_task(self, task: Task) -> None:
        """收到任务时的回调，执行 handle 并发布结果。"""
        if self._state not in (AgentState.RUNNING, AgentState.CREATED):
            logger.warning(
                "Agent %s 状态为 %s，拒绝任务 %s",
                self.agent_id,
                self._state.value,
                task.id,
            )
            result = TaskResult(
                trace_id=task.trace_id,
                task_id=task.id,
                status=TaskStatus.FAILED,
                error=f"Agent 状态不可执行任务: {self._state.value}",
            )
            await self._bus.publish(RESULT_TOPIC, result)
            return
        result = await self.handle(task)
        await self._bus.publish(RESULT_TOPIC, result)

    def _build_style_instruction(self) -> str:
        """返回风格指令段落，在 _build_prompt 之后注入到 prompt 头部。"""
        instructions = {
            ResponseStyle.DEFAULT: "",
            ResponseStyle.FORMAL: (
                "请使用正式、专业的风格回复。\n"
                "要求：用词严谨、结构清晰、避免口语化表达、适当使用敬语。"
            ),
            ResponseStyle.CASUAL: (
                "请使用轻松、友好的风格回复。\n"
                "要求：语气亲切、可以用适当的网络用语、像朋友聊天一样自然。"
            ),
            ResponseStyle.TECHNICAL: (
                "请使用技术文档风格的回复。\n"
                "要求：精确使用专业术语、提供技术原理说明、"
                "必要时给出代码示例或架构图解说明。"
            ),
            ResponseStyle.CREATIVE: (
                "请使用富有创意和想象力的风格回复。\n"
                "要求：用生动的比喻和形象的语言、"
                "可以适度使用拟人化和森林主题的趣味表达。"
            ),
        }
        return instructions.get(self._response_style, "")

    def _apply_style(self, prompt: str) -> str:
        """将风格指令包裹到 prompt 头部。"""
        style_instr = self._build_style_instruction()
        if not style_instr:
            return prompt
        return f"[风格指令]\n{style_instr}\n\n" + prompt

    async def _handle_build_prompt_and_infer(
        self, task: Task
    ) -> tuple[str, Any, TokenUsage]:
        prompt = self._apply_style(self._build_prompt(task))
        self._trace_span(task.trace_id, "prompt_built", prompt_len=len(prompt))
        model_response = await self._router.complete_with_failover(
            task.type,
            prompt,
            agent_id=self.agent_id,
        )
        model_name = (
            model_response.model_name
            if hasattr(model_response, "model_name")
            else "unknown"
        )
        total_tokens = TokenUsage()
        total_tokens.tokens_in += model_response.tokens_in
        total_tokens.tokens_out += model_response.tokens_out
        self._trace_span(
            task.trace_id,
            "model_complete",
            model=model_name,
            tokens_in=model_response.tokens_in,
            tokens_out=model_response.tokens_out,
        )
        return prompt, model_response, total_tokens

    async def _handle_tool_call(self, task: Task, model_response: Any) -> Any:
        tool_name = task.payload.get("tool")
        if not tool_name:
            return None
        tool_params = task.payload.get("tool_params", {})
        try:
            tool_output = await asyncio.wait_for(
                self._tools.call(tool_name, tool_params),
                timeout=get_config().task.default_wait_timeout,
            )
        except asyncio.TimeoutError:
            logger.exception(
                "Agent %s 工具调用超时: tool=%s, task=%s",
                self.agent_id,
                tool_name,
                task.id,
            )
            raise
        self._trace_span(task.trace_id, "tool_called", tool=tool_name)
        return tool_output

    def _handle_build_success_result(
        self,
        task: Task,
        model_response: Any,
        tool_output: Any,
        total_tokens: TokenUsage,
    ) -> TaskResult:
        model_name = (
            model_response.model_name
            if hasattr(model_response, "model_name")
            else "unknown"
        )
        output = {
            "model_response": model_response.content,
            "tool_output": tool_output,
            "model_used": model_name,
        }
        self._self_check(task, output)
        self._trace_span(task.trace_id, "handle_success", task_id=task.id)
        return TaskResult(
            trace_id=task.trace_id,
            task_id=task.id,
            status=TaskStatus.SUCCESS,
            output=output,
            token_usage=total_tokens,
        )

    async def _handle_build_failure_result(
        self, task: Task, e: Exception, total_tokens: TokenUsage
    ) -> TaskResult:
        logger.exception("Agent %s 处理任务 %s 失败", self.agent_id, task.id)
        healed = await self._try_self_heal(task, e)
        if healed is not None:
            return healed
        if self._tracer:
            self._tracer.error(
                task.trace_id,
                component=f"Agent:{self.agent_id}",
                action="handle_failed",
                error=str(e),
                task_id=task.id,
            )
        return TaskResult(
            trace_id=task.trace_id,
            task_id=task.id,
            status=TaskStatus.FAILED,
            error=str(e),
            token_usage=total_tokens,
        )

    async def handle(self, task: Task) -> TaskResult:
        """处理任务。

        流程: 构建 prompt -> 模型推理 -> 工具调用 -> 自检 -> 返回结果。
        异常包装为 TaskResult(FAILED)。
        集成: 输入护栏 -> 策略引擎 -> 会话持久化 -> Token 预算记录。
        """
        with Observability.span(
            "agent.run",
            agent_id=self.agent_id,
            task_id=task.id,
            task_type=task.type,
        ):
            return await self._handle_task(task)

    def _build_prompt(self, task: Task) -> str:
        """构建提示词。子类可覆盖以实现岗位专属逻辑。"""
        ctx = self._context.get_context(self.agent_id, task)
        ctx_str = ", ".join(f"{k}={v}" for k, v in ctx.items()) if ctx else "无"
        memory_snippet = ""
        if self._memory is not None:
            try:
                recs = self._memory.retrieve(self.agent_id, task.payload.get("query", ""), top_k=2)
                if recs:
                    memory_snippet = " 相关记忆: " + "; ".join(r.entry.content[:60] for r in recs)
            except Exception as e:
                logger.debug("BaseAgent %s 记忆检索失败: %s", self.agent_id, e)
        return (
            f"[角色:{self.role}] [Agent:{self.agent_id}] "
            f"任务类型:{task.type} 上下文:{ctx_str} "
            f"负载:{task.payload}{memory_snippet}"
        )

    def _self_check(self, task: Task, output: dict[str, Any]) -> None:
        """自检 hook。P1 简单校验输出非空。子类可覆盖。

        Raises:
            ValueError: 自检不通过时抛出。
        """
        if output is None:
            raise ValueError("自检失败：输出为空")

    async def _try_self_heal(self, task: Task, error: Exception) -> TaskResult | None:
        """异常自愈 hook（P0 修复：接入 healer 做一次重试）。

        融合项目17 autoresearch 自检闭环 + 项目8 DeerFlow 故障熔断。
        模型调用的多候选重试已由 router.complete_with_failover 内部处理，
        这里仅做一次完整 handle 重试（含工具调用）。无 healer 时返回 None。
        """
        if self._healer is None:
            return None
        try:
            logger.info("Agent %s 触发自愈重试（原始错误: %s）", self.agent_id, error)
            # 重试一次完整 handle，但禁用自愈避免无限递归
            original_healer = self._healer
            self._healer = None
            try:
                return await self.handle(task)
            finally:
                self._healer = original_healer
        except Exception as heal_err:
            logger.warning(
                "Agent %s 自愈失败: %s（原始错误: %s）",
                self.agent_id,
                heal_err,
                error,
            )
            return None

    async def _execute_via_bus(self, task: Task, timeout: float = 30.0) -> TaskResult:
        """通过 EventBus 执行任务并等待结果（request-reply 模式）。

        用于 007 Agent 内部循环将子任务下发到自身 topic，
        复用 BaseAgent._on_task -> handle -> RESULT_TOPIC 链路。
        集成：自动记录 token 用量到预算系统。
        """
        async with self.with_budget_check(task):
            return await self._bus.request(
                task,
                self._task_topic,
                RESULT_TOPIC,
                timeout=timeout,
            )

    def with_budget_check(self, task: Task) -> _BudgetCheckContext:
        """Token 预算检查上下文管理器。

        在任务执行前后自动检查预算并记录用量。
        """
        return _BudgetCheckContext(self, task)

    async def _cleanup_loop(self) -> None:
        """状态存储清理循环（仅 SQLiteStateStore）。

        每小时执行一次 cleanup，防止状态库无限膨胀。
        """
        if not isinstance(self._state_manager, SQLiteStateStore):
            return
        try:
            while self._state == AgentState.RUNNING:
                await asyncio.sleep(3600)
                if self._state != AgentState.RUNNING:
                    break
                try:
                    deleted = await self._state_manager.cleanup(older_than=7 * 24 * 3600)
                    if deleted:
                        logger.info(
                            "Agent %s 状态清理: 删除 %d 条过期记录",
                            self.agent_id,
                            deleted,
                        )
                except Exception as e:
                    logger.warning("Agent %s 状态清理失败: %s", self.agent_id, e)
        except asyncio.CancelledError:
            pass

    async def _handle_task(self, task: Task) -> TaskResult:
        """实际任务处理逻辑（被 handle 包装 OTel span 后调用）。"""
        self._trace_span(
            task.trace_id, "handle_start", task_id=task.id, task_type=task.type
        )
        self._health.update_heartbeat()
        total_tokens = TokenUsage()
        start_time = time.monotonic()
        try:
            validate_task_payload(task.payload, self.agent_id)
            if self._guardrail_engine is not None:
                try:
                    await self._guardrail_engine.check_input(self.agent_id, task.payload)
                except Exception as e:
                    return TaskResult(
                        trace_id=task.trace_id,
                        task_id=task.id,
                        status=TaskStatus.FAILED,
                        error=str(e),
                        token_usage=total_tokens,
                    )
            if self._token_budget is not None:
                allowed, reason = self._token_budget.check_budget(self.agent_id)
                if not allowed:
                    return TaskResult(
                        trace_id=task.trace_id,
                        task_id=task.id,
                        status=TaskStatus.FAILED,
                        error=f"预算不足: {reason}",
                        token_usage=total_tokens,
                    )
            if self._policy_engine is not None:
                tool_name = task.payload.get("tool")
                if tool_name:
                    decision = self._policy_engine.check_tool_access(
                        self.agent_id, tool_name
                    )
                    if not decision.allowed:
                        return TaskResult(
                            trace_id=task.trace_id,
                            task_id=task.id,
                            status=TaskStatus.FAILED,
                            error=decision.reason,
                            token_usage=total_tokens,
                        )
            _, model_response, total_tokens = await self._handle_build_prompt_and_infer(
                task
            )
            tool_output = await self._handle_tool_call(task, model_response)
            result = self._handle_build_success_result(
                task, model_response, tool_output, total_tokens
            )
            if self._guardrail_engine is not None:
                try:
                    await self._guardrail_engine.check_output(
                        self.agent_id, result.output or {}
                    )
                except Exception as e:
                    result = TaskResult(
                        trace_id=task.trace_id,
                        task_id=task.id,
                        status=TaskStatus.FAILED,
                        error=str(e),
                        token_usage=total_tokens,
                    )
        except Exception as e:
            result = await self._handle_build_failure_result(task, e, total_tokens)
        duration_ms = (time.monotonic() - start_time) * 1000
        self._metrics.record_task(
            TaskMetrics(
                task_type=task.type,
                agent_id=self.agent_id,
                status="success" if result.status == TaskStatus.SUCCESS else "failed",
                duration_ms=duration_ms,
                tokens_in=total_tokens.tokens_in,
                tokens_out=total_tokens.tokens_out,
            )
        )
        if self._token_budget is not None:
            try:
                self._token_budget.record(
                    self.agent_id,
                    task.id,
                    tokens_in=total_tokens.tokens_in,
                    tokens_out=total_tokens.tokens_out,
                )
            except Exception as e:
                logger.debug("BaseAgent %s token记录失败: %s", self.agent_id, e)
        if self._session_store is not None and result.status == TaskStatus.SUCCESS:
            try:
                await self._session_store.append_message(
                    task.id,
                    "assistant",
                    result.output,
                )
            except Exception as e:
                logger.debug("BaseAgent %s session存储失败: %s", self.agent_id, e)
        if self._state_manager is not None and result.status == TaskStatus.SUCCESS:
            try:
                await self._state_manager.save(
                    f"agent:{self.agent_id}:task:{task.id}",
                    {
                        "status": result.status.value,
                        "tokens_in": total_tokens.tokens_in,
                        "tokens_out": total_tokens.tokens_out,
                        "duration_ms": duration_ms,
                    },
                )
            except Exception as e:
                logger.debug("BaseAgent %s 状态存储失败: %s", self.agent_id, e)
        if result.status == TaskStatus.SUCCESS:
            try:
                self.remember(
                    f"task:{task.id}:{task.type}:{result.output}",
                    importance=0.3,
                )
            except Exception as e:
                logger.debug("BaseAgent %s 记忆落盘失败: %s", self.agent_id, e)
        return result


class _BudgetCheckContext:
    """with_budget_check 的内部上下文。"""

    def __init__(self, agent: BaseAgent, task: Task) -> None:
        self._agent = agent
        self._task = task

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None) -> None:
        return None
