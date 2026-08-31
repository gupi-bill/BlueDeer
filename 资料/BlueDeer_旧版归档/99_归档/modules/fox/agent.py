"""狡黠狐狸 Agent：测试质量专职员工。

P7 扩容：测试角色拆分
- FoxAgent（基类）：单元测试员工，agent_id=fox
- SecurityFoxAgent：安全测试员工，agent_id=fox_security
- ArtFoxAgent：美术规范测试员工，agent_id=fox_art
"""

from __future__ import annotations

import logging
from typing import Any

from core.base_agent import BaseAgent
from core.context import ContextManager
from core.event_bus import EventBus
from core.healer import Healer
from core.rag import RagCapable, RAGSystem
from core.task import Task, TaskResult, TaskStatus, TokenUsage
from core.test_runner import TestType
from core.tracer import Tracer
from models.router import Router
from modules.fox.skills import (
    ArtSpecTestSkill,
    HealSkill,
    SecurityTestSkill,
    TestRunSkill,
)
from tools.registry import ToolRegistry

logger = logging.getLogger("bluedeer.fox")


class FoxAgent(BaseAgent, RagCapable):
    """狡黠狐狸：测试质量员工。

    继承 BaseAgent，覆盖 _build_prompt 与 _self_check。
    handle 流程：
    1. 调 TestRunTool 跑测试
    2. 全通过 → SUCCESS
    3. 有失败 → 调 Healer 完整修复闭环
    4. 修复后全通过 → SUCCESS（记录修复历史）
    5. 仍失败 → FAILED（附失败详情）

    P3 扩容：接入岗位私有 RAG，沉淀测试与修复经验。
    P7 扩容：从 payload 读 test_type 选择测试类型，拆分子角色覆盖安全/美术。
    """

    def __init__(
        self,
        event_bus: EventBus,
        router: Router,
        tool_registry: ToolRegistry,
        context: ContextManager,
        healer: Healer | None = None,
        tracer: Tracer | None = None,
        rag: RAGSystem | None = None,
        response_style: str = "default",
    ) -> None:
        super().__init__(
            agent_id="fox",
            role="测试质量",
            event_bus=event_bus,
            router=router,
            tool_registry=tool_registry,
            context=context,
            tracer=tracer,
            response_style=response_style,
        )
        self._healer = healer or Healer()
        self.bind_rag(rag)

    async def handle(self, task: Task) -> TaskResult:
        """狡黠狐狸专属处理流程：跑测试 → 失败则修复 → 验证。"""
        if self._tracer:
            self._tracer.span(
                task.trace_id,
                component="FoxAgent",
                action="handle_start",
                task_id=task.id,
                task_type=task.type,
            )

        total_tokens = TokenUsage()

        try:
            async with self.with_budget_check(task):
                test_path = task.payload.get("test_path")
                target_file = task.payload.get("target_file")
                if not test_path:
                    raise ValueError("fox 任务 payload 必须包含 test_path")

                # P7 扩容：从 payload 读 test_type（默认 UNIT）
                test_type = self._resolve_test_type(task)

                # 1. 构建 prompt + 注入风格指令（用于 LLM 辅助分析，P7 mock 下非关键路径）
                prompt = self._apply_style(self._build_prompt(task))

                # 2. 调 LLM 生成测试分析建议
                model_client = self._router.route(task.type)
                model_response = await model_client.complete(prompt)
                total_tokens.tokens_in += model_response.tokens_in
                total_tokens.tokens_out += model_response.tokens_out

                if self._tracer:
                    self._tracer.span(
                        task.trace_id,
                        component="FoxAgent",
                        action="model_complete",
                        model=model_client.model_name,
                    )

                # 3. 调测试技能跑测试（P7 扩容：按 test_type 选 skill）
                test_skill = self._build_test_skill(test_type)
                run_result = await test_skill.run_tests(str(test_path))

                if self._tracer:
                    self._tracer.span(
                        task.trace_id,
                        component="FoxAgent",
                        action="test_run",
                        passed=run_result.get("passed"),
                        failed_count=run_result.get("failed_count", 0),
                        test_type=test_type.value,
                    )

                # 4. 全通过 → 直接成功
                if run_result.get("passed"):
                    output = {
                        "initial_result": run_result,
                        "heal_result": None,
                        "model_advice": model_response.content,
                        "model_used": model_client.model_name,
                        "test_path": test_path,
                    }
                    self._self_check(task, output)

                    # P3: 测试全通过经验写入岗位 RAG 库
                    self.rag_ingest(
                        id=f"test_pass_{task.id}",
                        text=f"测试通过 {test_path} 通过数 {run_result.get('passed_count', 0)}",
                        metadata={
                            "task_type": task.type,
                            "test_path": str(test_path),
                            "healed": False,
                        },
                    )

                    if self._tracer:
                        self._tracer.span(
                            task.trace_id,
                            component="FoxAgent",
                            action="handle_success",
                            task_id=task.id,
                            healed=False,
                        )

                    return TaskResult(
                        trace_id=task.trace_id,
                        task_id=task.id,
                        status=TaskStatus.SUCCESS,
                        output=output,
                        token_usage=total_tokens,
                    )

                # 5. 有失败 → 触发修复闭环
                heal_skill = HealSkill(self._healer)
                heal_result = await heal_skill.heal(
                    str(test_path),
                    target_file=str(target_file) if target_file else None,
                )

            if self._tracer:
                self._tracer.span(
                    task.trace_id,
                    component="FoxAgent",
                    action="heal_completed",
                    final_passed=heal_result.get("final_passed"),
                    fixes_applied=heal_result.get("fixes_applied", 0),
                )

            # 6. 组装输出 + 自检
            output = {
                "initial_result": run_result,
                "heal_result": heal_result,
                "model_advice": model_response.content,
                "model_used": model_client.model_name,
                "test_path": test_path,
                "target_file": target_file,
            }
            self._self_check(task, output)

            # 7. 修复后是否通过决定最终状态
            final_passed = heal_result.get("final_passed", False)
            status = TaskStatus.SUCCESS if final_passed else TaskStatus.FAILED

            # P3: 修复成功经验写入岗位 RAG 库
            if final_passed:
                self.rag_ingest(
                    id=f"test_heal_{task.id}",
                    text=f"测试修复 {test_path} 修复策略 {heal_result.get('fixes_applied', 0)}",
                    metadata={
                        "task_type": task.type,
                        "test_path": str(test_path),
                        "healed": True,
                        "fixes_applied": heal_result.get("fixes_applied", 0),
                    },
                )

            if self._tracer:
                self._tracer.span(
                    task.trace_id,
                    component="FoxAgent",
                    action="handle_success" if final_passed else "handle_failed",
                    task_id=task.id,
                    healed=final_passed,
                )

            return TaskResult(
                trace_id=task.trace_id,
                task_id=task.id,
                status=status,
                output=output,
                token_usage=total_tokens,
                error=(
                    None
                    if final_passed
                    else (
                        f"测试修复后仍失败: {heal_result.get('failures_count', 0)} 个失败"
                    )
                ),
            )

        except Exception as e:
            logger.exception("FoxAgent 处理任务 %s 失败", task.id)

            healed = await self._try_self_heal(task, e)
            if healed is not None:
                return healed

            if self._tracer:
                self._tracer.error(
                    task.trace_id,
                    component="FoxAgent",
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
        """构建测试分析提示词，注入 RAG 历史测试经验。"""
        test_path = task.payload.get("test_path", "")
        target_file = task.payload.get("target_file", "")

        ctx = self._context.get_context(self.agent_id, task)
        ctx_str = ", ".join(f"{k}={v}" for k, v in ctx.items()) if ctx else "无"

        # P3: RAG 检索历史测试/修复经验
        few_shot = self.build_rag_fewshot(f"测试 {test_path} {target_file}")

        return (
            f"你是狡黠狐狸，BlueDeer 森林公司的测试质量员工。\n"
            f"请分析以下测试任务：\n\n"
            f"测试路径: {test_path}\n"
            f"目标文件: {target_file or '(自动推断)'}\n"
            f"项目上下文: {ctx_str}\n"
            f"{few_shot}\n"
            f"要求：\n"
            f"1. 跑测试并收集失败\n"
            f"2. 分析失败模式\n"
            f"3. 尝试自动修复\n"
            f"4. 重新验证\n"
            f"注意：最终判定以 TestRunTool 实际结果为准"
        )

    # ============== P7 扩容：测试类型解析 + 技能选择 ==============

    def _resolve_test_type(self, task: Task) -> TestType:
        """P7 扩容：从 task.payload 解析 test_type。

        - 默认 UNIT（保持向后兼容）
        - 接受字符串（"unit"/"security"/"art_spec" 等）或 TestType
        - 未知值降级为 UNIT
        """
        raw = task.payload.get("test_type")
        if raw is None:
            return TestType.UNIT
        if isinstance(raw, TestType):
            return raw
        try:
            return TestType(str(raw))
        except ValueError:
            logger.warning("未知 test_type=%s，降级为 UNIT", raw)
            return TestType.UNIT

    def _build_test_skill(self, test_type: TestType):
        """P7 扩容：按 test_type 选择对应测试技能。

        - UNIT / INTEGRATION / COMMIT_LINT → TestRunSkill
        - SECURITY → SecurityTestSkill
        - ART_SPEC → ArtSpecTestSkill
        """
        if test_type == TestType.SECURITY:
            return SecurityTestSkill(self._tools)
        if test_type == TestType.ART_SPEC:
            return ArtSpecTestSkill(self._tools)
        return TestRunSkill(self._tools)

    @property
    def state(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "task_count": getattr(self, "_task_count", 0),
            "error_count": getattr(self, "_error_count", 0),
            "last_status": getattr(self, "_last_status", "idle"),
        }

    def _self_check(self, task: Task, output: dict[str, Any]) -> None:
        """校验测试运行结果完整性。"""
        if not output:
            raise ValueError("自检失败：输出为空")

        initial = output.get("initial_result")
        if not initial:
            raise ValueError("自检失败：缺少初始测试结果")
        if "passed" not in initial:
            raise ValueError("自检失败：测试结果缺少 passed 字段")

        # test_path 不可为空
        if not output.get("test_path"):
            raise ValueError("自检失败：缺少 test_path")

        # 若有 heal_result，需有 final_passed 字段
        heal = output.get("heal_result")
        if heal is not None and "final_passed" not in heal:
            raise ValueError("自检失败：修复结果缺少 final_passed 字段")


# ============== P7 扩容：测试角色拆分子类 ==============


class SecurityFoxAgent(FoxAgent):
    """安全测试员工（P7 扩容）。

    继承 FoxAgent，agent_id=fox_security。
    默认 test_type=SECURITY，专门跑安全扫描测试。
    """

    def __init__(
        self,
        event_bus: EventBus,
        router: Router,
        tool_registry: ToolRegistry,
        context: ContextManager,
        healer: Healer | None = None,
        tracer: Tracer | None = None,
        rag: RAGSystem | None = None,
        response_style: str = "default",
    ) -> None:
        super().__init__(
            event_bus=event_bus,
            router=router,
            tool_registry=tool_registry,
            context=context,
            healer=healer,
            tracer=tracer,
            rag=rag,
            response_style=response_style,
        )
        # 覆盖基座的 agent_id 与 role（退订旧 topic + 订阅新 topic）
        self._rebind_topic("fox_security")
        self.role = "安全测试"

    def _resolve_test_type(self, task: Task) -> TestType:
        """安全测试员工强制使用 SECURITY 类型（payload 不覆盖）。"""
        return TestType.SECURITY

    def _build_prompt(self, task: Task) -> str:
        """安全测试专属提示词。"""
        test_path = task.payload.get("test_path", "")
        ctx = self._context.get_context(self.agent_id, task)
        ctx_str = ", ".join(f"{k}={v}" for k, v in ctx.items()) if ctx else "无"
        few_shot = self.build_rag_fewshot(f"安全测试 {test_path}")
        return (
            f"你是狡黠狐狸（安全测试岗），BlueDeer 森林公司的安全测试员工。\n"
            f"请执行安全扫描测试：\n\n"
            f"测试路径: {test_path}\n"
            f"项目上下文: {ctx_str}\n"
            f"{few_shot}\n"
            f"要求：\n"
            f"1. 跑 security 标记测试，校验 SQL 注入/路径遍历/XSS/密钥泄露等规则\n"
            f"2. 收集失败并分析漏洞模式\n"
            f"3. 触发修复闭环\n"
            f"4. 重新验证"
        )


class ArtFoxAgent(FoxAgent):
    """美术规范测试员工（P7 扩容）。

    继承 FoxAgent，agent_id=fox_art。
    默认 test_type=ART_SPEC，专门校验美术素材规范（精灵尺寸/色板/命名）。
    """

    def __init__(
        self,
        event_bus: EventBus,
        router: Router,
        tool_registry: ToolRegistry,
        context: ContextManager,
        healer: Healer | None = None,
        tracer: Tracer | None = None,
        rag: RAGSystem | None = None,
        response_style: str = "default",
    ) -> None:
        super().__init__(
            event_bus=event_bus,
            router=router,
            tool_registry=tool_registry,
            context=context,
            healer=healer,
            tracer=tracer,
            rag=rag,
            response_style=response_style,
        )
        self._rebind_topic("fox_art")
        self.role = "美术规范测试"

    def _resolve_test_type(self, task: Task) -> TestType:
        """美术规范测试员工强制使用 ART_SPEC 类型。"""
        return TestType.ART_SPEC

    def _build_prompt(self, task: Task) -> str:
        """美术规范测试专属提示词。"""
        test_path = task.payload.get("test_path", "")
        ctx = self._context.get_context(self.agent_id, task)
        ctx_str = ", ".join(f"{k}={v}" for k, v in ctx.items()) if ctx else "无"
        few_shot = self.build_rag_fewshot(f"美术规范测试 {test_path}")
        return (
            f"你是狡黠狐狸（美术规范测试岗），BlueDeer 森林公司的美术测试员工。\n"
            f"请执行美术素材规范校验：\n\n"
            f"测试路径: {test_path}\n"
            f"项目上下文: {ctx_str}\n"
            f"{few_shot}\n"
            f"要求：\n"
            f"1. 跑 art_spec 标记测试，校验精灵尺寸/色板/命名规范\n"
            f"2. 收集失败并定位不合规素材\n"
            f"3. 触发修复闭环\n"
            f"4. 重新验证"
        )
