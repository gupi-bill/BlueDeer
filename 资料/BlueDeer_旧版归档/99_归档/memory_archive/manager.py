"""BlueDeer 记忆管理器：独立于 Agent 生命周期，按需加载/持久化。

设计原则：
- 不侵入 BaseAgent 生命周期（不修改 on_start / on_stop）
- 由 Harness 或显式调用方控制 load / persist 时机
- 支持后台自动 consolidation 线程
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from memory_archive.pipeline import MemoryPipeline
from memory_archive.schemas import MemoryEntry, MemoryType, RetrievalResult

logger = logging.getLogger("bluedeer.memory")


class MemoryManager:
    """记忆管理器（单例）。

    职责：
    1. 为每个 Agent 维护独立 MemoryPipeline
    2. 提供全局 load / persist / clear 接口
    3. 可选后台 consolidation 线程（定期合并相似记忆）

    使用方式：
        mgr = MemoryManager(data_dir="memory_archive/data")
        mgr.load_all()          # 显式加载所有 Agent 记忆
        entry = mgr.remember("deer", "xxx", MemoryType.SEMANTIC)
        results = mgr.recall("deer", "query")
        mgr.persist_all()       # 显式持久化
    """

    _instance: MemoryManager | None = None

    def __init__(self, data_dir: str = "memory_archive/data", auto_consolidate: bool = False) -> None:
        self._data_dir = data_dir
        self._pipelines: dict[str, MemoryPipeline] = {}
        self._lock = threading.RLock()
        self._consolidate_enabled = auto_consolidate
        self._consolidate_thread: threading.Thread | None = None
        self._consolidate_stop = threading.Event()

    @classmethod
    def get_instance(cls, data_dir: str = "memory_archive/data") -> MemoryManager:
        if cls._instance is None:
            cls._instance = cls(data_dir=data_dir)
        return cls._instance

    def get_pipeline(self, agent_id: str) -> MemoryPipeline:
        with self._lock:
            if agent_id not in self._pipelines:
                self._pipelines[agent_id] = MemoryPipeline(data_dir=self._data_dir)
            return self._pipelines[agent_id]

    def load(self, agent_id: str) -> None:
        pipe = self.get_pipeline(agent_id)
        try:
            pipe.load()
            logger.info("记忆加载: agent=%s, 当前%d条", agent_id, pipe.count)
        except Exception as e:
            logger.warning("记忆加载失败: agent=%s, %s", agent_id, e)

    def load_all(self) -> None:
        with self._lock:
            agents = list(self._pipelines.keys())
        for agent_id in agents:
            self.load(agent_id)

    def persist(self, agent_id: str) -> None:
        pipe = self.get_pipeline(agent_id)
        try:
            pipe.persist()
            logger.info("记忆持久化: agent=%s, 共%d条", agent_id, pipe.count)
        except Exception as e:
            logger.warning("记忆持久化失败: agent=%s, %s", agent_id, e)

    def persist_all(self) -> None:
        with self._lock:
            agents = list(self._pipelines.keys())
        for agent_id in agents:
            self.persist(agent_id)

    def remember(
        self,
        agent_id: str,
        raw_text: str,
        memory_type: MemoryType | str = MemoryType.EPISODIC,
        importance: float = 0.5,
    ) -> MemoryEntry | None:
        pipe = self.get_pipeline(agent_id)
        return pipe.remember(agent_id, raw_text, memory_type, importance)

    def recall(
        self,
        agent_id: str,
        query: str,
        top_k: int = 5,
        memory_types: list[MemoryType] | None = None,
    ) -> list[RetrievalResult]:
        pipe = self.get_pipeline(agent_id)
        return pipe.retrieve(agent_id, query, top_k=top_k, memory_types=memory_types)

    def remember_reasoning(
        self,
        agent_id: str,
        decision: str,
        alternatives: list[str],
        rationale: str,
        outcome: str = "",
    ) -> MemoryEntry | None:
        pipe = self.get_pipeline(agent_id)
        return pipe.remember_reasoning(agent_id, decision, alternatives, rationale, outcome)

    def forget(self, agent_id: str, memory_id: str) -> bool:
        pipe = self.get_pipeline(agent_id)
        return pipe.forget(memory_id)

    def get_stats(self, agent_id: str) -> dict[str, Any]:
        pipe = self.get_pipeline(agent_id)
        return {
            "agent_id": agent_id,
            "count": pipe.count,
            "types": {mtype.value: len(pipe._store.get_by_type(mtype)) for mtype in MemoryType},
        }

    def start_auto_consolidate(self, interval: float = 300.0) -> None:
        self._consolidate_enabled = True
        self._consolidate_stop.clear()
        self._consolidate_thread = threading.Thread(
            target=self._consolidate_loop,
            args=(interval,),
            daemon=True,
        )
        self._consolidate_thread.start()
        logger.info("自动 consolidation 线程已启动（间隔 %.0fs）", interval)

    def stop_auto_consolidate(self) -> None:
        self._consolidate_stop.set()
        if self._consolidate_thread is not None:
            self._consolidate_thread.join(timeout=5.0)
        self._consolidate_enabled = False
        logger.info("自动 consolidation 线程已停止")

    def _consolidate_loop(self, interval: float) -> None:
        while not self._consolidate_stop.wait(interval):
            try:
                with self._lock:
                    agents = list(self._pipelines.keys())
                for agent_id in agents:
                    pipe = self._pipelines[agent_id]
                    before = pipe.count
                    pipe._store._save_vector_store()
                    after = pipe.count
                    logger.debug("consolidation: agent=%s, 记忆数=%d", agent_id, after)
            except Exception as e:
                logger.warning("consolidation 异常: %s", e)
