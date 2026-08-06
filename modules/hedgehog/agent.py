"""戒备猬 Agent：安全审计专职员工。

P5 扩容：安全角色拆分
- HedgehogAgent（基类）：通用安全审计员工，agent_id=hedgehog
- StaticScanHedgehogAgent：静态扫描子岗位，agent_id=hedgehog_static
- RuntimeAuditHedgehogAgent：运行时审计子岗位，agent_id=hedgehog_runtime
- KeyManagementHedgehogAgent：密钥管理子岗位，agent_id=hedgehog_keymgmt
"""

from __future__ import annotations

import logging
from typing import Any

from core.base_agent import BaseAgent
from core.context import ContextManager
from core.event_bus import EventBus
from core.rag import RagCapable, RAGSystem
from core.security import SecurityReportGenerator
from core.task import Task, TaskResult, TaskStatus, TokenUsage
from core.tracer import Tracer
from models.router import Router
from modules.hedgehog.skills import SecurityScanSkill
from tools.registry import ToolRegistry

logger = logging.getLogger("bluedeer.hedgehog")


_TASK_QUEUE: list[dict[str, Any]] = []


def enqueue_task(task_data: dict[str, Any]) -> None:
    _TASK_QUEUE.append(task_data)


def dequeue_task() -> dict[str, Any] | None:
    if not _TASK_QUEUE:
        return None
    return _TASK_QUEUE.pop(0)


def queue_size() -> int:
    return len(_TASK_QUEUE)


