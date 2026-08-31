"""BlueDeer 记忆流水线：extract → consolidate → store → retrieve。

参考 Mem0 / Zep 设计，适配 BlueDeer 离线优先 + 纯标准库约束。
"""

from __future__ import annotations

import re
import time
import uuid

from memory_archive.schemas import MemoryEntry, MemoryType, RetrievalResult
from memory_archive.store import MemoryStore


class MemoryPipeline:
    """记忆流水线。

    职责：
    1. extract：从原始文本中提取可持久化记忆（去噪、结构化）
    2. consolidate：合并相似记忆，解决冲突
    3. store：写入 MemoryStore
    4. retrieve：按 Agent / 类型 / 语义检索
    """

    def __init__(self, data_dir: str = "memory_archive/data") -> None:
        self._store = MemoryStore(data_dir=data_dir)
        self._similarity_threshold = 0.85

    def extract(
        self,
        agent_id: str,
        raw_text: str,
        memory_type: MemoryType | str = MemoryType.EPISODIC,
        importance: float = 0.5,
    ) -> MemoryEntry | None:
        """从原始文本提取一条记忆。

        简单实现：按句号/换行拆分，取非空句；去首尾空白。
        生产环境可替换为 LLM-based extraction。
        """
        sentences = [s.strip() for s in re.split(r"[。\n.!?]", raw_text) if s.strip()]
        if not sentences:
            return None
        content = " | ".join(sentences[:3])
        mem = MemoryEntry(
            id=uuid.uuid4().hex[:16],
            agent_id=agent_id,
            memory_type=MemoryType(memory_type.value if isinstance(memory_type, MemoryType) else memory_type),
            content=content,
            importance=importance,
        )
        return mem

    def consolidate(self, new_entry: MemoryEntry) -> list[MemoryEntry]:
        """合并相似记忆。

        策略：
        - 同 agent + 同 memory_type 下，检索 top-1 相似记忆
        - 若相似度 > threshold，标记旧记忆为 superseded，写入新记忆
        - 否则直接写入
        """
        existing: list[MemoryEntry] = []
        candidates = self._store.search(new_entry.content, top_k=3)
        for r in candidates:
            if r.score < self._similarity_threshold:
                continue
            if r.entry.agent_id == new_entry.agent_id and r.entry.memory_type == new_entry.memory_type:
                existing.append(r.entry)
        return existing

    def store(self, entry: MemoryEntry) -> None:
        self._store.add(entry)

    def retrieve(
        self,
        agent_id: str,
        query: str,
        top_k: int = 5,
        memory_types: list[MemoryType] | None = None,
    ) -> list[RetrievalResult]:
        """检索记忆。

        优先语义检索，再按 memory_types 过滤。
        """
        results = self._store.search(query, top_k=top_k * 2)
        filtered = [r for r in results if r.entry.agent_id == agent_id]
        if memory_types:
            allowed = {m.value for m in memory_types}
            filtered = [r for r in filtered if r.entry.memory_type.value in allowed]
        return filtered[:top_k]

    def remember(
        self,
        agent_id: str,
        raw_text: str,
        memory_type: MemoryType | str = MemoryType.EPISODIC,
        importance: float = 0.5,
    ) -> MemoryEntry | None:
        """extract + consolidate + store 一体化接口。"""
        entry = self.extract(agent_id, raw_text, memory_type, importance)
        if entry is None:
            return None
        existing = self.consolidate(entry)
        for old in existing:
            old.metadata["superseded_by"] = entry.id
            old.updated_at = time.time()
        self.store(entry)
        return entry

    def remember_reasoning(
        self,
        agent_id: str,
        decision: str,
        alternatives: list[str],
        rationale: str,
        outcome: str = "",
    ) -> MemoryEntry | None:
        """记录推理决策过程（为什么选 A 而非 B）。

        Args:
            agent_id: 员工 ID。
            decision: 最终决策。
            alternatives: 备选方案列表。
            rationale: 决策理由。
            outcome: 执行结果（可选）。
        """
        content = (
            f"决策: {decision}\n"
            f"备选: {', '.join(alternatives)}\n"
            f"理由: {rationale}\n"
            f"结果: {outcome}"
        )
        return self.remember(agent_id, content, MemoryType.REASONING, importance=0.8)

    def forget(self, memory_id: str) -> bool:
        return self._store.delete(memory_id)

    def persist(self) -> None:
        self._store.persist()

    def load(self) -> None:
        self._store.load()

    @property
    def count(self) -> int:
        return self._store.count
