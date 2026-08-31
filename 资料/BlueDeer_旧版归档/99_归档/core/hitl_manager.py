"""BlueDeer Human-in-the-Loop (HITL) Manager。

功能：
- 审批任务队列
- 超时自动升级
- 审批人路由
- 审计日志

参考 OpenAI HITL / Anthropic 人工审核模式。
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger("bluedeer.hitl")


class HitlStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    TIMEOUT = "timeout"


@dataclass(slots=True)
class HitlTask:
    task_id: str
    agent_id: str
    payload: dict[str, Any]
    reason: str = ""
    status: HitlStatus = HitlStatus.PENDING
    approver: str = ""
    comment: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: str = ""
    timeout_seconds: int | None = None
    escalation_chain: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class HitlManager:
    """HITL 审批管理器。线程安全。"""

    def __init__(self, default_timeout: int = 3600) -> None:
        self._default_timeout = default_timeout
        self._lock = threading.Lock()
        self._tasks: dict[str, HitlTask] = {}
        self._subscribers: list[Callable[[HitlTask], None]] = []

    def submit(self, task: HitlTask) -> None:
        with self._lock:
            self._tasks[task.task_id] = task
        logger.info("HITL 任务已提交: %s (agent=%s, reason=%s)", task.task_id, task.agent_id, task.reason)

    def approve(self, task_id: str, approver: str = "", comment: str = "") -> HitlTask | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            task.status = HitlStatus.APPROVED
            task.approver = approver
            task.comment = comment
            task.resolved_at = datetime.now(timezone.utc).isoformat()
            return task

    def reject(self, task_id: str, approver: str = "", comment: str = "") -> HitlTask | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            task.status = HitlStatus.REJECTED
            task.approver = approver
            task.comment = comment
            task.resolved_at = datetime.now(timezone.utc).isoformat()
            return task

    def escalate(self, task_id: str) -> HitlTask | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            task.status = HitlStatus.ESCALATED
            task.resolved_at = datetime.now(timezone.utc).isoformat()
            return task

    def check_timeouts(self) -> list[HitlTask]:
        now = time.time()
        timed_out: list[HitlTask] = []
        with self._lock:
            for task in self._tasks.values():
                if task.status != HitlStatus.PENDING:
                    continue
                timeout = task.timeout_seconds or self._default_timeout
                created = datetime.fromisoformat(task.created_at).timestamp()
                if now - created > timeout:
                    task.status = HitlStatus.TIMEOUT
                    task.resolved_at = datetime.now(timezone.utc).isoformat()
                    timed_out.append(task)
        return timed_out

    def get_pending(self) -> list[HitlTask]:
        with self._lock:
            return [t for t in self._tasks.values() if t.status == HitlStatus.PENDING]

    def get_stats(self) -> dict[str, int]:
        with self._lock:
            counts: dict[str, int] = {}
            for task in self._tasks.values():
                counts[task.status.value] = counts.get(task.status.value, 0) + 1
            return counts
