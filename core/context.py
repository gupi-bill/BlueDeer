from __future__ import annotations

import threading
import time
from typing import Any

from core.task import Task


class ContextManager:
    def __init__(self, task_ttl: float = 300.0) -> None:
        self._global: dict[str, Any] = {}
        self._agent: dict[str, dict[str, Any]] = {}
        self._task: dict[str, dict[str, Any]] = {}
        self._task_ttl = task_ttl
        self._task_ts: dict[str, float] = {}
        self._nested: dict[str, list[dict[str, Any]]] = {}
        self._lock = threading.RLock()

    def set_global(self, key: str, value: Any) -> None:
        self._global[key] = value

    def get_global(self, key: str, default: Any = None) -> Any:
        return self._global.get(key, default)

    def set_agent(self, agent_id: str, key: str, value: Any) -> None:
        with self._lock:
            if agent_id not in self._agent:
                self._agent[agent_id] = {}
            self._agent[agent_id][key] = value

    def get_agent(self, agent_id: str, key: str, default: Any = None) -> Any:
        return self._agent.get(agent_id, {}).get(key, default)

    def set_task(self, task_id: str, key: str, value: Any) -> None:
        with self._lock:
            if task_id not in self._task:
                self._task[task_id] = {}
            self._task[task_id][key] = value
            self._task_ts[task_id] = time.monotonic()

    def get_task(self, task_id: str, key: str, default: Any = None) -> Any:
        self._expire_task(task_id)
        return self._task.get(task_id, {}).get(key, default)

    def clear_task(self, task_id: str) -> None:
        with self._lock:
            self._task.pop(task_id, None)
            self._task_ts.pop(task_id, None)
            self._nested.pop(task_id, None)

    def touch_task(self, task_id: str) -> None:
        with self._lock:
            self._task_ts[task_id] = time.monotonic()

    def _expire_task(self, task_id: str) -> bool:
        ts = self._task_ts.get(task_id)
        if ts and time.monotonic() - ts > self._task_ttl:
            self.clear_task(task_id)
            return True
        return False

    def push_nested(self, task_id: str, scope: str, ctx: dict[str, Any]) -> None:
        with self._lock:
            self._nested.setdefault(task_id, []).append({scope: ctx})

    def pop_nested(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            stack = self._nested.get(task_id)
            if stack:
                return stack.pop()
            return None

    def get_nested(self, task_id: str) -> list[dict[str, Any]]:
        return list(self._nested.get(task_id, []))

    def clear_expired(self) -> int:
        with self._lock:
            now = time.monotonic()
            expired = [
                tid for tid, ts in self._task_ts.items() if now - ts > self._task_ttl
            ]
            for tid in expired:
                self.clear_task(tid)
            return len(expired)

    def get_context(self, agent_id: str, task: Task) -> dict[str, Any]:
        self._expire_task(task.id)
        merged: dict[str, Any] = {}
        merged.update(self._global)
        merged.update(self._agent.get(agent_id, {}))
        merged.update(self._task.get(task.id, {}))
        for n in self._nested.get(task.id, []):
            merged.update(n)
        return merged
