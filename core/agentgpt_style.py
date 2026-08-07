"""AgentGPT-style browser-based goal-driven agent.

核心流程：
    - 接收自然语言目标
    - 任务分解
    - 自动执行
    - 结果反馈

融合自 AgentGPT 设计：
- 目标驱动
- 浏览器友好
- 动态任务规划
- 结果回传
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import logging
from dataclasses import dataclass, field

from core.base_agent import BaseAgent
from core.task import Task, TaskResult

logger = logging.getLogger("bluedeer.agentgpt")

__all__ = ["AgentGPTResult", "BrowserGoalAgent"]


@dataclass
class AgentGPTResult:
    goal: str = ""
    tasks: list[dict] = field(default_factory=list)
    results: list[TaskResult] = field(default_factory=list)
    status: str = "pending"
    error: str = ""


class BrowserGoalAgent(BaseAgent):
    """AgentGPT 风格浏览器目标驱动 Agent。"""

    async def run_goal(self, goal: str, max_tasks: int = 5) -> AgentGPTResult:
        result = AgentGPTResult(goal=goal)
        tasks = await self._decompose(goal, max_tasks=max_tasks)
        result.tasks = tasks
        for task in tasks:
            t = Task(id=task.get("id", ""), type=task.get("type", "auto"), payload=task)
            r = await self._execute_via_bus(t, timeout=60.0)
            result.results.append(r)
        result.status = "completed"
        return result

    async def _decompose(self, goal: str, max_tasks: int = 5) -> list[dict]:
        prompt = (
            f"目标：{goal}\n"
            f"请将目标分解为最多 {max_tasks} 个可执行任务，"
            "返回 JSON 数组，每项包含 description/type。"
        )
        try:
            resp = await self._router.complete_with_failover(
                "planning", prompt, agent_id=self.agent_id
            )
            return self._parse_tasks(resp.content)
        except Exception as exc:
            logger.warning("任务分解失败: %s", exc)
            return [{"id": "t0", "description": goal, "type": "auto"}]

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
        return [{"id": "t0", "description": content[:200], "type": "auto"}]
