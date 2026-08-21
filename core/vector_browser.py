"""BlueDeer 向量浏览器：跨层浏览、搜索、分析向量数据库。"""

from __future__ import annotations

import glob as glob_mod
import logging
import math
import os
import random
from typing import Any

from vector_db.persistence import load_from_disk
from vector_db.vector_store import VectorStore

logger = logging.getLogger("bluedeer.vector_browser")


class VectorBrowser:
    """向量库浏览器——不修改数据，只读查询。

    能做的事：
    - 发现所有层（global / agent / task）及其文档数
    - 浏览指定层的全部文档
    - 跨层搜索（一次 query 搜所有层）
    - 找相似文档（基于余弦相似度）
    """

    def __init__(self, db_root: str = "data") -> None:
        self._db_root = db_root
        # 缓存已打开的 store: path → VectorStore
        self._cache: dict[str, VectorStore] = {}

    # ============== 层发现 ==============

    def list_layers(self) -> list[dict[str, Any]]:
        """发现所有可用层及其文档数。"""
        layers: list[dict[str, Any]] = []
        seen: set[str] = set()

        # global 层
        global_path = f"{self._db_root}/global.json"
        if os.path.exists(global_path):
            store = self._get_store(global_path)
            layers.append(
                {
                    "scope": "global",
                    "sub_id": "",
                    "path": global_path,
                    "doc_count": store.size,
                }
            )
            seen.add(global_path)

        # agent 层：data/agent/*.json
        agent_pattern = f"{self._db_root}/agent/*.json"
        for fpath in sorted(glob_mod.glob(agent_pattern)):
            if fpath in seen:
                continue
            store = self._get_store(fpath)
            sub_id = os.path.splitext(os.path.basename(fpath))[0]
            layers.append(
                {
                    "scope": "agent",
                    "sub_id": sub_id,
                    "path": fpath,
                    "doc_count": store.size,
                }
            )
            seen.add(fpath)

        # task 层：data/task/*.json
        task_pattern = f"{self._db_root}/task/*.json"
        for fpath in sorted(glob_mod.glob(task_pattern)):
            if fpath in seen:
                continue
            store = self._get_store(fpath)
            sub_id = os.path.splitext(os.path.basename(fpath))[0]
            layers.append(
                {
                    "scope": "task",
                    "sub_id": sub_id,
                    "path": fpath,
                    "doc_count": store.size,
                }
            )
            seen.add(fpath)

        return layers

    def layer_stats(self) -> dict[str, Any]:
        """各层统计汇总。"""
        layers = self.list_layers()
        total_docs = sum(l["doc_count"] for l in layers)
        return {
            "total_layers": len(layers),
            "total_docs": total_docs,
            "layers": layers,
        }

    # ============== 文档浏览 ==============

    def list_documents(
        self,
        scope: str,
        sub_id: str = "",
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """列出指定层的文档（分页）。"""
        path = self._resolve_path(scope, sub_id)
        store = self._get_store(path)
        all_ids = store.list_ids()
        total = len(all_ids)
        page = all_ids[offset : offset + limit]

        docs = []
        for doc_id in page:
            doc = store.get(doc_id)
            if doc is None:
                continue
            docs.append(
                {
                    "id": doc.id,
                    "text_preview": doc.text[:200],
                    "text_length": len(doc.text),
                    "metadata": doc.metadata,
                    "token_count": len(doc.tfidf_vector),
                }
            )

        return {
            "scope": scope,
            "sub_id": sub_id,
            "total": total,
            "offset": offset,
            "limit": limit,
            "docs": docs,
        }

    def get_document(
        self, scope: str, sub_id: str, doc_id: str
    ) -> dict[str, Any] | None:
        """获取单篇文档详情。"""
        path = self._resolve_path(scope, sub_id)
        store = self._get_store(path)
        doc = store.get(doc_id)
        if doc is None:
            return None
        return {
            "id": doc.id,
            "text": doc.text,
            "metadata": doc.metadata,
            "token_count": len(doc.tfidf_vector),
            "top_tokens": sorted(doc.tfidf_vector.items(), key=lambda x: -x[1])[:20],
        }

    # ============== 搜索 ==============

    def search_all(
        self,
        query: str,
        top_k_per_layer: int = 3,
    ) -> list[dict[str, Any]]:
        """跨层搜索：每层搜 top_k，合并后按分数降序。"""
        layers = self.list_layers()
        all_results: list[dict[str, Any]] = []

        for layer in layers:
            path = layer["path"]
            store = self._get_store(path)
            if store.size == 0:
                continue
            results = store.search(query, top_k=top_k_per_layer)
            for r in results:
                all_results.append(
                    {
                        "id": r.id,
                        "text": r.text[:300],
                        "score": round(r.score, 4),
                        "metadata": r.metadata,
                        "layer_scope": layer["scope"],
                        "layer_sub_id": layer["sub_id"],
                    }
                )

        all_results.sort(key=lambda r: -r["score"])
        return all_results

    def similar_to(
        self,
        doc_id: str,
        scope: str,
        sub_id: str = "",
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """找与指定文档相似的其他文档（在同一层内）。"""
        path = self._resolve_path(scope, sub_id)
        store = self._get_store(path)
        doc = store.get(doc_id)
        if doc is None:
            return []

        # 用文档全文做 query 搜索同层（排除自身）
        results = store.search(doc.text, top_k=top_k + 1)
        similar = []
        for r in results:
            if r.id == doc_id:
                continue
            similar.append(
                {
                    "id": r.id,
                    "text": r.text[:300],
                    "score": round(r.score, 4),
                    "metadata": r.metadata,
                }
            )
            if len(similar) >= top_k:
                break
        return similar

    # ============== 可视化与筛选 ==============

    def _build_document_matrix(self, docs: list) -> tuple[list[list[float]], list[str]]:
        all_tokens = sorted({t for d in docs for t in d.tfidf_vector})
        matrix = []
        for d in docs:
            row = [d.tfidf_vector.get(t, 0.0) for t in all_tokens]
            matrix.append(row)
        return matrix, all_tokens

    def _project_pca(
        self, matrix: list[list[float]], docs: list
    ) -> list[dict[str, Any]]:
        n = len(matrix)
        m = len(matrix[0]) if n else 0
        if not n or not m:
            return []
        means = [sum(matrix[i][j] for i in range(n)) / n for j in range(m)]
        centered = [[matrix[i][j] - means[j] for j in range(m)] for i in range(n)]
        cov = [[0.0] * m for _ in range(m)]
        for i in range(m):
            for j in range(m):
                cov[i][j] = sum(centered[k][i] * centered[k][j] for k in range(n)) / (
                    n - 1 if n > 1 else 1
                )
        _eig_vals, eig_vecs = self._power_iteration(cov, 2)
        result_2d = []
        for i in range(n):
            x = sum(centered[i][j] * eig_vecs[0][j] for j in range(m))
            y = sum(centered[i][j] * eig_vecs[1][j] for j in range(m))
            result_2d.append(
                {
                    "id": docs[i].id,
                    "text_preview": docs[i].text[:80],
                    "x": round(x, 6),
                    "y": round(y, 6),
                    "metadata": docs[i].metadata,
                }
            )
        return result_2d

    def _project_tsne(
        self, matrix: list[list[float]], docs: list
    ) -> list[dict[str, Any]]:
        n = len(matrix)
        m = len(matrix[0]) if n else 0
        if not n or not m:
            return []
        sim_matrix = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                num = sum(matrix[i][k] * matrix[j][k] for k in range(m))
                ni = math.sqrt(sum(v * v for v in matrix[i])) or 1
                nj = math.sqrt(sum(v * v for v in matrix[j])) or 1
                sim_matrix[i][j] = num / (ni * nj)
        perplexity = max(1, min(n // 3, 30))
        eps = 1e-8
        p_joint = [[0.0] * n for _ in range(n)]
        for i in range(n):
            dists = [(j, 1.0 - sim_matrix[i][j]) for j in range(n) if j != i]
            dists.sort(key=lambda x: x[1])
            sigma = dists[min(perplexity, len(dists)) - 1][1] + eps if dists else 1.0
            row_sum = 0.0
            for j in range(n):
                if i == j:
                    continue
                p_joint[i][j] = math.exp(-(1.0 - sim_matrix[i][j]) / sigma)
                row_sum += p_joint[i][j]
            for j in range(n):
                if i == j:
                    continue
                p_joint[i][j] /= row_sum if row_sum else 1
        for i in range(n):
            for j in range(n):
                if i != j:
                    p_joint[i][j] = (p_joint[i][j] + p_joint[j][i]) / (2 * n)
        pos = [[random.gauss(0, 1e-4), random.gauss(0, 1e-4)] for _ in range(n)]
        lr = 200.0
        for _iter in range(200):
            grad = [[0.0, 0.0] for _ in range(n)]
            for i in range(n):
                for j in range(n):
                    if i == j:
                        continue
                    dij = (
                        math.sqrt(
                            (pos[i][0] - pos[j][0]) ** 2 + (pos[i][1] - pos[j][1]) ** 2
                        )
                        + eps
                    )
                    qij = 1.0 / (1.0 + dij**2)
                    pq = (p_joint[i][j] - qij) * qij
                    grad[i][0] += pq * (pos[i][0] - pos[j][0])
                    grad[i][1] += pq * (pos[i][1] - pos[j][1])
            for i in range(n):
                pos[i][0] += lr * grad[i][0]
                pos[i][1] += lr * grad[i][1]
        result_2d = []
        for i in range(n):
            result_2d.append(
                {
                    "id": docs[i].id,
                    "text_preview": docs[i].text[:80],
                    "x": round(pos[i][0], 6),
                    "y": round(pos[i][1], 6),
                    "metadata": docs[i].metadata,
                }
            )
        return result_2d

    def project_2d(
        self, scope: str, sub_id: str = "", method: str = "tsne"
    ) -> list[dict[str, Any]]:
        """降维投影到 2D（用于可视化）。

        Args:
            scope: 知识库层。
            sub_id: 岗位或任务 ID。
            method: 降维方法 — 'tsne'（t-SNE 风格）或 'pca'（主成分分析）。

        Returns:
            [{id, text_preview, x, y, metadata}, ...]
        """
        path = self._resolve_path(scope, sub_id)
        store = self._get_store(path)
        docs = [store.get(did) for did in store.list_ids()]
        docs = [d for d in docs if d and d.tfidf_vector]

        if not docs:
            return []

        matrix, _ = self._build_document_matrix(docs)

        if method == "pca":
            return self._project_pca(matrix, docs)
        return self._project_tsne(matrix, docs)

    @staticmethod
    def _power_iteration(
        matrix: list[list[float]], k: int
    ) -> tuple[list[float], list[list[float]]]:
        """幂迭代法求前 k 个特征对。"""
        m = len(matrix)
        vecs = [[random.gauss(0, 1) for _ in range(m)] for _ in range(k)]
        vals = [0.0] * k

        for _ in range(100):
            for ki in range(k):
                new_vec = [0.0] * m
                for i in range(m):
                    s = 0.0
                    for j in range(m):
                        s += matrix[i][j] * vecs[ki][j]
                    new_vec[i] = s
                norm = math.sqrt(sum(v * v for v in new_vec)) or 1
                vecs[ki] = [v / norm for v in new_vec]
                vals[ki] = (
                    sum(new_vec[i] * vecs[ki][i] for i in range(m)) / m if m else 0
                )

                # 格拉姆-施密特正交化
                for pk in range(ki):
                    dot = sum(vecs[ki][i] * vecs[pk][i] for i in range(m))
                    vecs[ki] = [vecs[ki][i] - dot * vecs[pk][i] for i in range(m)]
                norm = math.sqrt(sum(v * v for v in vecs[ki])) or 1
                vecs[ki] = [v / norm for v in vecs[ki]]

        return vals, vecs

    def filter_by(
        self, scope: str, sub_id: str = "", **conditions: Any
    ) -> list[dict[str, Any]]:
        """按元数据条件筛选文档。

        Args:
            scope: 知识库层。
            sub_id: 岗位或任务 ID。
            **conditions: 筛选条件键值对（metadata 字段匹配合）。

        Returns:
            匹配条件的文档列表。
        """
        path = self._resolve_path(scope, sub_id)
        store = self._get_store(path)
        results = []
        for doc_id in store.list_ids():
            doc = store.get(doc_id)
            if doc is None:
                continue
            match = True
            for key, val in conditions.items():
                if key not in doc.metadata or doc.metadata[key] != val:
                    match = False
                    break
            if match:
                results.append(
                    {
                        "id": doc.id,
                        "text_preview": doc.text[:200],
                        "metadata": doc.metadata,
                        "score": 0.0,
                    }
                )
        return results

    # ============== 内部 ==============

    def _resolve_path(self, scope: str, sub_id: str) -> str:
        if scope == "global":
            return f"{self._db_root}/global.json"
        elif scope == "agent":
            return f"{self._db_root}/agent/{sub_id}.json"
        elif scope == "task":
            return f"{self._db_root}/task/{sub_id}.json"
        else:
            return f"{self._db_root}/{scope}.json"

    def _get_store(self, path: str) -> VectorStore:
        if path not in self._cache:
            self._cache[path] = load_from_disk(path)
        return self._cache[path]
