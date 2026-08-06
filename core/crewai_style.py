"""CrewAI-style multi-agent role collaboration framework.

核心原语：
    - Agent：角色、目标、工具
    - Task：描述、执行 Agent、预期输出
    - Crew：Agent 团队 + 任务编排
    - Flow：事件驱动控制流（EventBus-based state machine）

融合自 CrewAI 设计：
- 角色驱动 Agent
- 自主任务委托
- 顺序/层级流程
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from core.base_agent import BaseAgent
from core.event_bus import EventBus
from core.task import Message, Task, TaskStatus

logger = logging.getLogger("bluedeer.crewai")

__all__ = ["AgentDef", "CrewAIFlow", "CrewDef", "CrewFlowState", "FlowEvent", "TaskDef"]


@dataclass
class AgentDef:
    role: str
    goal: str
    backstory: str = ""
    tools: list[str] = field(default_factory=list)


@dataclass
class TaskDef:
    description: str
    agent_role: str
    expected_output: str = ""


@dataclass
class CrewDef:
    agents: list[AgentDef]
    tasks: list[TaskDef]
    process: str = "sequential"


@dataclass(slots=True)
class CrewFlowState:
    """Crew 流程状态机状态。

    phase 流转：idle -> running -> completed | failed
    """

    phase: str = "idle"
    current_task: int = -1
    total: int = 0
    completed: list[dict] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    error: str | None = None


@dataclass(slots=True, kw_only=True)
class FlowEvent(Message):
    """Crew 流程事件，发布到 `crew.<flow_id>.<event_type>` topic。"""

    flow_id: str
    event_type: str
    task_index: int = -1
    payload: dict = field(default_factory=dict)


class CrewAIFlow:
    """CrewAI 风格多 Agent 编排（EventBus 驱动的状态机）。

    每个子任务的状态流转（started/completed/failed）与流程汇总
    （started/finished）都会发布到事件总线；顺序流程逐个下发，
    `process="parallel"` 时并行执行。
    """

    def __init__(
        self,
        crew: CrewDef,
        agent: BaseAgent | None = None,
        flow_id: str | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self.crew = crew
        self._agent = agent
        self._agent_map: dict[str, AgentDef] = {a.role: a for a in crew.agents}
        self.flow_id = flow_id or f"crew-{Task().trace_id}"
        self._bus = bus
        if self._bus is None and agent is not None:
            self._bus = getattr(agent, "_bus", None)
        self._state = CrewFlowState()

    @property
    def state(self) -> CrewFlowState:
        return self._state

    @property
    def flow_topic(self) -> str:
        return f"crew.{self.flow_id}"

    async def _emit(self, event_type: str, task_index: int = -1, **payload) -> None:
        if self._bus is None:
            return
        try:
            event = FlowEvent(
                flow_id=self.flow_id,
                event_type=event_type,
                task_index=task_index,
                payload=payload,
            )
            await self._bus.publish(f"{self.flow_topic}.{event_type}", event)
        except Exception as exc:
            logger.warning("Crew 事件发布失败（%s）: %s", event_type, exc)

    def run(self) -> list[dict]:
        """同步执行（仅未绑定 agent 时可用）。绑定 agent 时请用 run_async。"""
        if self._agent is not None:
            raise RuntimeError(
                "CrewAIFlow bound to an agent requires async execution: use await flow.run_async()"
            )
        self._state = CrewFlowState(phase="running", total=len(self.crew.tasks))
        results = []
        if self.crew.process == "sequential":
            for i, task in enumerate(self.crew.tasks):
                self._state.current_task = i
                result = self._run_task_sync(task)
                results.append(result)
                if result.get("status") == "completed":
                    self._state.completed.append(result)
                else:
                    self._state.failed.append(result)
        self._state.phase = "completed" if not self._state.failed else "failed"
        return results

    async def run_async(self) -> list[dict]:
        """异步执行：EventBus 驱动状态机。

        顺序流程逐个经 `_execute_via_bus` 下发（request-reply）；
        `process="parallel"` 时所有子任务并行执行。每步状态与事件
        （started/task_started/task_completed/task_failed/finished）
        发布到 `crew.<flow_id>.*` topic。
        """
        tasks = self.crew.tasks
        self._state = CrewFlowState(phase="running", total=len(tasks))
        await self._emit("started", total=len(tasks))

        async def _execute(i: int, task: TaskDef) -> dict:
            self._state.current_task = i
            await self._emit("task_started", task_index=i, task=task.description)
            result = await self._run_task(task)
            if result.get("status") == "completed":
                self._state.completed.append(result)
                await self._emit(
                    "task_completed",
                    task_index=i,
                    task=task.description,
                )
            else:
                self._state.failed.append(result)
                await self._emit(
                    "task_failed",
                    task_index=i,
                    task=task.description,
                    error=result.get("error"),
                )
            return result

        if self.crew.process == "parallel":
            results = await asyncio.gather(
                *(_execute(i, t) for i, t in enumerate(tasks))
            )
        else:
            results = []
            for i, task in enumerate(tasks):
                results.append(await _execute(i, task))

        self._state.phase = "completed" if not self._state.failed else "failed"
        await self._emit(
            "finished",
            phase=self._state.phase,
            completed=len(self._state.completed),
            failed=len(self._state.failed),
        )
        return results

    def _run_task_sync(self, task: TaskDef) -> dict:
        """无 agent 的静态执行。"""
        agent_def = self._agent_map.get(task.agent_role)
        if not agent_def:
            return {
                "task": task.description,
                "error": f"unknown agent role: {task.agent_role}",
            }
        return {
            "agent": agent_def.role,
            "task": task.description,
            "expected": task.expected_output,
            "tools": agent_def.tools,
            "status": "completed",
        }

    async def _run_task(self, task: TaskDef) -> dict:
        """异步执行单个子任务（绑定 agent 时经 EventBus 下发）。"""
        agent_def = self._agent_map.get(task.agent_role)
        if not agent_def:
            return {
                "task": task.description,
                "error": f"unknown agent role: {task.agent_role}",
            }
        if self._agent is not None:
            task_obj = Task(
                id=f"crew-{Task().trace_id}",
                type="crew_task",
                payload={
                    "description": task.description,
                    "agent_role": task.agent_role,
                    "expected_output": task.expected_output,
                },
            )
            try:
                result = await self._agent._execute_via_bus(task_obj, timeout=60.0)
                base = {
                    "agent": agent_def.role,
                    "task": task.description,
                    "expected": task.expected_output,
                    "tools": agent_def.tools,
                }
                if result.status in (TaskStatus.FAILED, TaskStatus.CANCELLED):
                    return {
                        **base,
                        "status": "failed",
                        "error": result.error or "task failed",
                    }
                return {
                    **base,
                    "status": "completed",
                    "result": result.output if result.output else {},
                }
            except Exception as exc:
                return {
                    "agent": agent_def.role,
                    "task": task.description,
                    "expected": task.expected_output,
                    "tools": agent_def.tools,
                    "status": "failed",
                    "error": str(exc),
                }
        return self._run_task_sync(task)
