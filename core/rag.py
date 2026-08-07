"""BlueDeer RAG 检索增强层：分层知识库 + 跨岗位定向检索。"""

from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import logging
import re
from dataclasses import dataclass
from typing import Any

from core.config import get_config
from vector_db.persistence import load_from_disk, save_to_disk
from vector_db.vector_store import SearchResult, VectorStore

logger = logging.getLogger("bluedeer.rag")

# 知识库层极
SCOPE_GLOBAL = "global"
SCOPE_AGENT = "agent"
SCOPE_TASK = "task"


@dataclass
class FusedResult:
    """多路召回融合结果。"""

    id: str
    text: str
    metadata: dict[str, Any]
    vector_score: float = 0.0
    keyword_score: float = 0.0
    kg_score: float = 0.0
    ensemble_score: float = 0.0


class RAGSystem:
    """RAG 检索增强系统。

    管理三层知识库：
    - 全局公共库：项目规范、开发规范、角色档案（所有 Agent 共享）
    - 岗位私有库：各员工历史任务方案、代码模板（按 agent_id 隔离）
    - 临时任务库：单次任务临时素材（任务完成后清理）

    支持跨层检索：合并多层结果后按相似度排序。
    检索失败不阻塞主链路（catch + 日志 + 返回空列表）。
    """

    def __init__(self, db_root: str | None = None) -> None:
        self._db_root = db_root if db_root is not None else get_config().db_root
        # 缓存已加载的 VectorStore
        self._stores: dict[str, VectorStore] = {}

    def _get_store(self, scope: str, sub_id: str = "") -> VectorStore:
        """获取指定层的 VectorStore（带缓存）。"""
        key = f"{scope}/{sub_id}" if sub_id else scope
        if key in self._stores:
            return self._stores[key]

        path = self._get_path(scope, sub_id)
        store = load_from_disk(path)
        self._stores[key] = store
        return store

    def _get_path(self, scope: str, sub_id: str) -> str:
        """获取持久化文件路径。"""
        if scope == SCOPE_GLOBAL:
            return f"{self._db_root}/global.json"
        elif scope == SCOPE_AGENT:
            return f"{self._db_root}/agent/{sub_id}.json"
        elif scope == SCOPE_TASK:
            return f"{self._db_root}/task/{sub_id}.json"
        else:
            return f"{self._db_root}/{scope}.json"

    def _save_store(self, scope: str, sub_id: str = "") -> None:
        """持久化存储。"""
        key = f"{scope}/{sub_id}" if sub_id else scope
        store = self._stores.get(key)
        if store:
            path = self._get_path(scope, sub_id)
            save_to_disk(store, path)

    def ingest(
        self,
        scope: str,
        id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
        sub_id: str = "",
        persist: bool = True,
    ) -> None:
        """向指定层注入知识。

        Args:
            scope: 知识库层（global / agent / task）。
            id: 知识条目 ID。
            text: 知识文本。
            metadata: 附加元数据。
            sub_id: 岗位 ID（scope=agent 时）或任务 ID（scope=task 时）。
            persist: 是否立即持久化。
        """
        try:
            store = self._get_store(scope, sub_id)
            store.insert(id, text, metadata)
            if persist:
                self._save_store(scope, sub_id)
            logger.info("RAG 注入: scope=%s, id=%s, sub_id=%s", scope, id, sub_id)
        except Exception as e:
            logger.error("RAG 注入失败: %s", e)

    def retrieve(
        self,
        query: str,
        scope: str,
        sub_id: str = "",
        top_k: int = 2,
        confidence_threshold: float = 0.0,
    ) -> list[SearchResult]:
        """从指定层检索，支持置信度过滤。

        Args:
            query: 查询文本。
            scope: 知识库层。
            sub_id: 岗位 ID 或任务 ID。
            top_k: 返回前 K 个结果。
            confidence_threshold: 置信度阈值，低于此值的分结果被过滤（默认 0.0 即不过滤）。

        Returns:
            检索结果列表（附置信度标签）。失败时返回空列表。
        """
        try:
            store = self._get_store(scope, sub_id)
            results = store.search(query, top_k=top_k)
            return self._apply_confidence(results, confidence_threshold)
        except Exception as e:
            logger.error("RAG 检索失败: %s", e)
            return []

    @staticmethod
    def _apply_confidence(
        results: list[SearchResult],
        threshold: float,
    ) -> list[SearchResult]:
        """过滤低于阈值的结果，并为每个结果附加置信度标签。"""
        filtered: list[SearchResult] = []
        for r in results:
            if r.score < threshold:
                continue
            # 在 metadata 中附加置信度信息
            metadata = dict(r.metadata) if r.metadata else {}
            if r.score >= 0.6:
                metadata["confidence"] = "high"
            elif r.score >= 0.3:
                metadata["confidence"] = "medium"
            else:
                metadata["confidence"] = "low"
            filtered.append(
                SearchResult(id=r.id, text=r.text, metadata=metadata, score=r.score)
            )
        return filtered

    def retrieve_cross(
        self,
        query: str,
        scopes: list[tuple[str, str]],
        top_k: int = 3,
    ) -> list[SearchResult]:
        """跨层检索：合并多层结果后按相似度排序。

        Args:
            query: 查询文本。
            scopes: [(scope, sub_id), ...] 指定要检索的多个层。
            top_k: 合并后返回前 K 个结果。

        Returns:
            合并排序后的检索结果列表。
        """
        all_results: list[SearchResult] = []
        for scope, sub_id in scopes:
            results = self.retrieve(query, scope, sub_id, top_k=top_k)
            all_results.extend(results)

        all_results.sort(key=lambda r: r.score, reverse=True)
        return all_results[:top_k]

    def retrieve_multi_source(
        self,
        query: str,
        scopes: list[tuple[str, str]],
        top_k: int = 3,
        kg_entities: list[str] | None = None,
        use_keyword: bool = True,
        use_vector: bool = True,
        use_kg: bool = False,
        ensemble_weights: tuple[float, float, float] = (0.5, 0.3, 0.2),
    ) -> list[FusedResult]:
        """多路召回：向量 + 关键词 + 知识图谱融合。

        Args:
            query: 查询文本。
            scopes: [(scope, sub_id), ...] 指定要检索的多个层。
            top_k: 最终返回前 K 个结果。
            kg_entities: 知识图谱实体列表（仅 use_kg=True 时）。
            use_keyword: 启用关键词检索。
            use_vector: 启用向量检索。
            use_kg: 启用知识图谱检索。
            ensemble_weights: (向量权重, 关键词权重, 知识图谱权重)。

        Returns:
            融合排序后的 FusedResult 列表。
        """
        w_vec, w_kw, w_kg = ensemble_weights
        fused: dict[str, FusedResult] = {}

        def _add(source: str, rid: str, text: str, meta: dict, score: float) -> None:
            if rid not in fused:
                fused[rid] = FusedResult(id=rid, text=text, metadata=meta)
            fr = fused[rid]
            if source == "vector":
                fr.vector_score = max(fr.vector_score, score)
            elif source == "keyword":
                fr.keyword_score = max(fr.keyword_score, score)
            elif source == "kg":
                fr.kg_score = max(fr.kg_score, score)
            fr.ensemble_score = (
                w_vec * fr.vector_score + w_kw * fr.keyword_score + w_kg * fr.kg_score
            )

        for scope, sub_id in scopes:
            store = self._get_store(scope, sub_id)

            # —— 向量召回 ——
            if use_vector:
                for r in store.search(query, top_k=top_k):
                    _add("vector", r.id, r.text, r.metadata or {}, r.score)

            # —— 关键词召回（BM25 风格） ——
            if use_keyword:
                kw_tokens = set(
                    re.findall(r"[a-zA-Z_]\w*|[\u4e00-\u9fff]", query.lower())
                )
                for doc_id in store.list_ids():
                    doc = store.get(doc_id)
                    if not doc:
                        continue
                    doc_tokens = set(
                        re.findall(r"[a-zA-Z_]\w*|[\u4e00-\u9fff]", doc.text.lower())
                    )
                    overlap = len(kw_tokens & doc_tokens)
                    if overlap == 0:
                        continue
                    score = overlap / (
                        len(kw_tokens) + len(doc_tokens) - overlap + 1e-8
                    )
                    _add("keyword", doc.id, doc.text, doc.metadata, score)

            # —— 知识图谱召回 ——
            if use_kg and kg_entities:
                for doc_id in store.list_ids():
                    doc = store.get(doc_id)
                    if not doc:
                        continue
                    doc_text_lower = doc.text.lower()
                    kg_score = 0.0
                    for ent in kg_entities:
                        if ent.lower() in doc_text_lower:
                            kg_score += 1.0
                    if kg_score > 0:
                        kg_score /= max(len(kg_entities), 1)
                        _add("kg", doc.id, doc.text, doc.metadata, kg_score)

        results = sorted(fused.values(), key=lambda x: -x.ensemble_score)
        return results[:top_k]

    @staticmethod
    def rerank(
        results: list[FusedResult | SearchResult], top_k: int | None = None
    ) -> list[FusedResult | SearchResult]:
        """重排序：使用交叉编码风格信号对结果重新排序。

        对每个结果计算三个信号：
        1. 长度惩罚：过长/过短文本降权
        2. 多样性奖励：与更高分结果的文本重复度惩罚
        3. 分数稳定性：已有 score 作为基础

        Args:
            results: 检索结果列表。
            top_k: 返回前 K 个（None = 全部）。

        Returns:
            重排序后的结果列表。
        """
        if not results:
            return results

        reranked: list[tuple[float, Any]] = []
        ideal_len = 200
        seen_texts: list[str] = []

        for r in results:
            base = r.ensemble_score if isinstance(r, FusedResult) else r.score
            text_len = len(r.text) if hasattr(r, "text") else 0

            # 长度惩罚
            len_penalty = 1.0 - min(abs(text_len - ideal_len) / ideal_len, 0.5)

            # 多样性奖励
            div_bonus = 1.0
            text_lower = r.text.lower() if hasattr(r, "text") else ""
            for prev in seen_texts:
                common = len(set(text_lower.split()) & set(prev.split()))
                total = len(set(text_lower.split()) | set(prev.split()))
                jaccard = common / total if total else 0
                if jaccard > 0.7:
                    div_bonus *= 0.5
            seen_texts.append(text_lower)

            final_score = base * len_penalty * div_bonus
            reranked.append((final_score, r))

        reranked.sort(key=lambda x: -x[0])
        results_out = [r for _, r in reranked]
        if top_k is not None:
            results_out = results_out[:top_k]
        return results_out

    def clear_task(self, task_id: str) -> None:
        """清理临时任务库。

        Args:
            task_id: 任务 ID。
        """
        key = f"{SCOPE_TASK}/{task_id}"
        self._stores.pop(key, None)

        path = self._get_path(SCOPE_TASK, task_id)
        import os

        if os.path.exists(path):
            os.remove(path)
            logger.info("RAG 清理任务库: task_id=%s", task_id)

    def purge_expired(
        self,
        scope: str,
        ttl_seconds: float,
        now: float | None = None,
        sub_id: str = "",
    ) -> int:
        """P0 修复：清理指定层过期记忆条目。

        基于 metadata 中的 timestamp 字段判断过期：若 now - timestamp > ttl_seconds，
        则删除该条目。删除后立即持久化。

        Args:
            scope: 知识库层（global / agent / task）。
            ttl_seconds: 生存时长（秒），超过则视为过期。
            now: 当前时间戳（测试注入），None 则用 time.time()。
            sub_id: 岗位 ID（scope=agent）或任务 ID（scope=task）。

        Returns:
            清理的条目数。
        """
        import time

        if now is None:
            now = time.time()
        try:
            store = self._get_store(scope, sub_id)
        except Exception as e:
            logger.error("RAG purge_expired 获取库失败: %s", e)
            return 0

        expired_ids: list[str] = []
        for doc_id in store.list_ids():
            doc = store.get(doc_id)
            if doc is None:
                continue
            ts = doc.metadata.get("timestamp")
            if ts is None:
                continue
            try:
                if now - float(ts) > ttl_seconds:
                    expired_ids.append(doc_id)
            except (TypeError, ValueError):
                logger.exception("Exception in block")
                continue

        for doc_id in expired_ids:
            store.delete(doc_id)

        if expired_ids:
            self._save_store(scope, sub_id)
            logger.info(
                "RAG 过期清理: scope=%s, sub_id=%s, 清理 %d 条",
                scope,
                sub_id,
                len(expired_ids),
            )
        return len(expired_ids)

    def retrieve_with_confidence(
        self,
        query: str,
        scope: str,
        sub_id: str = "",
        top_k: int = 2,
        min_confidence: str = "low",
    ) -> list[SearchResult]:
        """检索并按最低置信度等级过滤。

        Args:
            query: 查询文本。
            scope: 知识库层。
            sub_id: 岗位 ID 或任务 ID。
            top_k: 返回前 K 个结果。
            min_confidence: 最低置信度等级（high / medium / low）。

        Returns:
            过滤后的结果列表。
        """
        threshold_map = {"high": 0.6, "medium": 0.3, "low": 0.0}
        threshold = threshold_map.get(min_confidence, 0.0)
        return self.retrieve(
            query, scope, sub_id, top_k, confidence_threshold=threshold
        )

    def get_store_size(self, scope: str, sub_id: str = "") -> int:
        """获取指定层的文档数。"""
        store = self._get_store(scope, sub_id)
        return store.size

    def persist_all(self) -> None:
        """持久化所有已加载的库。"""
        for key in self._stores:
            parts = key.split("/", 1)
            scope = parts[0]
            sub_id = parts[1] if len(parts) > 1 else ""
            self._save_store(scope, sub_id)


