"""BlueDeer Harness（忧郁鹿总经理）：全局统筹调度器。

P6 前置优化：
- 接入 DreamSystem，梦境结果同步到 reward
- Token 节省/低成本占比同步到 reward
- aggregate 增加 dream_stats / token_savings 字段

P0 修复（融合 50 项目）：
- 任务卡死熔断：超时自动转 FAILED 并触发重分配（项目8 DeerFlow、项目12 RufloLabs、项目47 OpenMAS）
- 负载均衡：least-load 选 assignee（项目12 RufloLabs 负载流光）
- 异常重分配：FAILED 任务可重分配给其他 Agent（项目8 DeerFlow 故障熔断）
- 删除 _settle_rewards 死代码（项目13 ponytail YAGNI）
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as CFTimeoutError
from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

from core.config import get_config
from core.event_bus import EventBus
from core.reward import RewardSystem
from core.scene import CEOOffice
from core.task import (
    RESULT_TOPIC,
    Task,
    TaskResult,
    TaskStatus,
)
from core.token_auditor import TokenAuditor
from core.tracer import Tracer

if TYPE_CHECKING:
    from core.context import ContextManager

logger = logging.getLogger("bluedeer.harness")


@dataclass
class HarnessResult:
    """通用任务/函数执行结果。"""
    passed: bool = False
    duration_ms: float = 0.0
    error: str = ""
    output: Any = None

class Harness:
    """忧郁鹿总经理 / 全局统筹调度器。

    职责：
    1. submit_task：经事件总线将任务分发到指派 Agent 的 topic。
    2. aggregate：汇总各 TaskResult，返回任务看板状态。
    3. 维护内存任务看板（dict[task_id, TaskResult]）。
    4. P0 修复：任务卡死熔断 + 负载均衡 + 异常重分配。

    融合项目：
    - 项目8 DeerFlow 事件驱动故障熔断
    - 项目12 RufloLabs 负载流光调度
    - 项目47 OpenMAS 故障场景模拟
    """

    def __init__(
        self,
        event_bus: EventBus,
        tracer: Tracer | None = None,
        token_auditor: TokenAuditor | None = None,
        reward_system: RewardSystem | None = None,
        context: ContextManager | None = None,
        scene: CEOOffice | None = None,
    ) -> None:
        self._bus = event_bus
        self._tracer = tracer
        self._task_board: dict[str, TaskResult] = {}
        self._pending: dict[str, Task] = {}
        self._token_auditor = token_auditor
        self._reward_system = reward_system
        # P0 修复：ContextManager 引用（用于 Token 超限自动清理任务临时上下文）
        self._context = context
        # P0 修复：Agent 在途任务计数（负载均衡依据）
        self._in_flight: dict[str, int] = {}
        # P0 修复：任务重分配计数（防无限重试）
        self._reallocate_count: dict[str, int] = {}
        # P6 重试管理器（exponential backoff）
        from core.retry import RetryManager
        self._retry_mgr = RetryManager()
        # P6 审计日志
        from core.audit import get_audit_log
        self._audit = get_audit_log()
        # DAG 任务依赖图（Plan C）
        self._dag: Any = None
        self._webhook: Any = None
        self._task_event_cb: Any = None

        # P0 修复：Token 超限自动清理任务临时上下文
        if self._token_auditor is not None and self._context is not None:
            self._token_auditor.set_overload_callback(self._on_token_overload)

        # 订阅结果 topic
        self._bus.subscribe(RESULT_TOPIC, self._on_result)

        # 注册总经理办公室场景
        self._scene = scene or CEOOffice()

    @property
    def scene(self) -> CEOOffice:
        """获取总经理办公室场景。"""
        return self._scene

    def _on_token_overload(self, agent_id: str, task_id: str) -> None:
        """P0 修复：Token 超限回调，清理任务临时上下文。

        融合项目8 DeerFlow 故障熔断：超限时自动 clear_task 释放上下文占用，
        避免后续任务因上下文堆积继续超限。
        """
        if self._context is not None:
            self._context.clear_task(task_id)
            logger.info(
                "Token 超限自动清理任务临时上下文: agent=%s, task=%s",
                agent_id, task_id,
            )

    def set_dag(self, dag: Any) -> None:
        """绑定 DAG 依赖图。"""
        self._dag = dag

    def set_webhook(self, webhook: Any) -> None:
        """绑定 Webhook 调度器（用于 DAG 事件推送）。"""
        self._webhook = webhook

    def set_task_event_cb(self, cb: Any) -> None:
        """绑定任务事件回调（用于 WebSocket 实时推送）。"""
        self._task_event_cb = cb

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
                tid for tid, r in self._task_board.items()
                if r.status == TaskStatus.SUCCESS
            }
            if not self._dag.ready(task.id, completed):
                logger.info(
                    "任务 %s 等待前置依赖，暂不执行。"
                    "已就绪: %s", task.id, sorted(completed),
                )
                return

        self._in_flight[task.assignee] = self._in_flight.get(task.assignee, 0) + 1

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
            task_id=task.id, action="submitted", agent=task.assignee,
            detail=f"下发至 {task.assignee}", trace_id=task.trace_id,
        )

    async def submit_and_wait(
        self, task: Task, timeout: float = 30.0
    ) -> TaskResult:
        """下发任务并等待结果（请求-应答模式）。

        Args:
            task: 要下发的任务。
            timeout: 超时秒数。

        Returns:
            TaskResult。
        """
        self._pending[task.id] = task
        self._in_flight[task.assignee] = self._in_flight.get(task.assignee, 0) + 1

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
            task_id=result.task_id, action="completed",
            agent=agent_id, detail=result.error or "",
            new_status=result.status.value, trace_id=result.trace_id,
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
            asyncio.ensure_future(self._task_event_cb({
                "event": "task_result",
                "task_id": result.task_id,
                "status": result.status.value,
                "error": result.error,
                "timestamp": time.time(),
            }))

        # P6: 成功时清除重试状态
        if result.status == TaskStatus.SUCCESS:
            self._retry_mgr.record_success(result.task_id)

        # P0 修复：异常重分配（融合项目8 DeerFlow 故障熔断）
        if result.status == TaskStatus.FAILED:
            await self._on_task_failed(result, pending_task)

        # Plan C DAG：成功完成后自动触发下游就绪任务
        if result.status == TaskStatus.SUCCESS and self._dag is not None:
            await self._cascade_dag(result.task_id)
        # DAG 失败处理：前置失败，标记下游为 blocked
        elif result.status == TaskStatus.FAILED and self._dag is not None:
            self._block_dag_downstream(result.task_id)

    def _block_dag_downstream(self, failed_id: str) -> None:
        """DAG 失败处理：标记直接依赖失败节点的下游任务为 blocked。"""
        for dep_id in self._dag.dependents(failed_id):
            if dep_id in self._pending:
                logger.info(
                    "DAG 失败级联: %s 失败，阻塞 %s", failed_id, dep_id,
                )
                self._pending.pop(dep_id, None)
                from core.task import TaskResult, TaskStatus
                self._task_board[dep_id] = TaskResult(
                    task_id=dep_id,
                    trace_id="",
                    status=TaskStatus.FAILED,
                    error=f"前置任务 {failed_id} 失败",
                )
                if self._webhook:
                    asyncio.ensure_future(self._webhook.fire_dag_event(
                        "dag.blocked",
                        {"task_id": dep_id, "blocked_by": failed_id},
                    ))
            self._block_dag_downstream(dep_id)

    async def _cascade_dag(self, completed_id: str) -> None:
        """DAG 级联：当某任务成功后，自动下发所有就绪的下游任务。"""
        completed = {
            tid for tid, r in self._task_board.items()
            if r.status == TaskStatus.SUCCESS
        }
        for nid in self._dag.dependents(completed_id):
            if nid not in self._pending:
                continue
            if self._dag.ready(nid, completed):
                task = self._pending.get(nid)
                if task and nid not in completed:
                    logger.info(
                        "DAG 级联触发: %s 已完成，下发 %s",
                        completed_id, nid,
                    )
                    self._in_flight[task.assignee] = self._in_flight.get(task.assignee, 0) + 1
                    assignee_topic = f"agent.{task.assignee}"
                    await self._bus.publish(assignee_topic, task)
                    if self._webhook:
                        await self._webhook.fire_dag_event(
                            "dag.completed",
                            {"task_id": nid, "triggered_by": completed_id, "assignee": task.assignee},
                        )

    def aggregate(self) -> dict[str, Any]:
        """汇总任务看板状态。"""
        total = len(self._task_board)
        success = sum(
            1 for r in self._task_board.values() if r.status == TaskStatus.SUCCESS
        )
        failed = sum(
            1 for r in self._task_board.values() if r.status == TaskStatus.FAILED
        )
        pending = len(self._pending)
        total_tokens = sum(r.token_usage.total for r in self._task_board.values())

        # P0 修复：用公开方法替代 _profiles 私有属性访问
        achievement_progress = {}
        if self._reward_system:
            for aid in self._reward_system.leaderboard_agent_ids():
                achievement_progress[aid] = self._reward_system.achievement_progress(aid)

        return {
            "total": total,
            "success": success,
            "failed": failed,
            "pending": pending,
            "total_tokens": total_tokens,
            "in_flight": dict(self._in_flight),
            "tasks": {
                tid: {
                    "status": r.status.value,
                    "tokens": r.token_usage.total,
                    "error": r.error,
                }
                for tid, r in self._task_board.items()
            },
            "rewards": self._reward_system.leaderboard() if self._reward_system else [],
            "token_stats": self._token_auditor.get_total_stats() if self._token_auditor else {},
            # P6 新增字段
            "token_savings": (
                self._token_auditor.get_savings() if self._token_auditor else {"total_saved": 0}
            ),
            "achievement_progress": achievement_progress,
            "dag": self._dag.topological_sort() if self._dag else [],
            "dag_blocked": [
                tid for tid in self._pending
                if self._dag is not None
                and self._dag.has_node(tid)
                and not self._dag.ready(
                    tid,
                    {t for t, r in self._task_board.items() if r.status == TaskStatus.SUCCESS},
                )
            ] if self._dag else [],
        }

    # ---- P0 修复：任务熔断 + 负载均衡 + 重分配 ----

    def cleanup_old_tasks(self, max_age: float = 3600.0, now: float | None = None) -> int:
        """清理超过指定时长的已完成任务记录和重分配计数。

        Args:
            max_age: 最大保留时长（秒），默认 1 小时。
            now: 当前时间戳（测试注入），None 则用 time.time()。

        Returns:
            清理的任务记录数。
        """
        if now is None:
            now = time.time()
        stale_ids = [
            tid for tid, r in self._task_board.items()
            if now - r.timestamp > max_age
        ]
        for tid in stale_ids:
            del self._task_board[tid]
            self._reallocate_count.pop(tid, None)
        if stale_ids:
            logger.info("清理过期任务记录: %d 条", len(stale_ids))
        return len(stale_ids)

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

    async def _on_task_failed(
        self, result: TaskResult, task: Task | None
    ) -> None:
        """P0 修复：异常重分配 + P6 指数退避重试 hook。

        融合项目8 DeerFlow 故障熔断：先尝试指数退避重试（同一 Agent），
        重试耗尽后换 Agent 重分配。
        """
        if task is None:
            logger.warning("任务 %s 失败（无原始任务）: %s", result.task_id, result.error)
            return

        cfg = get_config().task

        # P6: 指数退避重试（同一 Agent）
        if cfg.retry_enabled:
            state = self._retry_mgr.record_failure(result.task_id, result.error or "")
            if not state.exhausted:
                self._audit.record_simple(
                    task_id=result.task_id, action="retry",
                    agent=task.assignee, attempt=state.attempt,
                    detail=f"第{state.attempt}次重试: {result.error}",
                    trace_id=result.trace_id,
                )
                delay = state.next_retry_time - time.time()
                if delay > 0:
                    logger.info(
                        "任务 %s 第 %d/%d 次重试，等待 %.1fs",
                        result.task_id, state.attempt, cfg.retry_max_attempts, delay,
                    )
                    await asyncio.sleep(delay)
                await self.submit_task(task)
                return

        # P0: 换 Agent 重分配
        count = self._reallocate_count.get(result.task_id, 0)
        if count >= cfg.max_reallocate:
            logger.warning(
                "任务 %s 失败且已达重分配上限 %d 次，放弃: %s",
                result.task_id, cfg.max_reallocate, result.error,
            )
            return

        new_assignee = self._pick_least_loaded(exclude=task.assignee)
        if new_assignee is None:
            logger.warning("任务 %s 失败，无可用 Agent 重分配: %s", result.task_id, result.error)
            return

        self._reallocate_count[result.task_id] = count + 1
        self._audit.record_simple(
            task_id=result.task_id, action="reallocated",
            agent=task.assignee, attempt=count + 1,
            detail=f"重分配: {task.assignee} → {new_assignee}",
            trace_id=result.trace_id,
        )
        logger.info(
            "任务 %s 重分配: %s → %s（第 %d 次）",
            result.task_id, task.assignee, new_assignee, count + 1,
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

    def _decrement_in_flight(self, agent_id: str) -> None:
        """递减 Agent 在途计数（不低于 0）。"""
        current = self._in_flight.get(agent_id, 0)
        if current <= 1:
            self._in_flight.pop(agent_id, None)
        else:
            self._in_flight[agent_id] = current - 1

    def _balance_load(self, task: Task) -> str:
        """负载均衡 hook（P0 修复：least-load 选 assignee）。

        融合项目12 RufloLabs 负载流光调度。
        若 task.assignee 已指定且负载可接受则保留，否则选最低负载 Agent。
        """
        if task.assignee and self._in_flight.get(task.assignee, 0) < 3:
            return task.assignee
        least = self._pick_least_loaded(exclude="")
        return least if least else task.assignee

    # ---- 任务持久化 ----

    def save_state(self, path: str = "data/task_state.json") -> int:
        """保存任务看板到数据库（并向后兼容写入 JSON）。

        Returns:
            保存的任务记录数。
        """
        board_data = {
            tid: {
                "trace_id": r.trace_id,
                "timestamp": r.timestamp,
                "status": r.status.value,
                "error": r.error,
                "task_type": r.task_type,
                "agent_id": r.agent_id,
                "tokens_in": r.token_usage.tokens_in,
                "tokens_out": r.token_usage.tokens_out,
                "created_at": r.timestamp,
            }
            for tid, r in self._task_board.items()
        }
        pending_data = {
            tid: {
                "trace_id": t.trace_id,
                "created_at": t.timestamp,
                "type": t.type,
                "assignee": t.assignee,
                "priority": t.priority,
                "context_ref": t.context_ref,
            }
            for tid, t in self._pending.items()
        }
        try:
            from core.database import Database
            db = Database()
            db.save_task_results(board_data)
            db.save_task_pending(pending_data)
        except Exception as e:
            logger.warning("保存任务状态到数据库失败: %s", e)

        # 向后兼容 JSON 写入
        import json, os
        state = {
            "board": {
                tid: {
                    "task_id": r.task_id,
                    "trace_id": r.trace_id,
                    "timestamp": r.timestamp,
                    "status": r.status.value,
                    "error": r.error,
                    "task_type": r.task_type,
                    "agent_id": r.agent_id,
                    "token_usage": {
                        "tokens_in": r.token_usage.tokens_in,
                        "tokens_out": r.token_usage.tokens_out,
                    },
                }
                for tid, r in self._task_board.items()
            },
            "pending": {
                tid: {
                    "id": t.id,
                    "trace_id": t.trace_id,
                    "timestamp": t.timestamp,
                    "type": t.type,
                    "assignee": t.assignee,
                    "priority": t.priority,
                    "context_ref": t.context_ref,
                }
                for tid, t in self._pending.items()
            },
            "saved_at": time.time(),
        }
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        count = len(state["board"])
        logger.info("任务状态已保存: %s (%d 条)", path, count)
        return count

    def load_state(self, path: str = "data/task_state.json") -> int:
        """从数据库恢复任务看板（优先），找不到则回退 JSON。

        Returns:
            恢复的任务记录数。
        """
        loaded = 0
        try:
            from core.database import Database
            db = Database()
            rows = db.load_task_results()
            if rows:
                for r in rows:
                    result = TaskResult(
                        task_id=r["task_id"],
                        trace_id=r.get("trace_id", ""),
                        timestamp=r.get("created_at", 0.0),
                        status=TaskStatus(r.get("status", "pending")),
                        error=r.get("error", ""),
                        task_type=r.get("task_type", "general"),
                        agent_id=r.get("agent_id", ""),
                        token_usage=TokenUsage(
                            tokens_in=r.get("tokens_in", 0),
                            tokens_out=r.get("tokens_out", 0),
                        ),
                    )
                    self._task_board[r["task_id"]] = result
                    loaded += 1
            pending_rows = db.load_task_pending()
            if pending_rows:
                for t in pending_rows:
                    task = Task(
                        id=t["task_id"],
                        trace_id=t.get("trace_id", ""),
                        timestamp=t.get("created_at", 0.0),
                        type=t.get("task_type", "general"),
                        assignee=t.get("assignee", ""),
                        priority=t.get("priority", 0),
                        context_ref=t.get("context_ref", ""),
                    )
                    self._pending[t["task_id"]] = task
        except Exception as e:
            logger.warning("从数据库恢复失败，尝试 JSON: %s", e)

        if loaded > 0:
            logger.info("任务状态已从数据库恢复 (%d 条)", loaded)
            return loaded

        # 回退 JSON
        import json, os
        if not os.path.exists(path):
            logger.info("无存档文件可恢复: %s", path)
            return 0
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        for tid, rd in state.get("board", {}).items():
            token = rd.get("token_usage", {})
            result = TaskResult(
                task_id=rd["task_id"],
                trace_id=rd.get("trace_id", tid),
                timestamp=rd.get("timestamp", 0.0),
                status=TaskStatus(rd["status"]),
                error=rd.get("error"),
                task_type=rd.get("task_type", "general"),
                agent_id=rd.get("agent_id", ""),
                token_usage=TokenUsage(
                    tokens_in=token.get("tokens_in", 0),
                    tokens_out=token.get("tokens_out", 0),
                ),
            )
            self._task_board[tid] = result
        for tid, td in state.get("pending", {}).items():
            task = Task(
                id=td["id"],
                trace_id=td.get("trace_id", tid),
                timestamp=td.get("timestamp", 0.0),
                type=td.get("type", "general"),
                assignee=td.get("assignee", ""),
                priority=td.get("priority", 0),
                context_ref=td.get("context_ref", ""),
            )
            self._pending[tid] = task
        count = len(state.get("board", {}))
        logger.info("任务状态已从 JSON 恢复: %s (%d 条)", path, count)
        return count

    # ---- run_concurrent / run_with_timeout ----

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
                return HarnessResult(passed=True, duration_ms=(time.time() - t0) * 1000, output=out)
            except Exception as e:
                return HarnessResult(passed=False, duration_ms=(time.time() - t0) * 1000, error=str(e))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            fut = {pool.submit(_run, i, t): i for i, t in enumerate(tasks)}
            from concurrent.futures import as_completed
            for f in as_completed(fut):
                idx = fut[f]
                results[idx] = f.result()
        return results

    @staticmethod
    def run_with_timeout(func: Callable, timeout: float = 30, *args, **kwargs) -> HarnessResult:
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
                return HarnessResult(passed=True, duration_ms=(time.time() - t0) * 1000, output=out)
        except CFTimeoutError:
            return HarnessResult(passed=False, duration_ms=(time.time() - t0) * 1000, error=f"超时 {timeout}s")
        except Exception as e:
            return HarnessResult(passed=False, duration_ms=(time.time() - t0) * 1000, error=str(e))

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
