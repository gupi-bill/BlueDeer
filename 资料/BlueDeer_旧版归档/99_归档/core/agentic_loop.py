"""BlueDeer 007-AutoGPT：经典 Agentic Loop。

实现 canonical agentic loop 模式：
    1. 接收目标
    2. 模型决定下一步
    3. 解析为结构化动作
    4. 执行动作
    5. 结果反馈到上下文
    6. 循环
    7. 停止条件

融合自 AutoGPT 核心设计：
- 目标驱动的自主任务执行
- 任务分解与动态规划
- 工具调用与结果观察
- 迭代式自我改进
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.base_agent import BaseAgent
from core.event_bus import EventBus
from core.task import Task, TaskResult, TaskStatus, TokenUsage
from core.tracer import Tracer
from models.router import Router
from tools.registry import ToolRegistry

logger = logging.getLogger("bluedeer.autogpt")

__all__ = ["AgenticLoopState", "AutoGPTAgent", "LoopPhase"]


class LoopPhase(Enum):
    """Agentic Loop 阶段。"""

    PLANNING = "planning"
    EXECUTING = "executing"
    REFLECTING = "reflecting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgenticLoopState:
    """Agentic Loop 执行状态。"""

    goal: str = ""
    current_step: int = 0
    max_steps: int = 20
    completed_tasks: list[dict] = field(default_factory=list)
    pending_tasks: list[dict] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    phase: LoopPhase = LoopPhase.PLANNING
    stop_reason: str = ""
    total_tokens_in: int = 0
    total_tokens_out: int = 0


class AutoGPTAgent(BaseAgent):
    """AutoGPT 风格自主 Agent。

    扩展 BaseAgent，实现：
    - 目标驱动的任务分解
    - 自主规划与执行循环
    - 反思与迭代优化
    - 停止条件检测

    使用方式：
        agent = AutoGPTAgent(
            agent_id="autogpt-1",
            role="general",
            event_bus=bus,
            router=router,
            tool_registry=tools,
            context=context,
        )
        result = await agent.run_autonomous(goal="分析项目结构")
    """

    def __init__(
        self,
        agent_id: str,
        role: str,
        event_bus: EventBus,
        router: Router,
        tool_registry: ToolRegistry,
        context: Any,
        tracer: Tracer | None = None,
        max_steps: int = 20,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            agent_id=agent_id,
            role=role,
            event_bus=event_bus,
            router=router,
            tool_registry=tool_registry,
            context=context,
            tracer=tracer,
            **kwargs,
        )
        self._max_steps = max_steps
        self._tool_descriptions = self._build_tool_descriptions()

    def _build_tool_descriptions(self) -> str:
        """构建可用工具描述字符串。"""
        tools = self._tools.list_tools() if hasattr(self._tools, "list_tools") else []
        if not tools:
            return "无可用工具"
        lines = []
        for tool in tools:
            name = tool.get("name", "unknown")
            desc = tool.get("description", "")
            lines.append(f"- {name}: {desc}")
        return "\n".join(lines)

    async def run_autonomous(
        self, goal: str, max_steps: int | None = None
    ) -> TaskResult:
        """执行自主任务循环。

        Args:
            goal: 任务目标描述。
            max_steps: 最大迭代步数，None 则用构造参数。

        Returns:
            TaskResult，包含执行结果。
        """
        max_steps = max_steps or self._max_steps
        state = AgenticLoopState(goal=goal, max_steps=max_steps)
        trace_id = Task().trace_id

        self._trace_span(trace_id, "autonomous_start", goal=goal, max_steps=max_steps)
        logger.info("Agent %s 开始自主任务: %s", self.agent_id, goal)

        try:
            while state.current_step < state.max_steps:
                state.current_step += 1
                self._trace_span(
                    trace_id,
                    "loop_iteration",
                    step=state.current_step,
                    phase=state.phase.value,
                )

                if state.phase == LoopPhase.PLANNING:
                    await self._planning_phase(state)
                elif state.phase == LoopPhase.EXECUTING:
                    await self._execution_phase(state)
                elif state.phase == LoopPhase.REFLECTING:
                    await self._reflection_phase(state)

                if state.phase == LoopPhase.COMPLETED:
                    break
                if state.phase == LoopPhase.FAILED:
                    break

            # 生成最终结果
            output = self._build_final_output(state)
            self._trace_span(
                trace_id,
                "autonomous_complete",
                steps=state.current_step,
                phase=state.phase.value,
                stop_reason=state.stop_reason,
            )

            return TaskResult(
                trace_id=trace_id,
                task_id="",
                status=TaskStatus.SUCCESS,
                output=output,
                token_usage=TokenUsage(
                    tokens_in=state.total_tokens_in,
                    tokens_out=state.total_tokens_out,
                ),
            )

        except Exception as e:
            logger.exception("Agent %s 自主任务失败")
            return TaskResult(
                trace_id=trace_id,
                task_id="",
                status=TaskStatus.FAILED,
                error=str(e),
                token_usage=TokenUsage(
                    tokens_in=state.total_tokens_in,
                    tokens_out=state.total_tokens_out,
                ),
            )

    async def _planning_phase(self, state: AgenticLoopState) -> None:
        """规划阶段：分解目标为子任务。"""
        prompt = self._build_planning_prompt(state)
        response = await self._call_model(prompt, state)
        state.total_tokens_in += response.get("tokens_in", 0)
        state.total_tokens_out += response.get("tokens_out", 0)

        tasks = self._parse_tasks_from_response(response.get("content", ""))
        if not tasks:
            state.stop_reason = "无法分解目标为可执行任务"
            state.phase = LoopPhase.FAILED
            return

        state.pending_tasks = tasks
        state.phase = LoopPhase.EXECUTING
        logger.info(
            "Agent %s 规划完成: %d 个子任务",
            self.agent_id,
            len(tasks),
        )

    async def _execution_phase(self, state: AgenticLoopState) -> None:
        """执行阶段：执行当前子任务（通过 EventBus 下发到自身 topic）。"""
        if not state.pending_tasks:
            state.phase = LoopPhase.REFLECTING
            return

        task = state.pending_tasks.pop(0)
        task_obj = Task(
            id=f"exec-{Task().trace_id}",
            type="execution",
            payload={
                "description": task.get("description", ""),
                "goal": state.goal,
                "observations": state.observations[-5:],
            },
        )
        result = await self._execute_via_bus(task_obj, timeout=60.0)
        state.total_tokens_in += result.token_usage.tokens_in
        state.total_tokens_out += result.token_usage.tokens_out

        content = ""
        if result.output and isinstance(result.output, dict):
            content = result.output.get("model_response", "")
        parsed = self._parse_execution_result(content)
        task["result"] = parsed
        state.completed_tasks.append(task)
        state.observations.append(
            f"[步骤 {state.current_step}] {task['description']}: {parsed}"
        )

        if self._should_stop(state, parsed):
            state.stop_reason = parsed
            state.phase = LoopPhase.COMPLETED
        elif not state.pending_tasks:
            state.phase = LoopPhase.REFLECTING

    async def _reflection_phase(self, state: AgenticLoopState) -> None:
        """反思阶段：评估进展，决定是否继续。"""
        prompt = self._build_reflection_prompt(state)
        response = await self._call_model(prompt, state)
        state.total_tokens_in += response.get("tokens_in", 0)
        state.total_tokens_out += response.get("tokens_out", 0)

        content = response.get("content", "")
        if "继续" in content or "continue" in content.lower():
            state.pending_tasks = self._parse_tasks_from_response(content)
            state.phase = LoopPhase.EXECUTING
        else:
            state.stop_reason = content[:200] if content else "任务完成"
            state.phase = LoopPhase.COMPLETED

    def _should_stop(self, state: AgenticLoopState, result: str) -> bool:
        """判断是否应该停止执行。"""
        if state.current_step >= state.max_steps:
            state.stop_reason = f"达到最大步数限制 ({state.max_steps})"
            return True
        stop_keywords = [
            "完成",
            "完成。",
            "finished",
            "done",
            "completed",
            "终止",
            "终止。",
        ]
        return any(kw in result for kw in stop_keywords)

    async def _call_model(self, prompt: str, state: AgenticLoopState) -> dict[str, Any]:
        """调用模型并返回结果。"""
        full_prompt = self._apply_style(prompt)
        try:
            response = await self._router.complete_with_failover(
                "general",
                full_prompt,
                agent_id=self.agent_id,
            )
            return {
                "content": response.content,
                "tokens_in": response.tokens_in,
                "tokens_out": response.tokens_out,
            }
        except Exception as e:
            logger.exception("模型调用失败: %s")
            return {
                "content": f"[错误] 模型调用失败: {e}",
                "tokens_in": 0,
                "tokens_out": 0,
            }

    def _build_planning_prompt(self, state: AgenticLoopState) -> str:
        """构建规划阶段 prompt。"""
        return (
            f"你是一个自主任务执行 Agent。你的目标是：{state.goal}\n\n"
            f"可用工具：\n{self._tool_descriptions}\n\n"
            "请将目标分解为 3-5 个可执行的子任务，每个子任务一行，格式：\n"
            "1. 子任务描述\n"
            "2. 子任务描述\n"
            "...\n\n"
            "要求：\n"
            "- 子任务应具体、可执行\n"
            "- 按逻辑顺序排列\n"
            "- 每个子任务不超过 50 字"
        )

    def _build_execution_prompt(
        self, state: AgenticLoopState, task: dict[str, Any]
    ) -> str:
        """构建执行阶段 prompt。"""
        context = "\n".join(state.observations[-5:]) if state.observations else "无"
        return (
            f"你是一个自主任务执行 Agent。\n"
            f"目标：{state.goal}\n\n"
            f"当前子任务：{task['description']}\n\n"
            f"之前的观察：\n{context}\n\n"
            f"可用工具：\n{self._tool_descriptions}\n\n"
            "请执行当前子任务，并返回结果。如果任务完成，请在结果末尾加上【完成】标记。"
        )

    def _build_reflection_prompt(self, state: AgenticLoopState) -> str:
        """构建反思阶段 prompt。"""
        summary = "\n".join(f"- {obs}" for obs in state.observations[-10:])
        return (
            f"你是一个自主任务执行 Agent。\n"
            f"目标：{state.goal}\n\n"
            f"已完成的任务：\n{summary}\n\n"
            "请评估目标是否已完成。如果已完成，请说明完成情况；"
            "如果还需要继续，请生成下一步的子任务。"
        )

    def _build_final_output(self, state: AgenticLoopState) -> dict[str, Any]:
        """构建最终输出。"""
        return {
            "goal": state.goal,
            "status": state.phase.value,
            "stop_reason": state.stop_reason,
            "steps_executed": state.current_step,
            "completed_tasks": state.completed_tasks,
            "observations": state.observations,
            "total_tokens_in": state.total_tokens_in,
            "total_tokens_out": state.total_tokens_out,
        }

    def _parse_tasks_from_response(self, content: str) -> list[dict[str, Any]]:
        """从模型响应中解析子任务列表。"""
        tasks = []
        lines = content.strip().split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line[0].isdigit() and ". " in line:
                desc = line.split(". ", 1)[1].strip()
                if desc:
                    tasks.append({"description": desc, "result": None})
        return tasks

    def _parse_execution_result(self, content: str) -> str:
        """解析执行结果。"""
        if "【完成】" in content:
            return content.replace("【完成】", "").strip() + " [已完成]"
        return content.strip()[:500]