class HedgehogAgent(BaseAgent, RagCapable):
    """戒备猬：安全审计员工。

    继承 BaseAgent，覆盖 _build_prompt 与 _self_check。
    handle 流程：构建审计 prompt → 调 SecurityScanTool 扫描 → 自检 → 返回 SecurityReport。

    与 SquirrelAgent 不同，戒备猬以工具调用结果为核心，
    LLM 仅用于辅助总结风险（P5 mock 模式下 LLM 输出未参与扫描逻辑）。

    P3 扩容：接入岗位私有 RAG，沉淀安全审计经验。
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
            agent_id="hedgehog",
            role="安全审计",
            event_bus=event_bus,
            router=router,
            tool_registry=tool_registry,
            context=context,
            tracer=tracer,
            response_style=response_style,
        )
        self.bind_rag(rag)

    async def handle(self, task: Task) -> TaskResult:
        """戒备猬专属处理流程：扫描 → 自检 → 返回报告。"""
        if self._tracer:
            self._tracer.span(
                task.trace_id,
                component="HedgehogAgent",
                action="handle_start",
                task_id=task.id,
                task_type=task.type,
            )

        total_tokens = TokenUsage()

        try:
            # 1. 构建 prompt + 注入风格指令（用于 LLM 总结，P5 mock 下非关键路径）
            prompt = self._apply_style(self._build_prompt(task))

            # 2. 调 LLM 生成审计建议（不参与扫描判定，仅作辅助提示）
            model_client = self._router.route(task.type)
            model_response = await model_client.complete(prompt)
            total_tokens.tokens_in += model_response.tokens_in
            total_tokens.tokens_out += model_response.tokens_out

            if self._tracer:
                self._tracer.span(
                    task.trace_id,
                    component="HedgehogAgent",
                    action="model_complete",
                    model=model_client.model_name,
                    tokens_in=model_response.tokens_in,
                    tokens_out=model_response.tokens_out,
                )

            # 3. 调 SecurityScanTool 扫描（核心步骤）
            scan_skill = SecurityScanSkill(self._tools)
            scan_report = await scan_skill.scan_task(task)

            if self._tracer:
                self._tracer.span(
                    task.trace_id,
                    component="HedgehogAgent",
                    action="scan_completed",
                    risk_level=scan_report.get("risk_level"),
                    threat_count=scan_report.get("threat_count", 0),
                    passed=scan_report.get("passed"),
                )

            # 4. 组装输出 + 自检
            output = {
                "scan_report": scan_report,
                "model_advice": model_response.content,
                "model_used": model_client.model_name,
                "target": task.payload.get("code")
                or task.payload.get("path")
                or task.payload.get("text", ""),
            }
            self._self_check(task, output)

            # P3: 成功后将审计经验写入岗位 RAG 库
            _target_str = str(output.get("target", ""))[:200]
            self.rag_ingest(
                id=f"security_{task.id}",
                text=str(scan_report.get("risk_level", "")) + " " + _target_str,
                metadata={
                    "task_type": task.type,
                    "risk_level": scan_report.get("risk_level"),
                    "threat_count": scan_report.get("threat_count", 0),
                },
            )

            if self._tracer:
                self._tracer.span(
                    task.trace_id,
                    component="HedgehogAgent",
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
            logger.exception("HedgehogAgent 处理任务 %s 失败", task.id)

            healed = await self._try_self_heal(task, e)
            if healed is not None:
                return healed

            if self._tracer:
                self._tracer.error(
                    task.trace_id,
                    component="HedgehogAgent",
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
        """构建安全审计提示词，注入 RAG 历史审计经验。"""
        target = (
            task.payload.get("code")
            or task.payload.get("path")
            or task.payload.get("text", "")
        )
        target_preview = str(target)[:200] if target else "(空)"

        ctx = self._context.get_context(self.agent_id, task)
        ctx_str = ", ".join(f"{k}={v}" for k, v in ctx.items()) if ctx else "无"

        # P3: RAG 检索历史审计经验
        few_shot = self.build_rag_fewshot(target_preview or "安全审计")

        return (
            f"你是戒备猬，BlueDeer 森林公司的安全审计员工。\n"
            f"请对以下内容做安全审计风险评估：\n\n"
            f"待审计内容预览:\n{target_preview}\n\n"
            f"项目上下文: {ctx_str}\n"
            f"{few_shot}\n"
            f"要求：\n"
            f"1. 列出可能存在的安全威胁（SQL注入/路径遍历/XSS/密钥泄露）\n"
            f"2. 给出修复建议\n"
            f"3. 注意：此 LLM 输出仅供参考，最终判定以 SecurityScanTool 的扫描报告为准"
        )

    def _self_check(self, task: Task, output: dict[str, Any]) -> None:
        """校验扫描结果完整性。"""
        if not output:
            raise ValueError("自检失败：输出为空")

        scan_report = output.get("scan_report")
        if not scan_report:
            raise ValueError("自检失败：缺少扫描报告")
        if "risk_level" not in scan_report:
            raise ValueError("自检失败：扫描报告缺少 risk_level 字段")
        if "threats" not in scan_report:
            raise ValueError("自检失败：扫描报告缺少 threats 字段")
        if "passed" not in scan_report:
            raise ValueError("自检失败：扫描报告缺少 passed 字段")

        # target 字段不可为空（必须有审计对象）
        if not output.get("target"):
            raise ValueError("自检失败：缺少审计对象 target")


# ============== P5 扩容：安全角色拆分子岗位 ==============


class StaticScanHedgehogAgent(HedgehogAgent):
    """静态扫描子岗位（P5 扩容）。

    继承 HedgehogAgent，agent_id=hedgehog_static。
    专注代码静态扫描：SQL 注入/路径遍历/XSS/密钥泄露/硬编码/不安全 API 等 10 大类。
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
            event_bus=event_bus,
            router=router,
            tool_registry=tool_registry,
            context=context,
            tracer=tracer,
            rag=rag,
            response_style=response_style,
        )
        self._rebind_topic("hedgehog_static")
        self.role = "静态扫描"

    def _build_prompt(self, task: Task) -> str:
        """静态扫描专属提示词。"""
        target = (
            task.payload.get("code")
            or task.payload.get("path")
            or task.payload.get("text", "")
        )
        target_preview = str(target)[:200] if target else "(空)"
        ctx = self._context.get_context(self.agent_id, task)
        ctx_str = ", ".join(f"{k}={v}" for k, v in ctx.items()) if ctx else "无"
        few_shot = self.build_rag_fewshot(f"静态扫描 {target_preview}")
        return (
            f"你是戒备猬（静态扫描岗），BlueDeer 森林公司的静态安全扫描员工。\n"
            f"请执行代码静态扫描：\n\n"
            f"待扫描内容预览:\n{target_preview}\n\n"
            f"项目上下文: {ctx_str}\n"
            f"{few_shot}\n"
            f"要求：\n"
            f"1. 跑 10 类静态规则（SQL注入/路径遍历/XSS/密钥泄露/硬编码/"
            f"不安全API/加密弱项/越权访问/日志未脱敏/配置不安全）\n"
            f"2. 列出命中规则与位置\n"
            f"3. 注意：最终判定以 SecurityScanTool 扫描报告为准"
        )


