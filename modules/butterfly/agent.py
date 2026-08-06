"""蝴蝶（butterfly）Agent：创意视觉专职员工。

负责提示词扩写、布局设计、风格迁移与像素画创作，为森林产品
产出视觉方案。
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
from modules.butterfly.skills import (
    ImagePromptSkill,
    LayoutSkill,
    PixelCanvasSkill,
    StyleTransferSkill,
    build_skills,
)
from tools.registry import ToolRegistry

logger = logging.getLogger("bluedeer.butterfly")


class ButterflyAgent(BaseAgent, RagCapable):
    """蝴蝶：创意视觉，专精提示词扩写 / 布局设计 / 风格迁移 / 像素画。"""

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
            agent_id="butterfly",
            role="创意视觉",
            event_bus=event_bus,
            router=router,
            tool_registry=tool_registry,
            context=context,
            tracer=tracer,
            response_style=response_style,
        )
        self.bind_rag(rag)
        skills = build_skills(tool_registry)
        self._prompt_skill: ImagePromptSkill = skills["image_prompt_expand"]
        self._layout_skill: LayoutSkill = skills["layout_designer"]
        self._style_skill: StyleTransferSkill = skills["style_transfer"]
        self._pixel_skill: PixelCanvasSkill = skills["pixel_canvas_draw"]

    async def handle(self, task: Task) -> TaskResult:
        """处理创意类任务：扩写 / 布局 / 迁移 / 像素画。"""
        if self._tracer:
            self._tracer.span(
                task.trace_id,
                component="ButterflyAgent",
                action="handle_start",
                task_id=task.id,
                task_type=task.type,
            )
        total_tokens = TokenUsage()
        try:
            operation = task.payload.get("operation", "expand_prompt")
            if not operation:
                raise ValueError("缺 operation 参数")

            prompt = self._apply_style(self._build_prompt(task))
            model_client = self._router.route(task.type)
            model_response = await model_client.complete(prompt)
            total_tokens.tokens_in += model_response.tokens_in
            total_tokens.tokens_out += model_response.tokens_out

            if operation == "expand_prompt":
                output = await self._prompt_skill.expand_prompt(
                    task.payload.get("idea", ""),
                    task.payload.get("style_hint", ""),
                )
            elif operation == "layout":
                output = await self._layout_skill.design_layout(
                    task.payload.get("elements", []),
                    task.payload.get("canvas", "16:9"),
                )
            elif operation == "style_transfer":
                output = await self._style_skill.transfer_style(
                    task.payload.get("source", ""),
                    task.payload.get("target_style", ""),
                )
            elif operation == "pixel":
                output = await self._pixel_skill.draw_pixel(
                    task.payload.get("subject", ""),
                    task.payload.get("palette", []),
                )
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
            logger.exception("ButterflyAgent 处理任务失败: %s", e)
            healed = await self._try_self_heal(task, e)
            if healed is not None:
                return healed
            if self._tracer:
                self._tracer.error(
                    task.trace_id,
                    component="ButterflyAgent",
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
        few_shot = self.build_rag_fewshot("创意视觉 提示词 布局 风格")
        return (
            f"你是森林公司的创意视觉蝴蝶（butterfly），专精提示词扩写、"
            f"布局设计、风格迁移与像素画创作。\n"
            f"任务详情: {task.payload}\n"
            f"上下文: {ctx_str}\n"
            f"参考经验:\n{few_shot}\n"
            f"请给出本任务的创意方案。"
        )

    def _self_check(self, task: Task, output: dict) -> None:
        if not output:
            raise ValueError("自检失败：输出为空")
