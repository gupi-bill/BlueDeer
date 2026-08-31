"""BlueDeer 并发任务编排器：DAG 依赖 + 并行执行 + 汇合 + 超时 + 状态快照。

evolution（并发维度 - R179）：
- 工作流经常是多步且依赖复杂的：A→B、A→C、B+C→D
- 串行执行慢，盲目并行又会破坏依赖
- DAG 编排：声明任务和依赖，按拓扑并行执行无依赖的任务
- 支持失败传播、超时、取消

P1 新增：状态快照（snapshot / restore），支持跨会话恢复。
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from core.exceptions import TaskDependencyError, TaskExecutionError, TaskTimeoutError
from core.observability import Observability

logger = logging.getLogger("bluedeer.orch")

__all__ = ["TaskExecutor", "TaskNode", "TaskOrchestrator"]


class TaskNode:
    """任务节点。"""

    __slots__ = (
        "deps",
        "exception",
        "finished_at",
        "func",
        "name",
        "result",
        "started_at",
        "state",
    )

    def __init__(self, name: str, func: Callable, deps: list[str] | None = None):
        self.name = name
        self.func = func
        self.deps = list(deps) if deps else []
        self.result: Any = None
        self.exception: Exception | None = None
        self.state = "pending"  # pending/running/done/failed/cancelled
        self.started_at = 0.0
        self.finished_at = 0.0


class TaskExecutor:
    """任务执行器：封装并发控制与任务执行逻辑。

    负责：
    - 并发度控制（asyncio.Semaphore）
    - 同步/异步函数统一执行
    - 执行异常捕获与日志
    """

    def __init__(self, max_workers: int = 4) -> None:
        if max_workers < 1:
            raise ValueError("max_workers 必须 >= 1")
        self._max_workers = max_workers
        self._sem = asyncio.Semaphore(max_workers)

    async def execute(self, node: TaskNode, dep_results: list) -> Any:
        """执行单个任务节点。"""
        async with self._sem:
            try:
                result = node.func(*dep_results)
                if inspect.isawaitable(result):
                    result = await result
                return result
            except Exception as exc:
                logger.warning("任务 %s 执行失败: %s", node.name, exc)
                raise


class TaskOrchestrator:
    """DAG 任务编排器。

    用法：
        orch = TaskOrchestrator(max_workers=4)
        orch.add_task("fetch_a", lambda: fetch("a"))
        orch.add_task("fetch_b", lambda: fetch("b"))
        orch.add_task("merge", lambda a, b: merge(a, b), deps=["fetch_a", "fetch_b"])
        results = orch.run(timeout=30.0)
        merged = results["merge"]

    支持集成 core.task_dag.TaskDAG：传入 dag 后自动同步依赖关系。
    """

    def __init__(self, max_workers: int = 4, dag: Any = None) -> None:
        if max_workers < 1:
            raise ValueError("max_workers 必须 >= 1")
        self._max_workers = max_workers
        self._tasks: dict[str, TaskNode] = {}
        self._lock = threading.RLock()
        self._dag = dag
        self._executor = TaskExecutor(max_workers)
        self._approval_callbacks: dict[str, Callable[[TaskNode], bool]] = {}
        self._paused_tasks: dict[str, TaskNode] = {}

    def add_task(
        self,
        name: str,
        func: Callable,
        deps: list[str] | None = None,
    ) -> TaskOrchestrator:
        """添加任务。返回 self 便于链式。"""
        with self._lock:
            if name in self._tasks:
                raise ValueError(f"任务已存在: {name}")
            self._tasks[name] = TaskNode(name, func, deps)
            # 同步到 TaskDAG
            if self._dag is not None:
                self._dag.add_node(name, depends_on=deps or [])
                self._dag.save()
        return self

    def _validate(self) -> None:
        """检查依赖完整性和无环。"""
        # 1. 所有 deps 必须存在
        for t in self._tasks.values():
            for d in t.deps:
                if d not in self._tasks:
                    raise ValueError(f"任务 {t.name} 依赖不存在的任务: {d}")
        # 2. 检查环（DFS）
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n: WHITE for n in self._tasks}

        def visit(node) -> Any:
            if color[node] == GRAY:
                raise TaskDependencyError(f"检测到循环依赖：{node}")
            if color[node] == BLACK:
                return
            color[node] = GRAY
            for d in self._tasks[node].deps:
                visit(d)
            color[node] = BLACK

        for n in self._tasks:
            if color[n] == WHITE:
                visit(n)

    def _get_ready(self) -> list[str]:
        """获取所有依赖已完成且自身 pending 的任务。"""
        ready = []
        for name, t in self._tasks.items():
            if t.state != "pending":
                continue
            if all(self._tasks[d].state == "done" for d in t.deps):
                ready.append(name)
        return ready

    def _has_failed_deps(self, node: TaskNode) -> bool:
        """检查依赖是否有失败。"""
        return any(self._tasks[d].state in ("failed", "cancelled") for d in node.deps)

    def run(self, timeout: float | None = None) -> dict[str, Any]:
        """运行所有任务。返回 {name: result}。

        - 按拓扑并行执行无依赖的任务
        - 依赖任务失败时，下游任务被取消
        - 超时取消所有未完成任务
        """
        with Observability.span("task_orchestrator.run", timeout=timeout or 0):
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return asyncio.run(self._run_async(timeout))
            raise RuntimeError(
                "TaskOrchestrator.run() 不能在有运行事件循环的协程中调用，"
                "请改用 await orch.run_async(timeout=...)"
            )

    async def _invoke(self, node: TaskNode, dep_results: list) -> Any:
        """执行节点函数（委托给 TaskExecutor）。"""
        with Observability.span("task_orchestrator.invoke", task=node.name):
            return await self._executor.execute(node, dep_results)

    async def run_async(self, timeout: float | None = None) -> dict[str, Any]:
        """协程友好的编排入口：await orch.run_async(timeout=...)。"""
        with Observability.span("task_orchestrator.run_async", timeout=timeout or 0):
            return await self._run_async(timeout)

    def _run_async_check_timeout(
        self, deadline: float | None, tasks_snapshot: dict, pending: dict
    ) -> None:
        if deadline is not None and time.monotonic() >= deadline:
            for t in tasks_snapshot.values():
                if t.state in ("pending", "running"):
                    t.state = "cancelled"
            for fut in list(pending):
                fut.cancel()
            pending.clear()
            raise TaskTimeoutError(f"编排超时 {self._timeout}s")

    def _run_async_cleanup_completed(
        self, tasks_snapshot: dict, pending: dict, results: dict
    ) -> None:
        for fut in list(pending):
            if fut.done():
                name = pending.pop(fut)
                t = tasks_snapshot[name]
                t.finished_at = time.time()
                try:
                    t.result = fut.result()
                    t.state = "done"
                    results[name] = t.result
                except Exception as e:
                    t.exception = e
                    t.state = "failed"
                fut.cancel()

    def _run_async_submit_ready(self, tasks_snapshot: dict, pending: dict) -> bool:
        ready = self._get_ready()
        submitted_any = False
        for name in ready:
            t = tasks_snapshot[name]
            if self._has_failed_deps(t):
                t.state = "cancelled"
                continue
            if t.state == "running":
                continue
            if not self._check_approval(t):
                continue
            dep_results = [tasks_snapshot[d].result for d in t.deps]
            t.state = "running"
            t.started_at = time.time()
            fut = asyncio.ensure_future(self._invoke(t, dep_results))
            pending[fut] = name
            submitted_any = True
        return submitted_any

    async def _run_async_wait_done(self, pending: dict, deadline: float | None) -> set:
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return set()
            try:
                done, _ = await asyncio.wait(
                    list(pending.keys()),
                    timeout=remaining,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            except TimeoutError:
                logger.exception("Exception in block")
                return set()
        else:
            done, _ = await asyncio.wait(
                list(pending.keys()),
                return_when=asyncio.FIRST_COMPLETED,
            )
        return done

    def _run_async_process_done(
        self, done: set, pending: dict, tasks_snapshot: dict, results: dict
    ) -> None:
        for fut in done:
            name = pending[fut]
            t = tasks_snapshot[name]
            t.finished_at = time.time()
            try:
                t.result = fut.result()
                t.state = "done"
                results[name] = t.result
            except asyncio.CancelledError:
                t.state = "cancelled"
                logger.info("任务 %s 被取消", name)
            except Exception as e:
                t.exception = e
                t.state = "failed"
            finally:
                pending.pop(fut, None)

    async def _run_async(self, timeout: float | None = None) -> dict[str, Any]:
        """asyncio 版本的编排执行（按拓扑并行 + 超时 + 失败传播）。"""
        self._timeout = timeout
        with self._lock:
            self._validate()
            tasks_snapshot = dict(self._tasks)
        deadline = None if timeout is None else time.monotonic() + timeout
        pending: dict[asyncio.Task, str] = {}
        results: dict[str, Any] = {}
        try:
            while True:
                self._run_async_check_timeout(deadline, tasks_snapshot, pending)
                self._run_async_cleanup_completed(tasks_snapshot, pending, results)
                submitted_any = self._run_async_submit_ready(tasks_snapshot, pending)
                if not pending:
                    if not any(t.state == "running" for t in tasks_snapshot.values()):
                        break
                    await asyncio.sleep(0.01)
                    continue
                if submitted_any:
                    await asyncio.sleep(0)
                    continue
                done = await self._run_async_wait_done(pending, deadline)
                self._run_async_process_done(done, pending, tasks_snapshot, results)
        except TaskTimeoutError:
            raise
        return results

    def _run_task(self, node: TaskNode, dep_results: list) -> Any:
        """实际执行任务（同步包装 _invoke，供外部同步场景使用）。"""
        try:
            return node.func(*dep_results)
        except Exception as e:
            logger.warning("任务 %s 失败: %s", node.name, e)
            raise

    def get_result(self, name: str) -> Any:
        with self._lock:
            t = self._tasks.get(name)
            if t is None:
                raise KeyError(name)
            if t.state == "failed":
                raise TaskExecutionError(str(t.exception)) from t.exception
            if t.state == "cancelled":
                raise TaskExecutionError(f"任务 {name} 被取消")
            return t.result

    def task_status(self, name: str) -> dict | None:
        with self._lock:
            t = self._tasks.get(name)
            if t is None:
                return None
            return {
                "name": t.name,
                "state": t.state,
                "deps": list(t.deps),
                "started_at": t.started_at,
                "finished_at": t.finished_at,
                "duration": (t.finished_at - t.started_at if t.finished_at else 0.0),
                "has_result": t.result is not None,
                "exception": str(t.exception) if t.exception else None,
            }

    def status(self) -> dict:
        with self._lock:
            states = {
                "pending": 0,
                "running": 0,
                "done": 0,
                "failed": 0,
                "cancelled": 0,
            }
            for t in self._tasks.values():
                states[t.state] = states.get(t.state, 0) + 1
            return {
                "max_workers": self._max_workers,
                "total_tasks": len(self._tasks),
                "states": states,
                "tasks": {n: t.state for n, t in self._tasks.items()},
            }

    def rollback_on_timeout(self, task_id: str) -> bool:
        """超时回滚：将指定任务及其下游未完成任务标记为 rolled_back。

        Args:
            task_id: 超时的任务 ID。

        Returns:
            True 如果回滚了任何任务。
        """
        with self._lock:
            target = self._tasks.get(task_id)
            if target is None:
                raise KeyError(task_id)
            rolled = False
            # 回滚超时任务本身
            if target.state in ("pending", "running"):
                target.state = "rolled_back"
                target.exception = TaskTimeoutError(f"任务 {task_id} 超时回滚")
                rolled = True
            # 回滚所有下游（依赖此任务的）pending 任务
            for t in self._tasks.values():
                if t.state == "pending" and task_id in t.deps:
                    t.state = "rolled_back"
                    t.exception = TaskTimeoutError(
                        f"依赖任务 {task_id} 超时，{t.name} 回滚"
                    )
                    rolled = True
            if rolled:
                logger.info("超时回滚完成: %s", task_id)
            return rolled

    def retry_with_backoff(
        self,
        task_id: str,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> bool:
        """指数退避重试失败的任务。

        Args:
            task_id: 要重试的任务 ID。
            max_retries: 最大重试次数（默认 3）。
            base_delay: 基础延迟秒数（默认 1.0）。

        Returns:
            True 如果重试成功。
        """
        with self._lock:
            node = self._tasks.get(task_id)
            if node is None:
                raise KeyError(task_id)
            if node.state != "failed":
                raise ValueError(
                    f"任务 {task_id} 状态为 {node.state}，只能重试 failed 任务"
                )

        last_exc = None
        for attempt in range(1, max_retries + 1):
            delay = base_delay * (2 ** (attempt - 1))
            logger.info(
                "重试任务 %s 第 %d/%d 次，等待 %.1fs",
                task_id,
                attempt,
                max_retries,
                delay,
            )
            time.sleep(delay)
            try:
                with self._lock:
                    dep_results = [self._tasks[d].result for d in node.deps]
                result = node.func(*dep_results)
                with self._lock:
                    node.state = "done"
                    node.result = result
                    node.exception = None
                    node.started_at = time.time()
                    node.finished_at = time.time()
                logger.info("任务 %s 重试成功 (第 %d 次)", task_id, attempt)
                return True
            except Exception as e:
                last_exc = e
                logger.warning("任务 %s 重试第 %d 次失败: %s", task_id, attempt, e)

        with self._lock:
            node.exception = last_exc
        raise TaskExecutionError(
            f"任务 {task_id} 重试 {max_retries} 次均失败"
        ) from last_exc

    def reset(self) -> None:
        with self._lock:
            for t in self._tasks.values():
                t.state = "pending"
                t.result = None
                t.exception = None
                t.started_at = 0.0
                t.finished_at = 0.0

    # ============== P1 新增：状态快照 ==============

    def snapshot(self) -> dict[str, Any]:
        """导出当前编排器状态快照。

        Returns:
            包含所有任务节点状态的字典，可用于跨会话恢复。
        """
        with self._lock:
            return {
                "max_workers": self._max_workers,
                "tasks": {
                    name: {
                        "name": t.name,
                        "state": t.state,
                        "deps": list(t.deps),
                        "started_at": t.started_at,
                        "finished_at": t.finished_at,
                        "result": t.result,
                        "exception": str(t.exception) if t.exception else None,
                    }
                    for name, t in self._tasks.items()
                },
            }

    def restore(self, snapshot_data: dict[str, Any]) -> None:
        """从快照恢复编排器状态。

        Args:
            snapshot_data: snapshot() 返回的字典。
        """
        with self._lock:
            self._max_workers = snapshot_data.get("max_workers", self._max_workers)
            self._executor = TaskExecutor(self._max_workers)
            for name, tdata in snapshot_data.get("tasks", {}).items():
                if name not in self._tasks:
                    self._tasks[name] = TaskNode(
                        name=tdata["name"],
                        func=lambda *a, **kw: None,
                        deps=tdata.get("deps", []),
                    )
                node = self._tasks[name]
                node.state = tdata.get("state", "pending")
                node.deps = tdata.get("deps", node.deps)
                node.started_at = tdata.get("started_at", 0.0)
                node.finished_at = tdata.get("finished_at", 0.0)
                node.result = tdata.get("result")
                exc_str = tdata.get("exception")
                node.exception = TaskExecutionError(exc_str) if exc_str else None

    def save_snapshot(self, path: str) -> None:
        """将状态快照保存到 JSON 文件。"""
        import os

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        data = self.snapshot()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    @classmethod
    def load_snapshot(cls, path: str) -> dict[str, Any]:
        """从 JSON 文件加载状态快照。"""
        import os

        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    # ============== P1 新增：Human-in-the-Loop ==============

    def register_approval_callback(
        self, task_name: str, callback: Callable[[TaskNode], bool]
    ) -> None:
        """注册人工审批回调。

        Args:
            task_name: 需要审批的任务名。
            callback: 审批函数，接收 TaskNode，返回 True(批准) / False(拒绝)。
        """
        self._approval_callbacks[task_name] = callback

    def approve(self, task_name: str) -> None:
        """人工批准任务，继续执行。"""
        node = self._paused_tasks.pop(task_name, None)
        if node is None:
            raise KeyError(f"任务 {task_name} 不在等待审批状态")
        node.state = "pending"
        logger.info("任务 %s 已人工批准", task_name)

    def reject(self, task_name: str) -> None:
        """人工拒绝任务，标记为 cancelled。"""
        node = self._paused_tasks.pop(task_name, None)
        if node is None:
            raise KeyError(f"任务 {task_name} 不在等待审批状态")
        node.state = "cancelled"
        logger.info("任务 %s 已人工拒绝", task_name)

    def _check_approval(self, node: TaskNode) -> bool:
        """检查任务是否需要人工审批。"""
        cb = self._approval_callbacks.get(node.name)
        if cb is None:
            return True
        approved = cb(node)
        if not approved:
            node.state = "paused"
            self._paused_tasks[node.name] = node
            logger.info("任务 %s 等待人工审批", node.name)
        return approved