class RuntimeAuditHedgehogAgent(HedgehogAgent):
    """运行时审计子岗位（P5 扩容）。

    继承 HedgehogAgent，agent_id=hedgehog_runtime。
    职责：聚合 SecurityReport 生成月度报告、跟踪审计记录、统计拦截率。
    """

    def __init__(
        self,
        event_bus: EventBus,
        router: Router,
        tool_registry: ToolRegistry,
        context: ContextManager,
        tracer: Tracer | None = None,
        rag: RAGSystem | None = None,
        report_generator: SecurityReportGenerator | None = None,
        response_style: str = "default",
    ) -> None:
        super().__init__(
            event_bus=event_bus,
            router=router,
            tool_registry=tool_registry,
            context=context,
            tracer=tracer,
            rag=rag,
            response_style=response_style,
        )
        self._rebind_topic("hedgehog_runtime")
        self.role = "运行时审计"
        # P5 扩容：内置 SecurityReportGenerator 实例
        self._report_gen = report_generator or SecurityReportGenerator()

    @property
    def report_generator(self) -> SecurityReportGenerator:
        """暴露月报生成器供外部查询。"""
        return self._report_gen

    def _build_prompt(self, task: Task) -> str:
        """运行时审计专属提示词。"""
        target = (
            task.payload.get("code")
            or task.payload.get("path")
            or task.payload.get("text", "")
        )
        target_preview = str(target)[:200] if target else "(空)"
        ctx = self._context.get_context(self.agent_id, task)
        ctx_str = ", ".join(f"{k}={v}" for k, v in ctx.items()) if ctx else "无"
        stats_summary = self._report_gen.stats()
        few_shot = self.build_rag_fewshot(f"运行时审计 {target_preview}")
        return (
            f"你是戒备猬（运行时审计岗），BlueDeer 森林公司的运行时安全审计员工。\n"
            f"请执行运行时审计并更新月报：\n\n"
            f"待审计内容预览:\n{target_preview}\n\n"
            f"项目上下文: {ctx_str}\n"
            f"累计审计记录: {stats_summary['total']} 条，"
            f"拦截 {stats_summary['blocked_count']} 次\n"
            f"{few_shot}\n"
            f"要求：\n"
            f"1. 扫描后将 SecurityReport 加入月报生成器\n"
            f"2. 按需生成 Markdown 月度报告\n"
            f"3. 跟踪高危目标与拦截率趋势"
        )

    async def handle(self, task: Task) -> TaskResult:
        """运行时审计专属流程：扫描 → 加入月报 → 返回报告。"""
        result = await super().handle(task)
        # P5 扩容：成功时把 SecurityReport 加入月报生成器
        if result.status == TaskStatus.SUCCESS and result.output:
            scan_report_dict = result.output.get("scan_report")
            if scan_report_dict:
                # 从 dict 重建轻量 SecurityReport 用于月报聚合
                from core.security import RiskLevel, SecurityReport, Threat

                threats: list[Threat] = []
                for t in scan_report_dict.get("threats", []):
                    try:
                        threats.append(
                            Threat(
                                threat_type=t.get("threat_type", ""),
                                risk=RiskLevel(t.get("risk", "safe")),
                                matched=t.get("matched", ""),
                                location=t.get("location", ""),
                            )
                        )
                    except (ValueError, KeyError):
                        continue
                report = SecurityReport(
                    target=scan_report_dict.get("target", ""),
                    threats=threats,
                    scanned_at=scan_report_dict.get("scanned_at", 0.0),
                )
                self._report_gen.add_report(report)
                # 把月报统计附到输出
                result.output["monthly_stats"] = self._report_gen.stats()
        return result

    def generate_monthly_report(self, period_label: str = "本月") -> str:
        """生成 Markdown 月度安全报告。"""
        return self._report_gen.generate_markdown(period_label)


class KeyManagementHedgehogAgent(HedgehogAgent):
    """密钥管理子岗位（P5 扩容）。

    继承 HedgehogAgent，agent_id=hedgehog_keymgmt。
    职责：专注密钥泄露/硬编码密码/API Key 明文/数据库连接串检测。
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
            event_bus=event_bus,
            router=router,
            tool_registry=tool_registry,
            context=context,
            tracer=tracer,
            rag=rag,
            response_style=response_style,
        )
        self._rebind_topic("hedgehog_keymgmt")
        self.role = "密钥管理"

    def _build_prompt(self, task: Task) -> str:
        """密钥管理专属提示词。"""
        target = (
            task.payload.get("code")
            or task.payload.get("path")
            or task.payload.get("text", "")
        )
        target_preview = str(target)[:200] if target else "(空)"
        ctx = self._context.get_context(self.agent_id, task)
        ctx_str = ", ".join(f"{k}={v}" for k, v in ctx.items()) if ctx else "无"
        few_shot = self.build_rag_fewshot(f"密钥管理 {target_preview}")
        return (
            f"你是戒备猬（密钥管理岗），BlueDeer 森林公司的密钥安全审计员工。\n"
            f"请专注检测密钥/凭证类风险：\n\n"
            f"待审计内容预览:\n{target_preview}\n\n"
            f"项目上下文: {ctx_str}\n"
            f"{few_shot}\n"
            f"要求：\n"
            f"1. 检测 API Key / password / token / AKSK / SK 明文泄露\n"
            f"2. 检测硬编码密码与数据库连接串\n"
            f"3. 检测日志未脱敏（print password / logger token）\n"
            f"4. 检测 SECRET_KEY 硬编码（Django 风格）\n"
            f"5. 建议接入密钥管理服务或环境变量"
        )

    def _self_check(self, task: Task, output: dict[str, Any]) -> None:
        """密钥管理岗位额外校验：关注 secret_leak 类威胁。"""
        super()._self_check(task, output)
        # P5 扩容：密钥管理岗位额外统计 secret_leak 命中数
        scan_report = output.get("scan_report", {})
        secret_threats = [
            t
            for t in scan_report.get("threats", [])
            if t.get("threat_type", "").startswith("secret_leak")
            or t.get("threat_type", "").startswith("hardcoded:password")
            or t.get("threat_type", "").startswith("undisinfected_log")
        ]
        # 把密钥类威胁统计附到 output（不抛异常，仅附加信息）
        output["key_related_threat_count"] = len(secret_threats)
