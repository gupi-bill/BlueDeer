"""BlueDeer 任务看板（008-3 拆分自 core/harness.py）。

TaskBoardMixin 承载任务看板数据与聚合/持久化逻辑：
- _task_board: dict[task_id, TaskResult] 已完成结果看板
- _pending: dict[task_id, Task] 待执行/等待前置任务
- _in_flight: dict[agent_id, int] 在途任务计数（负载均衡依据）
- _reallocate_count: dict[task_id, int] 重分配计数（防无限重试）
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from core.task import TaskResult, TaskStatus, TokenUsage

logger = logging.getLogger("bluedeer.task_board")


class TaskBoardMixin:
    """任务看板：数据 + 汇总 + 清理 + 持久化。"""

    # ---- 数据访问 ----

    def _board_init(self) -> None:
        """初始化看板字段（Harness.__init__ 调用）。"""
        self._task_board: dict[str, TaskResult] = {}
        self._pending: dict[str, Any] = {}
        self._in_flight: dict[str, int] = {}
        self._reallocate_count: dict[str, int] = {}

    def board_record_result(self, result: TaskResult) -> None:
        """登记结果到看板。"""
        self._task_board[result.task_id] = result

    def board_pending(self) -> dict[str, Any]:
        return self._pending

    def board_in_flight(self) -> dict[str, int]:
        return self._in_flight

    def in_flight_add(self, agent_id: str) -> None:
        """在途计数 +1。"""
        self._in_flight[agent_id] = self._in_flight.get(agent_id, 0) + 1

    def _decrement_in_flight(self, agent_id: str) -> None:
        """递减 Agent 在途计数（不低于 0）。"""
        current = self._in_flight.get(agent_id, 0)
        if current <= 1:
            self._in_flight.pop(agent_id, None)
        else:
            self._in_flight[agent_id] = current - 1

    # ---- 汇总 ----

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

        achievement_progress = {}
        if self._reward_system:
            for aid in self._reward_system.leaderboard_agent_ids():
                achievement_progress[aid] = self._reward_system.achievement_progress(
                    aid
                )

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
            "token_stats": (
                self._token_auditor.get_total_stats() if self._token_auditor else {}
            ),
            "token_savings": (
                self._token_auditor.get_savings()
                if self._token_auditor
                else {"total_saved": 0}
            ),
            "achievement_progress": achievement_progress,
            "dag": self._dag.topological_sort() if self._dag else [],
            "dag_blocked": (
                [
                    tid
                    for tid in self._pending
                    if self._dag is not None
                    and self._dag.has_node(tid)
                    and not self._dag.ready(
                        tid,
                        {
                            t
                            for t, r in self._task_board.items()
                            if r.status == TaskStatus.SUCCESS
                        },
                    )
                ]
                if self._dag
                else []
            ),
        }

    # ---- 清理 ----

    def cleanup_old_tasks(
        self, max_age: float = 3600.0, now: float | None = None
    ) -> int:
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
            tid for tid, r in self._task_board.items() if now - r.timestamp > max_age
        ]
        for tid in stale_ids:
            del self._task_board[tid]
            self._reallocate_count.pop(tid, None)
        if stale_ids:
            logger.info("清理过期任务记录: %d 条", len(stale_ids))
        return len(stale_ids)

    # ---- 持久化 ----

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

    def _load_state_from_db(self) -> int:
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
                    from core.task import Task

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
        return loaded

    def _load_state_from_json(self, path: str) -> int:
        count = 0
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
            from core.task import Task

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

    def load_state(self, path: str = "data/task_state.json") -> int:
        """从数据库恢复任务看板（优先），找不到则回退 JSON。

        Returns:
            恢复的任务记录数。
        """
        loaded = self._load_state_from_db()
        if loaded > 0:
            logger.info("任务状态已从数据库恢复 (%d 条)", loaded)
            return loaded
        if not os.path.exists(path):
            logger.info("无存档文件可恢复: %s", path)
            return 0
        return self._load_state_from_json(path)
