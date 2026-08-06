"""Task DAG — 任务依赖图。

支持前置任务链（task A 完成后 task B 才能执行），
可用于调度器、工作流编排等场景。

用法：
    dag = TaskDAG()
    dag.add_node("b", depends_on=["a"])
    dag.add_node("c", depends_on=["b"])
    assert dag.ready("b", completed={"a"})    # True
    assert dag.ready("c", completed={"a"})    # False
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger("bluedeer.task_dag")

_DAG_FILE = "data/task_dag.json"


@dataclass
class DAGNode:
    """DAG 节点定义"""

    id: str
    depends_on: list[str] = field(default_factory=list)
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class TaskDAG:
    """任务依赖图。"""

    def __init__(self) -> None:
        self._nodes: dict[str, DAGNode] = {}
        self._topo_cache: list[str] | None = None
        self._topo_dirty: bool = True
        self._cache_lock = threading.RLock()
        self._load()

    # ---- 节点操作 ----

    def add_node(
        self,
        node_id: str,
        depends_on: list[str] | None = None,
        description: str = "",
        **extra: Any,
    ) -> DAGNode:
        """添加或更新节点。"""
        meta = extra.pop("metadata", {}) if "metadata" in extra else extra
        node = DAGNode(
            id=node_id,
            depends_on=depends_on or [],
            description=description,
            metadata=meta,
        )
        self._nodes[node_id] = node
        with self._cache_lock:
            self._topo_dirty = True
        return node

    def remove_node(self, node_id: str) -> bool:
        """删除节点。返回 True 如果存在。"""
        ok = self._nodes.pop(node_id, None) is not None
        if ok:
            with self._cache_lock:
                self._topo_dirty = True
        return ok

    def get_node(self, node_id: str) -> DAGNode | None:
        return self._nodes.get(node_id)

    def list_nodes(self) -> list[DAGNode]:
        return list(self._nodes.values())

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    # ---- 依赖查询 ----

    def depends_on(self, node_id: str) -> list[str]:
        """返回某节点的直接前置依赖列表。"""
        node = self._nodes.get(node_id)
        return list(node.depends_on) if node else []

    def dependents(self, node_id: str) -> list[str]:
        """返回直接依赖某节点的下游节点列表。"""
        return [nid for nid, n in self._nodes.items() if node_id in n.depends_on]

    def ancestors(self, node_id: str) -> set[str]:
        """递归返回所有祖先节点。"""
        result: set[str] = set()
        stack = list(self.depends_on(node_id))
        while stack:
            cur = stack.pop()
            if cur in result:
                continue
            result.add(cur)
            stack.extend(self.depends_on(cur))
        return result

    def descendants(self, node_id: str) -> set[str]:
        """递归返回所有后代节点。"""
        result: set[str] = set()
        stack = list(self.dependents(node_id))
        while stack:
            cur = stack.pop()
            if cur in result:
                continue
            result.add(cur)
            stack.extend(self.dependents(cur))
        return result

    # ---- 就绪检查 ----

    def ready(self, node_id: str, completed: set[str]) -> bool:
        """检查节点是否就绪（所有前置依赖已完成）。"""
        deps = self.depends_on(node_id)
        return all(d in completed for d in deps)

    def next_ready(self, completed: set[str]) -> list[str]:
        """返回所有已就绪但尚未完成的节点。"""
        return [
            nid
            for nid in self._nodes
            if nid not in completed and self.ready(nid, completed)
        ]

    def topological_sort(self, cached: bool = True) -> list[str]:
        """返回拓扑排序后的节点 ID 列表。

        检测到环则抛出 ValueError。

        Args:
            cached: 是否使用缓存（默认 True）。节点未变更时返回上次结果。

        Returns:
            拓扑排序后的节点 ID 列表。
        """
        with self._cache_lock:
            if cached and not self._topo_dirty and self._topo_cache is not None:
                return list(self._topo_cache)

        visited: dict[str, int] = {}  # 0=未访问 1=访问中 2=已完成
        order: list[str] = []

        def _dfs(nid: str) -> None:
            if visited.get(nid) == 1:
                raise ValueError(f"检测到环，涉及节点: {nid}")
            if visited.get(nid) == 2:
                return
            visited[nid] = 1
            for dep in self._nodes[nid].depends_on:
                if dep in self._nodes:
                    _dfs(dep)
            visited[nid] = 2
            order.append(nid)

        for nid in self._nodes:
            if nid not in visited:
                _dfs(nid)

        with self._cache_lock:
            self._topo_cache = list(order)
            self._topo_dirty = False

        return order

    def detect_cycle(self) -> list[str] | None:
        """检测环。返回环上的一个节点（入口）或 None。"""
        try:
            self.topological_sort()
            return None
        except ValueError as e:
            msg = str(e)
            if "涉及节点:" in msg:
                return [msg.split(":")[-1].strip()]
            return None

    # ---- 批量查询 ----

    def subgraph(self, root_id: str) -> list[DAGNode]:
        """返回以 root_id 为根的整个子图节点列表（含 root）。"""
        ids = {root_id} | self.ancestors(root_id) | self.descendants(root_id)
        return [self._nodes[nid] for nid in ids if nid in self._nodes]

    def execution_plan(self, completed: set[str] | None = None) -> list[list[str]]:
        """返回分层执行计划，每层内的节点可并行执行。

        返回示例：[["a"], ["b", "c"], ["d"]]
        """
        completed = completed or set()
        remaining = set(self._nodes.keys()) - completed
        layers: list[list[str]] = []

        while remaining:
            layer = [nid for nid in remaining if self.ready(nid, completed)]
            if not layer:
                raise ValueError(
                    "无法继续编排：剩余节点均有未完成的前置依赖，"
                    f"可能引入环。剩余节点: {remaining}"
                )
            layers.append(layer)
            completed |= set(layer)
            remaining -= set(layer)

        return layers

    # ---- 持久化 ----

    def _load(self) -> None:
        try:
            from core.database import Database

            raw = Database().load_dag_nodes()
            if raw:
                for item in raw:
                    node = DAGNode(**item)
                    self._nodes[node.id] = node
                return
        except Exception as e:
            logger.warning("从数据库加载 DAG 失败: %s", e)
        # 回退 JSON
        try:
            if not os.path.exists(_DAG_FILE):
                return
            with open(_DAG_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for item in raw:
                node = DAGNode(**item)
                self._nodes[node.id] = node
        except Exception as e:
            logger.warning("从 JSON 回退加载 DAG 失败: %s", e)

    def save(self) -> None:
        try:
            raw = [asdict(n) for n in self._nodes.values()]
            from core.database import Database

            Database().save_dag_nodes(raw)
        except Exception as e:
            logger.warning("保存 DAG 到数据库失败: %s", e)
        # 向后兼容 JSON
        try:
            os.makedirs(os.path.dirname(_DAG_FILE), exist_ok=True)
            raw = [asdict(n) for n in self._nodes.values()]
            with open(_DAG_FILE, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("保存 DAG JSON 回退失败: %s", e)

    # ---- 导入/导出 ----

    def to_dict_list(self) -> list[dict[str, Any]]:
        """导出为可序列化的字典列表。"""
        return [asdict(n) for n in self._nodes.values()]

    @classmethod
    def from_dict_list(cls, data: list[dict[str, Any]]) -> TaskDAG:
        """从字典列表导入，替换当前全部节点。"""
        dag = cls()
        dag.reset()
        for item in data:
            node = DAGNode(**item)
            dag._nodes[node.id] = node
        return dag

    def export_json(self, path: str) -> None:
        """导出 DAG 到 JSON 文件。"""
        import json
        import os

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict_list(), f, ensure_ascii=False, indent=2)

    @classmethod
    def import_json(cls, path: str) -> TaskDAG:
        """从 JSON 文件导入 DAG。"""
        import json

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict_list(data)

    # ---- 集成辅助 ----

    def decorate_task(self, task_id: str, task_type: str) -> str:
        """生成任务装饰描述，用于日志/前端。"""
        deps = self.depends_on(task_id)
        if not deps:
            return f"{task_id} ({task_type}) — 无依赖"
        return f"{task_id} ({task_type}) — 前置: {', '.join(deps)}"

    def execute_parallel(
        self,
        task_funcs: dict[str, Callable[[], Any]] | None = None,
        max_workers: int = 4,
    ) -> dict[str, Any]:
        """按拓扑顺序并行执行无依赖节点。

        自动从 DAG 中读取节点 ID 和依赖关系。每层内（无相互依赖）
        的节点通过 ThreadPoolExecutor 并行执行。

        Args:
            task_funcs: {节点ID: 可调用对象} 映射。为 None 时只验证拓扑。
            max_workers: 线程池大小（默认 4）。

        Returns:
            {节点ID: 执行结果} 字典。

        Raises:
            ValueError: 检测到环或缺少 task_funcs 条目。
        """
        topo_order = self.topological_sort(cached=True)

        if task_funcs is None:
            return {}

        missing = [nid for nid in topo_order if nid not in task_funcs]
        if missing:
            raise ValueError(f"缺少以下节点的执行函数: {missing}")

        completed: dict[str, Any] = {}
        errors: dict[str, Exception] = {}

        for layer in self.execution_plan(set(completed.keys())):
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                future_map: dict[Any, str] = {}
                for nid in layer:
                    if nid in errors:
                        continue
                    deps_ok = all(
                        d in completed and d not in errors for d in self.depends_on(nid)
                    )
                    if not deps_ok:
                        continue
                    fut = pool.submit(task_funcs[nid])
                    future_map[fut] = nid

                for fut in as_completed(future_map):
                    nid = future_map[fut]
                    try:
                        completed[nid] = fut.result()
                    except Exception as e:
                        errors[nid] = e
                        logger.error("并行执行节点 %s 失败: %s", nid, e)

        if errors:
            raise RuntimeError(f"以下节点执行失败: {list(errors.keys())}") from next(
                iter(errors.values())
            )

        return completed

    def reset(self) -> None:
        """清除所有节点。"""
        self._nodes.clear()
        with self._cache_lock:
            self._topo_cache = None
            self._topo_dirty = True
