"""BlueDeer 并发任务编排器：DAG 依赖 + 并行执行 + 汇合 + 超时。

evolution（并发维度 - R179）：
- 工作流经常是多步且依赖复杂的：A→B、A→C、B+C→D
- 串行执行慢，盲目并行又会破坏依赖
- DAG 编排：声明任务和依赖，按拓扑并行执行无依赖的任务
- 支持失败传播、超时、取消
"""
from __future__ import annotations
import logging
import threading
import time
from concurrent.futures import (
    ThreadPoolExecutor, Future, as_completed, TimeoutError as FutureTimeout,
)
from typing import Any, Callable

from core.exceptions import TaskDependencyError, TaskExecutionError, TaskTimeoutError

logger = logging.getLogger("bluedeer.orch")


class TaskNode:
    """任务节点。"""
    __slots__ = ("name", "func", "deps", "result", "exception", "state",
                 "started_at", "finished_at")

    def __init__(self, name: str, func: Callable, deps: list[str] | None = None):
        self.name = name
        self.func = func
        self.deps = list(deps) if deps else []
        self.result: Any = None
        self.exception: Exception | None = None
        self.state = "pending"  # pending/running/done/failed/cancelled
        self.started_at = 0.0
        self.finished_at = 0.0


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

    def add_task(
        self,
        name: str,
        func: Callable,
        deps: list[str] | None = None,
    ) -> "TaskOrchestrator":
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

        def visit(node):
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
        return any(self._tasks[d].state in ("failed", "cancelled")
                   for d in node.deps)

    def run(self, timeout: float = None) -> dict[str, Any]:
        """运行所有任务。返回 {name: result}。

        - 按拓扑并行执行无依赖的任务
        - 依赖任务失败时，下游任务被取消
        - 超时取消所有未完成任务
        """
        with self._lock:
            self._validate()
            tasks_snapshot = dict(self._tasks)

        end = None if timeout is None else time.time() + timeout
        completed_futures: dict[Future, str] = {}
        results: dict[str, Any] = {}
        any_failed = False

        with ThreadPoolExecutor(max_workers=self._max_workers) as ex:
            try:
                while True:
                    # 检查超时
                    if end is not None and time.time() >= end:
                        # 取消所有 pending
                        for t in self._tasks.values():
                            if t.state == "pending":
                                t.state = "cancelled"
                        raise TaskTimeoutError(f"编排超时 {timeout}s")

                    # 找就绪任务
                    ready = self._get_ready()
                    submitted_any = False
                    for name in ready:
                        t = self._tasks[name]
                        # 检查依赖失败
                        if self._has_failed_deps(t):
                            t.state = "cancelled"
                            continue
                        # 收集依赖结果作为参数
                        dep_results = [self._tasks[d].result for d in t.deps]
                        t.state = "running"
                        t.started_at = time.time()
                        fut = ex.submit(self._run_task, t, dep_results)
                        completed_futures[fut] = name
                        submitted_any = True

                    if not submitted_any:
                        # 没有可提交的：要么全完成，要么全失败/取消
                        pending = [t for t in self._tasks.values()
                                   if t.state == "pending"]
                        if not pending and not completed_futures:
                            break
                        if not pending and completed_futures:
                            # 等待未完成的 future
                            pass

                    # 等待至少一个完成
                    if completed_futures:
                        if end is not None:
                            remaining = end - time.time()
                            if remaining <= 0:
                                continue
                        else:
                            remaining = None
                        # 用 as_completed 等一个
                        done_set = set()
                        try:
                            for fut in list(as_completed(
                                completed_futures.keys(),
                                timeout=remaining,
                            )):
                                done_set.add(fut)
                                name = completed_futures.pop(fut)
                                t = self._tasks[name]
                                t.finished_at = time.time()
                                if fut.exception() is not None:
                                    t.exception = fut.exception()
                                    t.state = "failed"
                                    any_failed = True
                                else:
                                    t.result = fut.result()
                                    t.state = "done"
                                    results[name] = t.result
                                break  # 处理一个就回到循环重新检查 ready
                        except FutureTimeout:
                            # as_completed 超时
                            if end is not None and time.time() >= end:
                                for t in self._tasks.values():
                                    if t.state in ("pending", "running"):
                                        t.state = "cancelled"
                                raise TaskTimeoutError(f"编排超时 {timeout}s")
                            continue
                    else:
                        # 没有 future 在跑，检查是否还有 pending
                        pending = [t for t in self._tasks.values()
                                   if t.state == "pending"]
                        if pending and all(self._has_failed_deps(t) for t in pending):
                            # 全是依赖失败的 pending
                            for t in pending:
                                t.state = "cancelled"
                        if not pending:
                            break
            except TaskTimeoutError:
                raise

        return results

    def _run_task(self, node: TaskNode, dep_results: list) -> Any:
        """实际执行任务（在工作线程中）。"""
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
                "duration": (t.finished_at - t.started_at
                            if t.finished_at else 0.0),
                "has_result": t.result is not None,
                "exception": str(t.exception) if t.exception else None,
            }

    def status(self) -> dict:
        with self._lock:
            states = {"pending": 0, "running": 0, "done": 0,
                      "failed": 0, "cancelled": 0}
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
                raise ValueError(f"任务 {task_id} 状态为 {node.state}，只能重试 failed 任务")

        last_exc = None
        for attempt in range(1, max_retries + 1):
            delay = base_delay * (2 ** (attempt - 1))
            logger.info("重试任务 %s 第 %d/%d 次，等待 %.1fs", task_id, attempt, max_retries, delay)
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
        raise TaskExecutionError(f"任务 {task_id} 重试 {max_retries} 次均失败") from last_exc

    def reset(self) -> None:
        with self._lock:
            for t in self._tasks.values():
                t.state = "pending"
                t.result = None
                t.exception = None
                t.started_at = 0.0
                t.finished_at = 0.0
