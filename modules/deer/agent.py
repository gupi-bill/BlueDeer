"""鹿（deer）Agent：协调总监专职员工。

负责任务编排、共识投票、事件广播与流水线规划，把森林里的活儿
拆成可执行的计划并分派出去。
"""

from __future__ import annotations

import logging

from core.base_agent import BaseAgent
from core.context import ContextManager
from core.event_bus import EventBus
from core.rag import RagCapable, RAGSystem
from core.task import Task, TaskResult, TaskStatus, TokenUsage
from core.tracer import Tracer
from models.router import Router
from modules.deer.skills import (
    ConsensusVoteSkill,
    EventBusPublishSkill,
    PipelinePlanSkill,
    TaskOrchestrateSkill,
    build_skills,
)
from tools.registry import ToolRegistry

logger = logging.getLogger("bluedeer.deer")


class DeerAgent(BaseAgent, RagCapable):
    """鹿：协调总监，专精任务编排 / 共识投票 / 事件发布 / 流水线规划。"""

    def __init__(
        self,
        event_bus: EventBus,
        router: Router,
        tool_registry: ToolRegistry,
        context: ContextManager,
        tracer: Tracer | None = None,
        rag: RAGSystem | None = None,
        response_style: str = "default",
    ) -> None:
        super().__init__(
            agent_id="deer",
            role="协调总监",
            event_bus=event_bus,
            router=router,
            tool_registry=tool_registry,
            context=context,
            tracer=tracer,
            response_style=response_style,
        )
        self.bind_rag(rag)
        skills = build_skills(tool_registry)
        self._orchestrate_skill: TaskOrchestrateSkill = skills["task_orchestrate"]
        self._vote_skill: ConsensusVoteSkill = skills["consensus_vote"]
        self._publish_skill: EventBusPublishSkill = skills["event_bus_publish"]
        self._plan_skill: PipelinePlanSkill = skills["pipeline_plan"]

    async def handle(self, task: Task) -> TaskResult:
        """处理协调类任务：编排 / 投票 / 广播 / 规划。"""
        if self._tracer:
            self._tracer.span(
                task.trace_id,
                component="DeerAgent",
                action="handle_start",
                task_id=task.id,
                task_type=task.type,
            )
        total_tokens = TokenUsage()
        try:
            async with self.with_budget_check(task):
                operation = task.payload.get("operation", "orchestrate")
                if not operation:
                    raise ValueError("缺 operation 参数")

                prompt = self._apply_style(self._build_prompt(task))
                model_client = self._router.route(task.type)
                model_response = await model_client.complete(prompt)
                total_tokens.tokens_in += model_response.tokens_in
                total_tokens.tokens_out += model_response.tokens_out

                if operation == "orchestrate":
                    output = await self._orchestrate_skill.orchestrate(
                        task.payload.get("goal", ""),
                        task.payload.get("subtasks", []),
                    )
                elif operation == "vote":
                    output = await self._vote_skill.vote(
                        task.payload.get("topic", ""),
                        task.payload.get("options", []),
                    )
                elif operation == "publish":
                    output = await self._publish_skill.publish(
                        task.payload.get("event_type", ""),
                        task.payload.get("data", {}),
                    )
                elif operation == "plan":
                    output = await self._plan_skill.plan(task.payload.get("stages", []))
                else:
                    raise ValueError(f"未知操作: {operation}")

                self._self_check(task, output)
                return TaskResult(
                    trace_id=task.trace_id,
                    task_id=task.id,
                    status=TaskStatus.SUCCESS,
                    output=output,
                    token_usage=total_tokens,
                )
        except Exception as e:
            logger.exception("DeerAgent 处理任务失败")
            healed = await self._try_self_heal(task, e)
            if healed is not None:
                return healed
            if self._tracer:
                self._tracer.error(
                    task.trace_id,
                    component="DeerAgent",
                    action="handle_failed",
                    error=str(e),
                    task_id=task.id,
                )
            return TaskResult(
                trace_id=task.trace_id,
                task_id=task.id,
                status=TaskStatus.FAILED,
                output={"error": str(e)},
                error=str(e),
                token_usage=total_tokens,
            )

    def _build_prompt(self, task: Task) -> str:
        ctx = self._context.get_context(self.agent_id, task)
        ctx_str = ", ".join(f"{k}={v}" for k, v in ctx.items()) if ctx else "无"
        few_shot = self.build_rag_fewshot("协调总监 任务编排 共识投票")
        return (
            f"你是森林公司的协调总监鹿（deer），专精任务编排、共识投票、"
            f"事件广播与流水线规划。\n"
            f"任务详情: {task.payload}\n"
            f"上下文: {ctx_str}\n"
            f"参考经验:\n{few_shot}\n"
            f"请给出本任务的编排/决策意见。"
        )

    def _self_check(self, task: Task, output: dict) -> None:
        if not output:
            raise ValueError("自检失败：输出为空")
        if (
            "fallback" not in output
            and not output.get("subtasks")
            and not output.get("options")
            and not output.get("stages")
        ):
            raise ValueError("自检失败：输出缺少关键字段")
