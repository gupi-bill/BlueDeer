"""BabyAGI-style minimal 3-agent loop.

三阶段循环：
    1. Execution Agent  执行当前任务
    2. Task Creation Agent 基于目标与结果生成后续任务
    3. Prioritization Agent 对任务队列重新排序

融合自 BabyAGI 核心设计：
- 目标驱动的任务自生成
- 向量记忆持久化（复用现有记忆/上下文能力）
- 动态任务队列
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import logging
from dataclasses import dataclass, field

from core.base_agent import BaseAgent
from core.task import Task, TaskResult
from vector_db.persistence import load_from_disk, save_to_disk
from vector_db.vector_store import VectorStore

logger = logging.getLogger("bluedeer.babyagi")

__all__ = ["BabyAGILoopAgent", "BabyAGIState"]


@dataclass
class BabyAGIState:
    objective: str = ""
    completed: list[TaskResult] = field(default_factory=list)
    pending: list[dict] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 10
    done: bool = False
    stop_reason: str = ""


class BabyAGILoopAgent(BaseAgent):
    """BabyAGI 三 Agent 循环。

    使用方式：
        agent = BabyAGILoopAgent(
            agent_id="babyagi-1",
            role="general",
            event_bus=bus,
            router=router,
            tool_registry=tools,
            context=context,
        )
        state = await agent.run(objective="分析项目结构")
    """

    def __init__(
        self,
        agent_id: str,
        role: str,
        event_bus,
        router,
        tool_registry,
        context,
        max_iterations: int = 10,
        memory_path: str | None = None,
        **kwargs,
    ):
        super().__init__(
            agent_id, role, event_bus, router, tool_registry, context, **kwargs
        )
        self.max_iterations = max_iterations
        self.memory_path = memory_path
        self._memory_store = (
            load_from_disk(memory_path) if memory_path else VectorStore()
        )
        self._memory_seq = 0

    async def run(self, objective: str) -> BabyAGIState:
        state = BabyAGIState(objective=objective, max_iterations=self.max_iterations)
        state.pending = await self._create_tasks(
            objective, state.completed, state.pending
        )
        while state.pending and not state.done:
            task = state.pending.pop(0)
            result = await self._execute_task(state, task)
            state.completed.append(result)
            self._remember(task.get("description", ""), result)
            state.iteration += 1
            if state.iteration >= self.max_iterations:
                state.done = True
                state.stop_reason = "max_iterations"
                break
            state.pending = await self._create_tasks(
                objective, state.completed, state.pending
            )
            state.pending = await self._prioritize(objective, state.pending)
        if self.memory_path:
            try:
                save_to_disk(self._memory_store, self.memory_path)
            except Exception as exc:
                logger.warning("记忆落盘失败: %s", exc)
        if not state.stop_reason:
            state.stop_reason = "objective_achieved" if state.done else "queue_empty"
        return state

    def _remember(self, description: str, result: TaskResult) -> None:
        """将任务结果写入向量记忆。"""
        text = f"任务：{description}\n结果：{result.output}"
        self._memory_store.insert(
            f"{self.agent_id}-mem-{self._memory_seq}",
            text,
            metadata={"agent_id": self.agent_id, "objective": ""},
        )
        self._memory_seq += 1

    def _recall(self, query: str, top_k: int = 3) -> list[str]:
        """从向量记忆检索相关结果。"""
        if self._memory_store.size == 0 or not query:
            return []
        return [r.text for r in self._memory_store.search(query, top_k=top_k)]

    @property
    def memory_store(self) -> VectorStore:
        return self._memory_store

    async def _execute_task(self, state: BabyAGIState, task: dict) -> TaskResult:
        task_obj = Task(
            id=task.get("id", f"baby-{Task().trace_id}"),
            type="execution",
            payload={
                "description": task.get("description", ""),
                "objective": state.objective,
                "completed_count": len(state.completed),
            },
        )
        return await self._execute_via_bus(task_obj, timeout=60.0)

    async def _create_tasks(
        self, objective: str, completed: list[TaskResult], pending: list[dict]
    ) -> list[dict]:
        memory_hits = self._recall(objective, top_k=3)
        memory_block = ""
        if memory_hits:
            memory_block = (
                "相关历史记忆：\n" + "\n".join(f"- {m}" for m in memory_hits) + "\n"
            )
        prompt = (
            f"目标：{objective}\n"
            f"已完成：{len(completed)} 个任务\n"
            f"待执行：{len(pending)} 个任务\n"
            f"{memory_block}"
            "请生成 1-3 个下一步任务（JSON 数组，每项包含 description/type）。"
        )
        try:
            resp = await self._router.complete_with_failover(
                "planning", prompt, agent_id=self.agent_id
            )
            return self._parse_tasks(resp.content)
        except Exception as exc:
            logger.warning("任务创建失败: %s", exc)
            return []

    async def _prioritize(self, objective: str, pending: list[dict]) -> list[dict]:
        if not pending:
            return []
        prompt = (
            f"目标：{objective}\n"
            f"待执行任务：\n"
            + "\n".join(f"- {t.get('description', '')}" for t in pending)
            + "\n\n请按优先级重新排序（返回 JSON 数组，顺序即优先级）。"
        )
        try:
            resp = await self._router.complete_with_failover(
                "prioritization", prompt, agent_id=self.agent_id
            )
            tasks = self._parse_tasks(resp.content)
            return tasks or pending
        except Exception:
            return pending

    def _parse_tasks(self, content: str) -> list[dict]:
        try:
            import json

            data = json.loads(content)
            if isinstance(data, list):
                return [
                    {
                        "id": f"t{i}",
                        "description": item.get("description", ""),
                        "type": item.get("type", "auto"),
                    }
                    for i, item in enumerate(data)
                ]
        except Exception:
            logger.exception("Exception in block")
        return []
