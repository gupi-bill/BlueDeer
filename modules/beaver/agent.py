"""勤恳海狸 Agent：构建部署专职员工。"""

from __future__ import annotations

import logging
from typing import Any

from core.base_agent import BaseAgent
from core.context import ContextManager
from core.event_bus import EventBus
from core.git_ops import GitHubClient, GitOps
from core.rag import RagCapable, RAGSystem
from core.task import Task, TaskResult, TaskStatus, TokenUsage
from core.tracer import Tracer
from models.router import Router
from modules.beaver.skills import BuildSkill, generate_commit_message
from tools.registry import ToolRegistry

logger = logging.getLogger("bluedeer.beaver")


_BUILD_QUEUE: list[dict[str, Any]] = []


def enqueue_build(build_data: dict[str, Any]) -> None:
    _BUILD_QUEUE.append(build_data)


def dequeue_build() -> dict[str, Any] | None:
    if not _BUILD_QUEUE:
        return None
    return _BUILD_QUEUE.pop(0)


def build_queue_count() -> int:
    return len(_BUILD_QUEUE)


class BeaverAgent(BaseAgent, RagCapable):
    """勤恳海狸：构建部署员工。

    继承 BaseAgent，覆盖 _build_prompt 与 _self_check。
    handle 流程：
    1. 调 TestRunTool 跑全量测试
    2. 全通过 → GitOps.add_all() → commit（自动生成 message）
    3. payload 指定 push → push 到远程
    4. payload 指定 pr → 创建 PR
    5. 测试失败 → FAILED（不提交，保护代码质量）

    P3 扩容：接入岗位私有 RAG，沉淀构建提交规范经验。
    """

    def __init__(
        self,
        event_bus: EventBus,
        router: Router,
        tool_registry: ToolRegistry,
        context: ContextManager,
        git_ops: GitOps | None = None,
        github_client: GitHubClient | None = None,
        tracer: Tracer | None = None,
        rag: RAGSystem | None = None,
        response_style: str = "default",
    ) -> None:
        super().__init__(
            agent_id="beaver",
            role="构建部署",
            event_bus=event_bus,
            router=router,
            tool_registry=tool_registry,
            context=context,
            tracer=tracer,
            response_style=response_style,
        )
        self._git = git_ops or GitOps()
        self._github = github_client or GitHubClient()
        self.bind_rag(rag)

    async def handle(self, task: Task) -> TaskResult:
        """勤恳海狸专属处理流程：测试 → 提交 → 可选推送/PR。"""
        if self._tracer:
            self._tracer.span(
                task.trace_id,
                component="BeaverAgent",
                action="handle_start",
                task_id=task.id,
                task_type=task.type,
            )

        total_tokens = TokenUsage()

        try:
            async with self.with_budget_check(task):
                test_path = task.payload.get("test_path", "tests/")
                commit_message = task.payload.get("commit_message")
                do_push = task.payload.get("push", False)
                do_pr = task.payload.get("pr", False)
                repo = task.payload.get("repo", "")
                pr_base = task.payload.get("pr_base", "main")

                # 1. 构建 prompt + 注入风格指令（用于 LLM 辅助生成 commit message）
                prompt = self._apply_style(self._build_prompt(task))

                # 2. 调 LLM 生成提交建议
                model_client = self._router.route(task.type)
                model_response = await model_client.complete(prompt)
                total_tokens.tokens_in += model_response.tokens_in
                total_tokens.tokens_out += model_response.tokens_out

                if self._tracer:
                    self._tracer.span(
                        task.trace_id,
                        component="BeaverAgent",
                        action="model_complete",
                        model=model_client.model_name,
                    )

                # 3. 跑测试
                build_skill = BuildSkill(self._tools, self._git)
                test_result = await build_skill.run_tests(str(test_path))

                if self._tracer:
                    self._tracer.span(
                        task.trace_id,
                        component="BeaverAgent",
                        action="test_run",
                        passed=test_result.get("passed"),
                    )

                # 4. 测试失败 → 不提交
                if not test_result.get("passed"):
                    output = {
                        "test_result": test_result,
                        "commit_result": None,
                        "push_result": None,
                        "pr_result": None,
                        "model_advice": model_response.content,
                        "model_used": model_client.model_name,
                    }
                    self._self_check(task, output)

                    if self._tracer:
                        self._tracer.span(
                            task.trace_id,
                            component="BeaverAgent",
                            action="handle_failed",
                            task_id=task.id,
                            reason="tests_failed",
                        )

                    return TaskResult(
                        trace_id=task.trace_id,
                        task_id=task.id,
                        status=TaskStatus.FAILED,
                        output=output,
                        error=f"测试未通过: {test_result.get('failed_count', 0)} 个失败，不提交",
                        token_usage=total_tokens,
                    )

                # 5. 测试通过 → Git 提交
                if not commit_message:
                    summary = task.payload.get("description", "自动提交")
                    commit_message = generate_commit_message(task.type, summary)

                commit_result = build_skill.git_commit(commit_message)

                if self._tracer:
                    self._tracer.span(
                        task.trace_id,
                        component="BeaverAgent",
                        action="committed",
                        success=commit_result.get("success"),
                        sha=commit_result.get("sha", ""),
                    )

                # 6. 可选推送
                push_result = None
                if do_push and commit_result.get("success"):
                    ok, msg = self._git.push()
                push_result = {"success": ok, "message": msg}

            # 7. 可选创建 PR
            pr_result = None
            if do_pr and repo:
                branch = self._git.current_branch()
                ok, resp = self._github.create_pr(
                    repo=repo,
                    title=commit_message,
                    head=branch,
                    base=pr_base,
                    body=f"自动提交: {commit_message}\n\n测试: {test_result.get('passed_count', 0)} 通过",
                )
                pr_result = {"success": ok, "response": resp}

            # 8. 组装输出 + 自检
            output = {
                "test_result": test_result,
                "commit_result": commit_result,
                "push_result": push_result,
                "pr_result": pr_result,
                "model_advice": model_response.content,
                "model_used": model_client.model_name,
                "commit_message": commit_message,
            }
            self._self_check(task, output)

            # P3: 规范提交经验写入岗位 RAG 库
            self.rag_ingest(
                id=f"commit_{task.id}",
                text=f"规范提交 {commit_message}",
                metadata={
                    "task_type": task.type,
                    "commit_message": commit_message,
                    "sha": commit_result.get("sha", ""),
                    "pushed": push_result is not None,
                },
            )

            if self._tracer:
                self._tracer.span(
                    task.trace_id,
                    component="BeaverAgent",
                    action="handle_success",
                    task_id=task.id,
                    sha=commit_result.get("sha", ""),
                )

            return TaskResult(
                trace_id=task.trace_id,
                task_id=task.id,
                status=TaskStatus.SUCCESS,
                output=output,
                token_usage=total_tokens,
            )

        except Exception as e:
            logger.exception("BeaverAgent 处理任务 %s 失败", task.id)

            healed = await self._try_self_heal(task, e)
            if healed is not None:
                return healed

            if self._tracer:
                self._tracer.error(
                    task.trace_id,
                    component="BeaverAgent",
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
        """构建构建部署提示词，注入 RAG 历史提交规范经验。"""
        test_path = task.payload.get("test_path", "tests/")
        description = task.payload.get("description", "自动构建部署")

        ctx = self._context.get_context(self.agent_id, task)
        ctx_str = ", ".join(f"{k}={v}" for k, v in ctx.items()) if ctx else "无"

        # P3: RAG 检索历史构建/提交经验
        few_shot = self.build_rag_fewshot(f"构建部署 {description}")

        return (
            f"你是勤恳海狸，BlueDeer 森林公司的构建部署员工。\n"
            f"请执行构建部署任务：\n\n"
            f"任务描述: {description}\n"
            f"测试路径: {test_path}\n"
            f"项目上下文: {ctx_str}\n"
            f"{few_shot}\n"
            f"要求：\n"
            f"1. 跑全量测试，必须全通过\n"
            f"2. 测试通过后 git add + commit（约定式提交）\n"
            f"3. 可选 push / 创建 PR\n"
            f"4. 测试失败则不提交，保护代码质量"
        )

    def _self_check(self, task: Task, output: dict[str, Any]) -> None:
        """校验构建结果完整性。"""
        if not output:
            raise ValueError("自检失败：输出为空")

        test_result = output.get("test_result")
        if not test_result:
            raise ValueError("自检失败：缺少测试结果")
        if "passed" not in test_result:
            raise ValueError("自检失败：测试结果缺少 passed 字段")

        # 若测试通过，必须有 commit_result
        if test_result.get("passed"):
            commit_result = output.get("commit_result")
            if not commit_result:
                raise ValueError("自检失败：测试通过但缺少提交结果")
            if "success" not in commit_result:
                raise ValueError("自检失败：提交结果缺少 success 字段")
