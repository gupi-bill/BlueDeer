"""BlueDeer 核心数据结构：Message、Task、TaskResult、TokenUsage、TaskStatus。

集中定义全局常量，避免各模块重复定义。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

# ============================================================
# 全局常量
# ============================================================

RESULT_TOPIC = "harness.result"

# ============================================================
# 工具函数
# ============================================================


def _generate_id() -> str:
    """生成唯一 ID。"""
    return uuid.uuid4().hex[:12]


class TaskStatus(Enum):
    """任务生命周期状态。

    流转：PENDING -> RUNNING -> COMPLETED | FAILED | CANCELLED
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    #: SUCCESS 是 COMPLETED 的别名（大量调用方用 SUCCESS 判断成功）
    SUCCESS = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class TokenUsage:
    """单次调用的 Token 消耗记录。"""

    tokens_in: int = 0
    tokens_out: int = 0

    @property
    def total(self) -> int:
        return self.tokens_in + self.tokens_out


@dataclass(slots=True)
class Message:
    """消息基类，所有通过事件总线传递的消息均继承此类。"""

    trace_id: str = field(default_factory=_generate_id)
    timestamp: float = field(default_factory=time.time)


@dataclass(slots=True)
class Task(Message):
    """任务消息，由 Harness 下发给 Agent。

    Attributes:
        id: 任务唯一标识。
        type: 任务类型（code / architecture / batch / voice 等），用于模型路由。
        payload: 任务负载，包含具体任务内容与参数。
        assignee: 指派 Agent 的 ID。
        priority: 优先级，数值越大越优先。
        context_ref: 上下文引用键，用于从 ContextManager 获取关联上下文。
        status: 任务生命周期状态。
        created_at: 创建时间戳。
        started_at: 开始执行时间戳（None 表示未开始）。
        completed_at: 完成时间戳（None 表示未完成）。
    """

    id: str = field(default_factory=_generate_id)
    type: str = "general"
    payload: dict[str, Any] = field(default_factory=dict)
    assignee: str = ""
    priority: int = 0
    context_ref: str = ""
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None

    @property
    def elapsed(self) -> float:
        """任务已运行时间（秒）。未开始返回 0。"""
        if self.started_at is None:
            return 0.0
        end = self.completed_at if self.completed_at is not None else time.time()
        return end - self.started_at

    def to_dict(self) -> dict:
        """序列化为 JSON 可用的 dict。"""
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @staticmethod
    def from_dict(data: dict) -> Task:
        """从 dict 反序列化 Task。"""
        status_str = data.pop("status", "pending")
        task = Task(**data)
        task.status = TaskStatus(status_str)
        return task


@dataclass(slots=True)
class TaskResult(Message):
    """任务执行结果，由 Agent 返回给 Harness。

    Attributes:
        task_id: 对应的 Task.id。
        status: 执行状态（COMPLETED / FAILED）。
        output: 执行输出内容。
        error: 失败时的错误信息。
        token_usage: 本次任务消耗的 Token 统计。
    """

    task_id: str = ""
    status: TaskStatus = TaskStatus.COMPLETED
    output: Any = None
    error: str | None = None
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    agent_id: str = ""
    task_type: str = "general"
