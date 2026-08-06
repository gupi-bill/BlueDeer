"""LangGraph-style graph state-machine agent runtime.

核心原语：
    - StateGraph：状态机图
    - Node：处理节点
    - Edge：状态转换边
    - Checkpoint：持久化检查点

融合自 LangGraph 设计：
- 状态为中心
- 图结构工作流
- 持久化记忆
- 人机协同
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("bluedeer.langgraph")

__all__ = ["NodeFn", "State", "StateGraph"]


@dataclass
class State:
    data: dict = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value


NodeFn = Callable[[State], State]


class StateGraph:
    """LangGraph 风格状态图。"""

    def __init__(
        self,
        initial_state: State | None = None,
        checkpoint_path: str | None = None,
    ):
        self._nodes: dict[str, NodeFn] = {}
        self._edges: dict[str, str] = {}
        self._conditional: dict[str, Callable[[State], str]] = {}
        self._state = initial_state or State()
        self._entry_point: str | None = None
        self._checkpoints: list[dict] = []
        self._checkpoint_path = checkpoint_path
        if checkpoint_path:
            self.load(checkpoint_path)

    def add_node(self, name: str, fn: NodeFn) -> None:
        self._nodes[name] = fn

    def add_edge(self, from_node: str, to_node: str) -> None:
        self._edges[from_node] = to_node

    def add_conditional_edge(
        self, from_node: str, router: Callable[[State], str]
    ) -> None:
        self._conditional[from_node] = router

    def set_entry_point(self, node: str) -> None:
        self._entry_point = node

    def checkpoint(self) -> dict:
        snap = {
            "state": dict(self._state.data),
            "checkpoints": len(self._checkpoints) + 1,
        }
        self._checkpoints.append(snap)
        if self._checkpoint_path:
            self.save(self._checkpoint_path)
        return snap

    def save(self, path: str | None = None) -> None:
        """持久化当前状态与全部检查点到磁盘（JSON）。"""
        path = path or self._checkpoint_path
        if not path:
            raise ValueError("checkpoint_path not configured")
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        payload = {
            "state": dict(self._state.data),
            "checkpoints": self._checkpoints,
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        if self._checkpoint_path is None:
            self._checkpoint_path = path

    def load(self, path: str | None = None) -> bool:
        """从磁盘恢复检查点；文件不存在或损坏时返回 False。"""
        path = path or self._checkpoint_path
        if not path or not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, ValueError):
            logger.warning("checkpoint load failed: %s", path)
            return False
        self._state = State(data=dict(payload.get("state", {})))
        self._checkpoints = list(payload.get("checkpoints", []))
        self._checkpoint_path = path
        return True

    @property
    def checkpoints(self) -> list[dict]:
        return list(self._checkpoints)

    def run(self, steps: int = 20) -> State:
        if not self._entry_point:
            raise RuntimeError("entry_point not set")
        current = self._entry_point
        for _ in range(steps):
            if current not in self._nodes:
                break
            node_fn = self._nodes[current]
            self._state = node_fn(self._state)
            self.checkpoint()
            if current in self._conditional:
                current = self._conditional[current](self._state)
            elif current in self._edges:
                current = self._edges[current]
            else:
                break
        return self._state
