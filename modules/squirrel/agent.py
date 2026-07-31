"""较真松鼠 Agent：全栈代码开发员工。"""

from __future__ import annotations

import logging
from typing import Any

from core.base_agent import BaseAgent
from core.context import ContextManager
from core.event_bus import EventBus
from core.rag import RagCapable, RAGSystem, SCOPE_AGENT
from core.task import Task, TaskResult, TaskStatus, TokenUsage
from core.tracer import Tracer
from models.router import Router
from modules.squirrel.skills import CodeGenSkill, FileWriteSkill, SyntaxCheckSkill
from tools.registry import ToolRegistry

# Token 估算：每字符约 1/4 Token
_TOKEN_ESTIMATE_DIVISOR = 4

logger = logging.getLogger("bluedeer.squirrel")


_TASK_QUEUE: list[Task] = []
_TASK_RESULTS: list[dict[str, Any]] = []


def enqueue_code_task(task: Task) -> None:
    _TASK_QUEUE.append(task)


def dequeue_code_task() -> Task | None:
    if not _TASK_QUEUE:
        return None
    return _TASK_QUEUE.pop(0)


def record_task_result(result: dict[str, Any]) -> None:
    _TASK_RESULTS.append(result)
    if len(_TASK_RESULTS) > 200:
        _TASK_RESULTS.pop(0)


def recent_results(limit: int = 20) -> list[dict[str, Any]]:
    return list(_TASK_RESULTS[-limit:])


class SquirrelAgent(BaseAgent, RagCapable):
    """较真松鼠：全栈代码开发员工。

    继承 BaseAgent，覆盖 _build_prompt 和 _self_check。
    handle 流程：RAG 检索历史方案 → 模型生成代码 → 写入文件 → 语法校验 → 自检 → 返回 → 成功方案写入 RAG。

    P3 新增：
    - _build_prompt：注入 RAG 检索到的历史方案作为 few-shot 示例
    - handle：任务成功后将生成方案写入岗位私有 RAG 库
    """

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
            agent_id="squirrel",
            role="全栈代码开发",
            event_bus=event_bus,
            router=router,
            tool_registry=tool_registry,
            context=context,
            tracer=tracer,
            response_style=response_style,
        )
        self.bind_rag(rag)

    async def handle(self, task: Task) -> TaskResult:
        """较真松鼠专属处理流程：生成→写入→校验→自检。"""
        if self._tracer:
            self._tracer.span(
                task.trace_id,
                component="SquirrelAgent",
                action="handle_start",
                task_id=task.id,
                task_type=task.type,
            )

        total_tokens = TokenUsage()

        try:
            # 1. 构建代码生成 prompt + 注入风格指令
            prompt = self._apply_style(self._build_prompt(task))

            # 2. 调 LLM 生成代码
            model_client = self._router.route(task.type)
            code_gen = CodeGenSkill(model_client)
            generated_code = await code_gen.generate(task, prompt)
            total_tokens.tokens_in += len(prompt) // _TOKEN_ESTIMATE_DIVISOR  # 估算
            total_tokens.tokens_out += len(generated_code) // _TOKEN_ESTIMATE_DIVISOR

            if self._tracer:
                self._tracer.span(
                    task.trace_id,
                    component="SquirrelAgent",
                    action="code_generated",
                    model=model_client.model_name,
                    code_len=len(generated_code),
                )

            # 3. 写入文件
            target_file = task.payload.get("target_file", "output/generated.py")
            file_write = FileWriteSkill(self._tools)
            write_result = await file_write.write(target_file, generated_code)

            if self._tracer:
                self._tracer.span(
                    task.trace_id,
                    component="SquirrelAgent",
                    action="file_written",
                    path=write_result.get("path"),
                    bytes_written=write_result.get("bytes"),
                )

            # 4. 语法校验
            syntax_check = SyntaxCheckSkill(self._tools)
            check_result = await syntax_check.check_file(target_file)

            if self._tracer:
                self._tracer.span(
                    task.trace_id,
                    component="SquirrelAgent",
                    action="syntax_checked",
                    valid=check_result.get("valid"),
                )

            # 5. 组装输出并自检
            output = {
                "generated_code": generated_code,
                "write_result": write_result,
                "syntax_check": check_result,
                "model_used": model_client.model_name,
            }
            self._self_check(task, output)

            # P3: 任务成功后将方案写入岗位私有 RAG 库
            self.rag_ingest(
                id=f"code_{task.id}",
                text=generated_code,
                metadata={
                    "task_type": task.type,
                    "description": task.payload.get("description", ""),
                    "target_file": target_file,
                },
            )
            if self._tracer:
                self._tracer.span(
                    task.trace_id,
                    component="SquirrelAgent",
                    action="rag_ingested",
                    scope=SCOPE_AGENT,
                    sub_id=self.agent_id,
                )

            if self._tracer:
                self._tracer.span(
                    task.trace_id,
                    component="SquirrelAgent",
                    action="handle_success",
                    task_id=task.id,
                )

            return TaskResult(
                trace_id=task.trace_id,
                task_id=task.id,
                status=TaskStatus.SUCCESS,
                output=output,
                token_usage=total_tokens,
            )

        except Exception as e:
            logger.exception("SquirrelAgent 处理任务 %s 失败", task.id)

            healed = await self._try_self_heal(task, e)
            if healed is not None:
                return healed

            if self._tracer:
                self._tracer.error(
                    task.trace_id,
                    component="SquirrelAgent",
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

    def _build_prompt(self, task: Task) -> str:
        """构建代码生成专属提示词，注入 RAG 检索的历史方案。"""
        description = task.payload.get("description", "未指定")
        language = task.payload.get("language", "python")
        target_file = task.payload.get("target_file", "output/generated.py")

        ctx = self._context.get_context(self.agent_id, task)
        ctx_str = ", ".join(f"{k}={v}" for k, v in ctx.items()) if ctx else "无"

        # P3: RAG 检索历史方案作为 few-shot 示例
        few_shot_section = self.build_rag_fewshot(description)

        return (
            f"你是较真松鼠，BlueDeer 森林公司的全栈代码开发员工。\n"
            f"请根据以下需求生成代码：\n\n"
            f"需求描述: {description}\n"
            f"编程语言: {language}\n"
            f"目标文件: {target_file}\n"
            f"项目上下文: {ctx_str}\n"
            f"{few_shot_section}\n"
            f"要求：\n"
            f"1. 只输出纯代码，不要 markdown 代码块标记\n"
            f"2. 代码必须语法正确、可运行\n"
            f"3. 包含必要的注释\n"
            f"4. 遵循 PEP 8 规范"
        )

    def _self_check(self, task: Task, output: dict[str, Any]) -> None:
        """校验生成结果：代码非空、文件写入成功、语法校验通过。"""
        if not output:
            raise ValueError("自检失败：输出为空")

        generated_code = output.get("generated_code")
        if not generated_code or not generated_code.strip():
            raise ValueError("自检失败：生成的代码为空")

        write_result = output.get("write_result")
        if not write_result or write_result.get("bytes", 0) == 0:
            raise ValueError("自检失败：文件写入失败或写入 0 字节")

        check_result = output.get("syntax_check")
        if not check_result or not check_result.get("valid"):
            error = check_result.get("error", "未知错误") if check_result else "无校验结果"
            raise ValueError(f"自检失败：语法校验未通过: {error}")
