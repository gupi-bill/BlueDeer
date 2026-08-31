"""OpenDevin-style developer full-stack agent.

核心闭环：
    - 代码规划
    - 代码编写
    - 代码执行
    - 调试

融合自 OpenDevin 设计：
- IDE 集成
- 本地环境交互
- 开发者专属工具集
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from core.base_agent import BaseAgent
from core.task import Task

logger = logging.getLogger("bluedeer.opendevin")

__all__ = ["DevTask", "DeveloperAgent"]


@dataclass
class DevTask:
    step: str
    description: str
    status: str = "pending"
    result: str = ""


class DeveloperAgent(BaseAgent):
    """OpenDevin 风格开发者全栈 Agent。"""

    async def run_dev_loop(self, goal: str, max_steps: int = 10) -> list[DevTask]:
        plan = await self._plan(goal)
        tasks = [
            DevTask(step=f"step-{i + 1}", description=t) for i, t in enumerate(plan)
        ]
        for task in tasks[:max_steps]:
            task.status = "running"
            task_obj = Task(
                id=f"dev-{Task().trace_id}",
                type="coding",
                payload={"description": task.description, "goal": goal},
            )
            r = await self._execute_via_bus(task_obj, timeout=120.0)
            content = (
                r.output.get("model_response", "")
                if r.output and isinstance(r.output, dict)
                else ""
            )
            task.result = content
            task.status = "completed"
            if self._needs_debug(content):
                debug_task = Task(
                    id=f"debug-{Task().trace_id}",
                    type="debugging",
                    payload={"description": task.description, "code": content},
                )
                debug_r = await self._execute_via_bus(debug_task, timeout=120.0)
                task.result = (
                    debug_r.output.get("model_response", "")
                    if debug_r.output and isinstance(debug_r.output, dict)
                    else content
                )
        return tasks

    async def _plan(self, goal: str) -> list[str]:
        prompt = f"开发者目标：{goal}\n请生成代码实现步骤（每行一个步骤）。"
        try:
            resp = await self._router.complete_with_failover(
                "planning", prompt, agent_id=self.agent_id
            )
            return [
                line.strip()
                for line in resp.content.strip().split("\n")
                if line.strip()
            ]
        except Exception:
            return [goal]

    async def _execute_code_task(self, description: str) -> str:
        prompt = f"请为以下任务编写代码：\n{description}\n仅返回代码，不要解释。"
        try:
            resp = await self._router.complete_with_failover(
                "coding", prompt, agent_id=self.agent_id
            )
            return resp.content
        except Exception as exc:
            return f"[错误] {exc}"

    async def _debug(self, description: str, code: str) -> str:
        prompt = f"以下代码可能有问题，请调试：\n任务：{description}\n代码：\n{code}\n返回修复后的代码。"
        try:
            resp = await self._router.complete_with_failover(
                "debugging", prompt, agent_id=self.agent_id
            )
            return resp.content
        except Exception:
            return code

    def _needs_debug(self, result: str) -> bool:
        error_keywords = [
            "error",
            "Error",
            "Traceback",
            "exception",
            "Exception",
            "failed",
            "Failed",
        ]
        return any(kw in result for kw in error_keywords)