class RagCapable:
    """RAG 能力 Mixin：为任意 Agent 提供岗位私有知识库接入。

    P3 扩容：岗位 RAG 全覆盖。
    使用方式：继承此类并在 __init__ 中调用 bind_rag(rag)。
    rag 为 None 时所有方法安全跳过，不影响主链路。
    """

    def bind_rag(self, rag: RAGSystem | None) -> None:
        """绑定 RAG 系统（None 表示不启用）。"""
        self._rag = rag

    def rag_retrieve(
        self, query: str, top_k: int = 2, confidence_threshold: float = 0.0
    ) -> list[SearchResult]:
        """从岗位私有库检索历史方案。rag 未绑定或失败时返回空列表。"""
        if not getattr(self, "_rag", None):
            return []
        try:
            return self._rag.retrieve(
                query=query,
                scope=SCOPE_AGENT,
                sub_id=self.agent_id,
                top_k=top_k,
                confidence_threshold=confidence_threshold,
            )
        except Exception as e:
            logger.warning("RAG 检索失败（不阻塞）: %s", e)
            return []

    def rag_ingest(
        self,
        id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """向岗位私有库注入知识。rag 未绑定时安全跳过。"""
        if not getattr(self, "_rag", None):
            return
        try:
            self._rag.ingest(
                scope=SCOPE_AGENT,
                id=id,
                text=text,
                metadata=metadata or {},
                sub_id=self.agent_id,
            )
        except Exception as e:
            logger.warning("RAG 注入失败（不阻塞）: %s", e)

    def build_rag_fewshot(self, query: str, top_k: int = 2) -> str:
        """构建 RAG few-shot 文本块（无结果返回空串）。

        包含置信度标签：high ✓ / medium ~ / low ⚠。
        """
        results = self.rag_retrieve(query, top_k=top_k)
        if not results:
            return ""
        parts = ["\n参考方案（来自历史记忆）：\n"]
        for i, r in enumerate(results, 1):
            conf = r.metadata.get("confidence", "low") if r.metadata else "low"
            tags = {"high": "✓", "medium": "~", "low": "⚠"}
            tag = tags.get(conf, "?")
            parts.append(
                f"方案{i}（相似度 {r.score:.2f} [{tag} {conf}]）：\n"
                f"{r.text[:200]}\n\n"
            )
        return "".join(parts)
