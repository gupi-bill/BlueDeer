"""BlueDeer 任务分发器（008-3 拆分自 core/harness.py）。

TaskDispatcherMixin 承载任务下发、请求-应答、结果回执、DAG 级联、
WebSocket 推送与 Token/奖励结算逻辑。依赖 TaskBoardMixin 的数据字段
（_task_board/_pending/_in_flight），由 Harness 组合使用。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as CFTimeoutError
from dataclasses import dataclass
from typing import Any

from core.task import RESULT_TOPIC, Task, TaskResult, TaskStatus

logger = logging.getLogger("bluedeer.task_dispatcher")


@dataclass
class HarnessResult:
    """通用任务/函数执行结果。"""

    passed: bool = False
    duration_ms: float = 0.0
    error: str = ""
    output: Any = None


class TaskDispatcherMixin:
    """任务分发与结算。"""

    # ---- 下发 ----

    async def submit_task(self, task: Task) -> None:
        """下发任务到指派 Agent。

        P0 修复：记录下发时间用于卡死熔断，更新在途计数。
        Plan C DAG：前置依赖未完成则暂存，等前置跑完再下发。

        Args:
            task: 要下发的任务，assignee 已指定。
        """
        self._pending[task.id] = task

        # DAG 依赖检查
        if self._dag is not None and self._dag.has_node(task.id):
            completed = {
                tid
                for tid, r in self._task_board.items()
                if r.status == TaskStatus.SUCCESS
            }
            if not self._dag.ready(task.id, completed):
                logger.info(
                    "任务 %s 等待前置依赖，暂不执行。已就绪: %s",
                    task.id,
                    sorted(completed),
                )
                return

        self.in_flight_add(task.assignee)

        if self._tracer:
            self._tracer.span(
                task.trace_id,
                component="Harness",
                action="submit_task",
                task_id=task.id,
                assignee=task.assignee,
                task_type=task.type,
            )

        assignee_topic = f"agent.{task.assignee}"
        await self._bus.publish(assignee_topic, task)
        self._audit.record_simple(
            task_id=task.id,
            action="submitted",
            agent=task.assignee,
            detail=f"下发至 {task.assignee}",
            trace_id=task.trace_id,
        )

    async def submit_and_wait(self, task: Task, timeout: float = 30.0) -> TaskResult:
        """下发任务并等待结果（请求-应答模式）。

        Args:
            task: 要下发的任务。
            timeout: 超时秒数。

        Returns:
            TaskResult。
        """
        self._pending[task.id] = task
        self.in_flight_add(task.assignee)

        if self._tracer:
            self._tracer.span(
                task.trace_id,
                component="Harness",
                action="submit_and_wait",
                task_id=task.id,
                assignee=task.assignee,
            )

        assignee_topic = f"agent.{task.assignee}"
        result = await self._bus.request(
            task, assignee_topic, RESULT_TOPIC, timeout=timeout
        )
        self._task_board[task.id] = result
        self._pending.pop(task.id, None)
        self._decrement_in_flight(task.assignee)

        # P4: Token 审计 + 奖惩结算
        self._record_and_settle(result, task.assignee)

        if self._tracer:
            self._tracer.span(
                task.trace_id,
                component="Harness",
                action="result_received",
                task_id=task.id,
                status=result.status.value,
                tokens=result.token_usage.total,
            )

        return result

    # ---- 结果回执 ----

    async def _on_result(self, result: TaskResult) -> None:
        """收到 Agent 回传结果时的回调。

        Plan C DAG：成功完成后自动触发下游任务。
        """
        self._task_board[result.task_id] = result
        pending_task = self._pending.pop(result.task_id, None)
        agent_id = pending_task.assignee if pending_task else "unknown"
        if pending_task:
            self._decrement_in_flight(agent_id)

        # P6: 审计记录
        self._audit.record_simple(
            task_id=result.task_id,
            action="completed",
            agent=agent_id,
            detail=result.error or "",
            new_status=result.status.value,
            trace_id=result.trace_id,
        )

        # P4: Token 审计 + 奖惩结算
        self._record_and_settle(result, agent_id)

        if self._tracer:
            self._tracer.span(
                result.trace_id,
                component="Harness",
                action="result_received",
                task_id=result.task_id,
                status=result.status.value,
                tokens=result.token_usage.total,
            )

        # WebSocket 实时推送
        if self._task_event_cb:
            asyncio.ensure_future(
                self._task_event_cb(
                    {
                        "event": "task_result",
                        "task_id": result.task_id,
                        "status": result.status.value,
                        "error": result.error,
                        "timestamp": time.time(),
                    }
                )
            )

        # P6: 成功时清除重试状态
        if result.status == TaskStatus.SUCCESS:
            self._retry_mgr.record_success(result.task_id)

        # P0 修复：异常重分配（融合项目8 DeerFlow 故障熔断）
        if result.status == TaskStatus.FAILED:
            await self._on_task_failed(result, pending_task)

        # Plan C DAG：成功完成后自动触发下游就绪任务
        if result.status == TaskStatus.SUCCESS and self._dag is not None:
            await self._cascade_dag(result.task_id)
        elif result.status == TaskStatus.FAILED and self._dag is not None:
            self._block_dag_downstream(result.task_id)

    def _block_dag_downstream(self, failed_id: str) -> None:
        """DAG 失败处理：标记直接依赖失败节点的下游任务为 blocked。"""
        for dep_id in self._dag.dependents(failed_id):
            if dep_id in self._pending:
                logger.info(
                    "DAG 失败级联: %s 失败，阻塞 %s",
                    failed_id,
                    dep_id,
                )
                self._pending.pop(dep_id, None)
                self._task_board[dep_id] = TaskResult(
                    task_id=dep_id,
                    trace_id="",
                    status=TaskStatus.FAILED,
                    error=f"前置任务 {failed_id} 失败",
                )
                if self._webhook:
                    asyncio.ensure_future(
                        self._webhook.fire_dag_event(
                            "dag.blocked",
                            {"task_id": dep_id, "blocked_by": failed_id},
                        )
                    )
            self._block_dag_downstream(dep_id)

    async def _cascade_dag(self, completed_id: str) -> None:
        """DAG 级联：当某任务成功后，自动下发所有就绪的下游任务。"""
        completed = {
            tid for tid, r in self._task_board.items() if r.status == TaskStatus.SUCCESS
        }
        for nid in self._dag.dependents(completed_id):
            if nid not in self._pending:
                continue
            if self._dag.ready(nid, completed):
                task = self._pending.get(nid)
                if task and nid not in completed:
                    logger.info(
                        "DAG 级联触发: %s 已完成，下发 %s",
                        completed_id,
                        nid,
                    )
                    self.in_flight_add(task.assignee)
                    assignee_topic = f"agent.{task.assignee}"
                    await self._bus.publish(assignee_topic, task)
                    if self._webhook:
                        await self._webhook.fire_dag_event(
                            "dag.completed",
                            {
                                "task_id": nid,
                                "triggered_by": completed_id,
                                "assignee": task.assignee,
                            },
                        )

    # ---- 结算 ----

    def _record_and_settle(self, result: TaskResult, agent_id: str) -> None:
        """P4: Token 审计记录 + 奖惩结算。P6: 同步节省指标到 reward。"""
        # Token 审计
        if self._token_auditor:
            model_name = "unknown"
            if result.output and isinstance(result.output, dict):
                model_name = result.output.get("model_used", "unknown")
            self._token_auditor.record(
                agent_id=agent_id,
                task_id=result.task_id,
                model=model_name,
                tokens_in=result.token_usage.tokens_in,
                tokens_out=result.token_usage.tokens_out,
            )
            # 超限告警
            exceeded, msg = self._token_auditor.check_threshold(
                result.task_id, result.token_usage.total
            )
            if exceeded:
                logger.warning("Token 超限告警: %s", msg)

            # P6: 同步节省/低成本占比到 reward（每次任务后刷新）
            if self._reward_system:
                self._token_auditor.sync_to_reward(agent_id, self._reward_system)

        # 奖惩结算
        if self._reward_system:
            self._reward_system.settle(result, agent_id)

    # ---- 并发执行 ----

    @staticmethod
    def run_concurrent(
        tasks: list[Callable[[], Any]],
        max_workers: int = 4,
    ) -> list[HarnessResult]:
        """用 ThreadPoolExecutor 并发执行一批函数。

        Args:
            tasks: 可调用对象列表（无参）。
            max_workers: 最大并发数（默认 4）。

        Returns:
            与 tasks 顺序一致的 HarnessResult 列表。
        """
        results: list[HarnessResult] = [None] * len(tasks)

        def _run(idx: int, fn: Callable) -> HarnessResult:
            t0 = time.time()
            try:
                out = fn()
                return HarnessResult(
                    passed=True, duration_ms=(time.time() - t0) * 1000, output=out
                )
            except Exception as e:
                return HarnessResult(
                    passed=False, duration_ms=(time.time() - t0) * 1000, error=str(e)
                )

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            fut = {pool.submit(_run, i, t): i for i, t in enumerate(tasks)}
            from concurrent.futures import as_completed

            for f in as_completed(fut):
                idx = fut[f]
                results[idx] = f.result()
        return results

    @staticmethod
    def run_with_timeout(
        func: Callable, timeout: float = 30, *args: Any, **kwargs: Any
    ) -> HarnessResult:
        """给一个同步函数加超时执行（ThreadPoolExecutor 包装）。

        Args:
            func: 要执行的同步函数。
            timeout: 超时秒数（默认 30s）。
            *args, **kwargs: 传给 func。

        Returns:
            HarnessResult。
        """
        t0 = time.time()
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(func, *args, **kwargs)
                out = fut.result(timeout=timeout)
                return HarnessResult(
                    passed=True, duration_ms=(time.time() - t0) * 1000, output=out
                )
        except CFTimeoutError:
            return HarnessResult(
                passed=False,
                duration_ms=(time.time() - t0) * 1000,
                error=f"超时 {timeout}s",
            )
        except Exception as e:
            return HarnessResult(
                passed=False, duration_ms=(time.time() - t0) * 1000, error=str(e)
            )
