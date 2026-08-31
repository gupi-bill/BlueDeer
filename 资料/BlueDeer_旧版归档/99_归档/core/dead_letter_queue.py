"""BlueDeer Dead Letter Queue: captures and stores permanently failed tasks."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("bluedeer.dlq")


@dataclass
class DeadLetterEntry:
    task_id: str
    agent_id: str
    task_type: str
    payload: dict[str, Any]
    error: str
    attempts: int
    failed_at: float = field(default_factory=time.time)
    trace_id: str = ""


class DeadLetterQueue:
    """Stores tasks that failed after all retry attempts."""

    def __init__(self, max_size: int = 1000) -> None:
        self._entries: list[DeadLetterEntry] = []
        self._max_size = max_size
        self._lock = threading.Lock()

    def enqueue(self, entry: DeadLetterEntry) -> None:
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max_size:
                self._entries = self._entries[-self._max_size :]
        logger.warning(
            "DLQ enqueued task %s (agent=%s, error=%s, attempts=%d)",
            entry.task_id,
            entry.agent_id,
            entry.error,
            entry.attempts,
        )

    def dequeue(self) -> DeadLetterEntry | None:
        with self._lock:
            if not self._entries:
                return None
            return self._entries.pop(0)

    def peek(self, count: int = 10) -> list[DeadLetterEntry]:
        with self._lock:
            return list(self._entries[-count:])

    def get_by_agent(self, agent_id: str) -> list[DeadLetterEntry]:
        with self._lock:
            return [e for e in self._entries if e.agent_id == agent_id]

    def clear(self) -> int:
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
            return count

    def size(self) -> int:
        with self._lock:
            return len(self._entries)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            by_agent: dict[str, int] = {}
            for e in self._entries:
                by_agent[e.agent_id] = by_agent.get(e.agent_id, 0) + 1
            return {
                "total": len(self._entries),
                "by_agent": by_agent,
                "max_size": self._max_size,
            }


_global_dlq: DeadLetterQueue | None = None
_dlq_lock = threading.Lock()


def get_dlq() -> DeadLetterQueue:
    global _global_dlq
    if _global_dlq is None:
        with _dlq_lock:
            if _global_dlq is None:
                _global_dlq = DeadLetterQueue()
    return _global_dlq


__all__ = ["DeadLetterEntry", "DeadLetterQueue", "get_dlq"]
