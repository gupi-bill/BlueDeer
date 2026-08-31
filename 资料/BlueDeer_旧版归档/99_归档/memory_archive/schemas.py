"""BlueDeer 记忆系统 schemas：记忆条目 / 记忆类型 / 检索结果。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MemoryType(str, Enum):
    """记忆类型。"""

    EPISODIC = "episodic"  # 情节记忆：具体交互事件
    SEMANTIC = "semantic"  # 语义记忆：事实性知识
    PROCEDURAL = "procedural"  # 程序记忆：技能/偏好
    REASONING = "reasoning"  # 推理记忆：决策过程
    WORKING = "working"  # 工作记忆：当前任务上下文


@dataclass
class MemoryEntry:
    """单条记忆条目。"""

    id: str
    agent_id: str
    memory_type: MemoryType
    content: str
    embedding: dict[str, float] = field(default_factory=dict)
    importance: float = 0.5
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    access_count: int = 0
    last_accessed_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    related_ids: list[str] = field(default_factory=list)

    def touch(self) -> None:
        self.access_count += 1
        self.last_accessed_at = time.time()


@dataclass
class RetrievalResult:
    """检索结果。"""

    entry: MemoryEntry
    score: float
