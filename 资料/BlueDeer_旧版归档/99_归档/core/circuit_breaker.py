"""BlueDeer 任务熔断器（008-3 拆分自 core/harness.py）。

CircuitBreakerMixin 承载：
- 卡死任务扫描（check_stale_tasks / fail_stale_task）
- 异常重分配 + 指数退避重试（_on_task_failed）
- 负载均衡（_pick_least_loaded / _balance_load）
- Token 超限回调（_on_token_overload）

依赖 TaskBoardMixin 数据字段与 TaskDispatcherMixin 的 submit_task，
由 Harness 组合使用。
"""

from __future__ import annotations

import asyncio
import logging
import time

from core.config import get_config
from core.task import Task, TaskResult, TaskStatus

logger = logging.getLogger("bluedeer.circuit_breaker")


class CircuitBreakerMixin:
    """任务熔断、重试与负载均衡。"""

    def _breaker_init(self) -> None:
        """初始化熔断相关字段（Harness.__init__ 调用）。"""
        from core.retry import RetryManager

        self._retry_mgr = RetryManager()

    def _on_token_overload(self, agent_id: str, task_id: str) -> None:
        """P0 修复：Token 超限回调，清理任务临时上下文。

        融合项目8 DeerFlow 故障熔断：超限时自动 clear_task 释放上下文占用，
        避免后续任务因上下文堆积继续超限。
        """
        if self._context is not None:
            self._context.clear_task(task_id)
            logger.info(
                "Token 超限自动清理任务临时上下文: agent=%s, task=%s",
                agent_id,
                task_id,
            )

    def check_stale_tasks(self, now: float | None = None) -> list[str]:
        """P0 修复：扫描卡死任务，返回超时 task_id 列表。

        融合项目8 DeerFlow 故障熔断 + 项目47 OpenMAS 任务卡死模拟。
        调用方应在事件循环周期中定期调用此方法，并对返回的 task_id
        调用 fail_stale_task() 完成熔断。

        Args:
            now: 当前时间戳（测试注入），None 则用 time.time()。

        Returns:
            超时的 task_id 列表。
        """
        if now is None:
            now = time.time()
        stale: list[str] = []
        for tid, task in self._pending.items():
            submitted_at = task.timestamp
            if now - submitted_at > get_config().task.timeout_seconds:
                stale.append(tid)
        return stale

    async def fail_stale_task(self, task_id: str) -> None:
        """P0 修复：熔断超时任务，转为 FAILED 并触发重分配。"""
        task = self._pending.pop(task_id, None)
        if task is None:
            return
        self._decrement_in_flight(task.assignee)
        failed_result = TaskResult(
            trace_id=task.trace_id,
            task_id=task_id,
            status=TaskStatus.FAILED,
            error=f"任务卡死熔断（超时 {get_config().task.timeout_seconds}s）",
        )
        self._task_board[task_id] = failed_result
        logger.warning("任务 %s 卡死熔断，触发重分配", task_id)
        await self._on_task_failed(failed_result, task)

    async def _on_task_failed(self, result: TaskResult, task: Task | None) -> None:
        """P0 修复：异常重分配 + P6 指数退避重试 hook。

        融合项目8 DeerFlow 故障熔断：先尝试指数退避重试（同一 Agent），
        重试耗尽后换 Agent 重分配。
        """
        if task is None:
            logger.warning(
                "任务 %s 失败（无原始任务）: %s", result.task_id, result.error
            )
            return

        cfg = get_config().task

        # P6: 指数退避重试（同一 Agent）
        if cfg.retry_enabled:
            state = self._retry_mgr.record_failure(result.task_id, result.error or "")
            if not state.exhausted:
                self._audit.record_simple(
                    task_id=result.task_id,
                    action="retry",
                    agent=task.assignee,
                    attempt=state.attempt,
                    detail=f"第{state.attempt}次重试: {result.error}",
                    trace_id=result.trace_id,
                )
                delay = state.next_retry_time - time.time()
                if delay > 0:
                    logger.info(
                        "任务 %s 第 %d/%d 次重试，等待 %.1fs",
                        result.task_id,
                        state.attempt,
                        cfg.retry_max_attempts,
                        delay,
                    )
                    await asyncio.sleep(delay)
                await self.submit_task(task)
                return

        # P0: 换 Agent 重分配
        count = self._reallocate_count.get(result.task_id, 0)
        if count >= cfg.max_reallocate:
            logger.warning(
                "任务 %s 失败且已达重分配上限 %d 次，放弃: %s",
                result.task_id,
                cfg.max_reallocate,
                result.error,
            )
            return

        new_assignee = self._pick_least_loaded(exclude=task.assignee)
        if new_assignee is None:
            logger.warning(
                "任务 %s 失败，无可用 Agent 重分配: %s", result.task_id, result.error
            )
            return

        self._reallocate_count[result.task_id] = count + 1
        self._audit.record_simple(
            task_id=result.task_id,
            action="reallocated",
            agent=task.assignee,
            attempt=count + 1,
            detail=f"重分配: {task.assignee} → {new_assignee}",
            trace_id=result.trace_id,
        )
        logger.info(
            "任务 %s 重分配: %s → %s（第 %d 次）",
            result.task_id,
            task.assignee,
            new_assignee,
            count + 1,
        )
        task.assignee = new_assignee
        await self.submit_task(task)

    def _pick_least_loaded(self, exclude: str = "") -> str | None:
        """P0 修复：负载均衡，选在途任务最少的 Agent。

        融合项目12 RufloLabs 负载流光调度。
        当前仅从已知的 agent_id 集合中选择；若无历史数据返回 None。
        """
        candidates = {
            aid: load for aid, load in self._in_flight.items() if aid != exclude
        }
        if not candidates:
            return None
        return min(candidates, key=lambda a: candidates[a])

    def _balance_load(self, task: Task) -> str:
        """负载均衡 hook（P0 修复：least-load 选 assignee）。

        融合项目12 RufloLabs 负载流光调度。
        若 task.assignee 已指定且负载可接受则保留，否则选最低负载 Agent。
        """
        if task.assignee and self._in_flight.get(task.assignee, 0) < 3:
            return task.assignee
        least = self._pick_least_loaded(exclude="")
        return least if least else task.assignee
