"""BlueDeer 向量存储引擎：纯标准库 TF-IDF + 余弦相似度 + IVF 索引。"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VectorDocument:
    """向量文档条目。"""

    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    tfidf_vector: dict[str, float] = field(default_factory=dict)


@dataclass
class SearchResult:
    """检索结果。"""

    id: str
    text: str
    metadata: dict[str, Any]
    score: float


@dataclass
class IVFIndex:
    """IVF（倒排文件）索引配置与状态。"""

    nlist: int = 10  # 聚类中心数（分区数）
    nprobe: int = 2  # 检索时探査的分区数
    centroids: list[dict[str, float]] | None = None  # 每个分区的质心向量
    labels: dict[str, int] | None = None  # 文档 id → 分区 id


class VectorStore:
    """内存向量存储引擎。

    使用 TF-IDF（词频-逆文档频率）将文本转为稀疏向量，
    通过余弦相似度进行检索。纯标准库实现，零第三方依赖。

    中文按字符分词，英文按空格 + 标点分词。

    支持 IVF 索引：将文档聚类到 nlist 个分区，检索时只扫描 nprobe 个最近分区。
    """

    def __init__(self) -> None:
        self._documents: dict[str, VectorDocument] = {}
        # 文档频率：每个词出现在多少篇文档中
        self._df: dict[str, int] = {}
        self._ivf: IVFIndex | None = None

    def _tokenize(self, text: str) -> list[str]:
        """分词：中文按字符，英文按空格/标点。"""
        # 提取英文单词
        tokens = re.findall(r"[a-zA-Z_]\w*", text.lower())
        # 提取中文字符（每个字符作为一个 token）
        tokens.extend(re.findall(r"[\u4e00-\u9fff]", text))
        return tokens

    def _compute_tfidf(self, text: str) -> dict[str, float]:
        """计算文本的 TF-IDF 向量。"""
        tokens = self._tokenize(text)
        if not tokens:
            return {}

        # 词频
        tf: dict[str, int] = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1

        total_docs = len(self._documents) + 1  # +1 平滑

        # TF-IDF
        vector: dict[str, float] = {}
        for token, count in tf.items():
            tf_val = count / len(tokens)
            df = self._df.get(token, 0) + 1  # +1 平滑
            idf_val = math.log(total_docs / df) + 1
            vector[token] = tf_val * idf_val

        return vector

    def _update_df(self, tokens: list[str], delta: int) -> None:
        """更新文档频率。"""
        unique_tokens = set(tokens)
        for token in unique_tokens:
            self._df[token] = self._df.get(token, 0) + delta

    def insert(
        self, id: str, text: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """插入文档。若 id 已存在则覆盖。"""
        # 若已存在，先移除旧的
        if id in self._documents:
            self.delete(id)

        tokens = self._tokenize(text)
        self._update_df(tokens, 1)

        tfidf = self._compute_tfidf(text)
        doc = VectorDocument(
            id=id,
            text=text,
            metadata=metadata or {},
            tfidf_vector=tfidf,
        )
        self._documents[id] = doc

    def delete(self, id: str) -> bool:
        """删除文档。返回是否删除成功。"""
        if id not in self._documents:
            return False
        doc = self._documents.pop(id)
        tokens = self._tokenize(doc.text)
        self._update_df(tokens, -1)
        # 清理 df 为 0 的词
        self._df = {k: v for k, v in self._df.items() if v > 0}
        return True

    def delete_batch(self, ids: list[str]) -> int:
        """批量删除文档。

        Args:
            ids: 要删除的文档 ID 列表。

        Returns:
            实际删除的文档数量。
        """
        removed = 0
        for id in ids:
            if self.delete(id):
                removed += 1
        return removed

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """余弦相似度检索（支持 IVF 加速）。

        Args:
            query: 查询文本。
            top_k: 返回前 K 个结果。

        Returns:
            按相似度降序排列的检索结果列表。
        """
        if not self._documents:
            return []

        query_vector = self._compute_tfidf(query)
        if not query_vector:
            return []

        # 确定要扫描的文档列表（IVF 剪枝）
        docs_to_scan = (
            self._ivf_prune(query_vector)
            if self._ivf
            else list(self._documents.values())
        )

        results: list[SearchResult] = []
        for doc in docs_to_scan:
            score = self._cosine_similarity(query_vector, doc.tfidf_vector)
            results.append(
                SearchResult(
                    id=doc.id,
                    text=doc.text,
                    metadata=doc.metadata,
                    score=score,
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def _ivf_prune(self, query_vector: dict[str, float]) -> list[VectorDocument]:
        """IVF 剪枝：只返回 nprobe 个最近分区中的文档。"""
        if not self._ivf or not self._ivf.centroids or not self._ivf.labels:
            return list(self._documents.values())

        # 计算查询向量与每个分区质心的距离
        scored_centroids: list[tuple[float, int]] = []
        for cid, centroid in enumerate(self._ivf.centroids):
            sim = self._cosine_similarity(query_vector, centroid)
            scored_centroids.append((sim, cid))
        scored_centroids.sort(key=lambda x: -x[0])

        # 取 nprobe 个最近分区
        probe_cids = {cid for _, cid in scored_centroids[: self._ivf.nprobe]}
        result: list[VectorDocument] = []
        for doc_id, cid in self._ivf.labels.items():
            if cid in probe_cids and doc_id in self._documents:
                result.append(self._documents[doc_id])
        return result

    def build_ivf(self, nlist: int = 10, nprobe: int = 2) -> None:
        """构建 IVF 索引。

        使用 KMeans 风格的贪心分配：将每个文档分配到与其向量最相似的质心分区。

        Args:
            nlist: 聚类中心数（分区数）。
            nprobe: 检索时探査的分区数。
        """
        docs = list(self._documents.values())
        if len(docs) < nlist:
            nlist = max(1, len(docs))

        # 随机初始化质心（取前 nlist 个文档的向量）
        centroids: list[dict[str, float]] = []
        for i in range(nlist):
            centroids.append(dict(docs[i % len(docs)].tfidf_vector))

        # 迭代分配（最多 10 轮）
        labels: dict[str, int] = {}
        for _ in range(10):
            changed = 0
            new_labels: dict[str, int] = {}
            for doc in docs:
                best_cid = 0
                best_sim = -1.0
                for cid, centroid in enumerate(centroids):
                    sim = self._cosine_similarity(doc.tfidf_vector, centroid)
                    if sim > best_sim:
                        best_sim = sim
                        best_cid = cid
                new_labels[doc.id] = best_cid
                if labels.get(doc.id) != best_cid:
                    changed += 1
            labels = new_labels
            if changed == 0:
                break

            # 更新质心
            for cid in range(nlist):
                cluster_docs = [d for did, d in docs if labels.get(did) == cid]
                if not cluster_docs:
                    continue
                centroid: dict[str, float] = {}
                for d in cluster_docs:
                    for token, val in d.tfidf_vector.items():
                        centroid[token] = centroid.get(token, 0) + val
                n = len(cluster_docs)
                centroids[cid] = {k: v / n for k, v in centroid.items()}

        self._ivf = IVFIndex(
            nlist=nlist, nprobe=nprobe, centroids=centroids, labels=labels
        )

    def _cosine_similarity(
        self, vec_a: dict[str, float], vec_b: dict[str, float]
    ) -> float:
        """计算两个稀疏向量的余弦相似度。"""
        if not vec_a or not vec_b:
            return 0.0

        # 点积
        common_keys = set(vec_a.keys()) & set(vec_b.keys())
        dot_product = sum(vec_a[k] * vec_b[k] for k in common_keys)

        # 模长
        norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
        norm_b = math.sqrt(sum(v * v for v in vec_b.values()))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    @property
    def size(self) -> int:
        """当前文档数。"""
        return len(self._documents)

    def get(self, id: str) -> VectorDocument | None:
        """获取文档。"""
        return self._documents.get(id)

    def list_ids(self) -> list[str]:
        """列出所有文档 ID。"""
        return list(self._documents.keys())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VectorStore:
        """从字典反序列化。"""
        store = cls()
        store._df = data.get("df", {})
        for doc_id, doc_data in data.get("documents", {}).items():
            tokens = store._tokenize(doc_data["text"])
            tfidf = store._compute_tfidf(doc_data["text"])
            store._documents[doc_id] = VectorDocument(
                id=doc_data["id"],
                text=doc_data["text"],
                metadata=doc_data.get("metadata", {}),
                tfidf_vector=tfidf,
            )
        ivf_data = data.get("ivf")
        if ivf_data:
            store._ivf = IVFIndex(
                nlist=ivf_data["nlist"],
                nprobe=ivf_data["nprobe"],
                centroids=ivf_data.get("centroids"),
                labels=ivf_data.get("labels"),
            )
        return store

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典（用于持久化）。"""
        result = {
            "documents": {
                doc_id: {
                    "id": doc.id,
                    "text": doc.text,
                    "metadata": doc.metadata,
                }
                for doc_id, doc in self._documents.items()
            },
            "df": self._df,
        }
        if self._ivf:
            result["ivf"] = {
                "nlist": self._ivf.nlist,
                "nprobe": self._ivf.nprobe,
                "centroids": self._ivf.centroids,
                "labels": self._ivf.labels,
            }
        return result
