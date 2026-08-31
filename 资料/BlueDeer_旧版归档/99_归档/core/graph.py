"""BlueDeer 图：邻接表 + BFS/DFS + Dijkstra + 拓扑排序。

特性：
- 邻接表 dict[V, list[(V, weight)]]
- BFS / DFS 遍历
- Dijkstra 最短路径
- 拓扑排序（Kahn 入度法）
- 环检测（有向三色标记 / 无向 DFS 背边）
- 连通分量

用法：
    g = Graph()
    g.add_edge("A", "B", 1)
    g.bfs("A")  # ["A", "B"]
"""

from __future__ import annotations

import heapq
import threading
from collections import deque
from collections.abc import Hashable
from typing import Any

V = Hashable  # 顶点类型：可哈希即可


class Graph:
    """带权图（可指定有向/无向）。"""

    def __init__(self, directed: bool = False) -> None:
        self._adj: dict = {}  # {v: [(neighbor, weight), ...]}
        self._directed = directed
        self._edge_count = 0
        self._lock = threading.RLock()

    @property
    def directed(self) -> bool:
        return self._directed

    def __len__(self) -> int:
        return len(self._adj)

    def add_vertex(self, v) -> None:
        with self._lock:
            if v not in self._adj:
                self._adj[v] = []

    def add_edge(self, u: Any, v: Any, weight: float = 1.0) -> None:
        with self._lock:
            if u not in self._adj:
                self._adj[u] = []
            if v not in self._adj:
                self._adj[v] = []
            self._adj[u].append((v, weight))
            if not self._directed:
                self._adj[v].append((u, weight))
            self._edge_count += 1

    def remove_edge(self, u: Any, v) -> bool:
        with self._lock:
            if u not in self._adj:
                return False
            for i, (nb, _) in enumerate(self._adj[u]):
                if nb == v:
                    self._adj[u].pop(i)
                    self._edge_count -= 1
                    if not self._directed:
                        for j, (nb2, _) in enumerate(self._adj[v]):
                            if nb2 == u:
                                self._adj[v].pop(j)
                                break
                    return True
            return False

    def neighbors(self, v) -> list[tuple]:
        return list(self._adj.get(v, []))

    def vertices(self) -> list:
        return list(self._adj.keys())

    def edges(self) -> list[tuple]:
        result = []
        for u in self._adj:
            for v, w in self._adj[u]:
                result.append((u, v, w))
        return result

    def bfs(self, start) -> list:
        """广度优先遍历，返回访问顺序。"""
        with self._lock:
            if start not in self._adj:
                return []
            visited = {start}
            order = [start]
            q = deque([start])
            while q:
                u = q.popleft()
                for v, _ in self._adj[u]:
                    if v not in visited:
                        visited.add(v)
                        order.append(v)
                        q.append(v)
            return order

    def dfs(self, start) -> list:
        """深度优先遍历（显式栈）。"""
        with self._lock:
            if start not in self._adj:
                return []
            visited = {start}
            order = [start]
            stack = [start]
            while stack:
                u = stack[-1]
                pushed = False
                for v, _ in self._adj[u]:
                    if v not in visited:
                        visited.add(v)
                        order.append(v)
                        stack.append(v)
                        pushed = True
                        break
                if not pushed:
                    stack.pop()
            return order

    def bfs_shortest_path(self, start: Any, end) -> list | None:
        """BFS 求无权图最短路径。"""
        with self._lock:
            if start not in self._adj or end not in self._adj:
                return None
            visited = {start}
            parent = {start: None}
            q = deque([start])
            while q:
                u = q.popleft()
                if u == end:
                    break
                for v, _ in self._adj[u]:
                    if v not in visited:
                        visited.add(v)
                        parent[v] = u
                        q.append(v)
            if end not in parent:
                return None
            path = []
            cur = end
            while cur is not None:
                path.append(cur)
                cur = parent[cur]
            return list(reversed(path))

    def dijkstra(self, start) -> dict:
        """Dijkstra 单源最短路径，返回 {v: dist}。"""
        with self._lock:
            if start not in self._adj:
                return {}
            dist = {start: 0.0}
            pq = [(0.0, start)]
            while pq:
                d, u = heapq.heappop(pq)
                if d > dist.get(u, float("inf")):
                    continue
                for v, w in self._adj[u]:
                    nd = d + w
                    if nd < dist.get(v, float("inf")):
                        dist[v] = nd
                        heapq.heappush(pq, (nd, v))
            return dist

    def dijkstra_path(self, start: Any, end) -> list | None:
        """Dijkstra 带路径回溯。"""
        with self._lock:
            if start not in self._adj or end not in self._adj:
                return None
            dist = {start: 0.0}
            parent = {start: None}
            pq = [(0.0, start)]
            while pq:
                d, u = heapq.heappop(pq)
                if u == end:
                    break
                if d > dist.get(u, float("inf")):
                    continue
                for v, w in self._adj[u]:
                    nd = d + w
                    if nd < dist.get(v, float("inf")):
                        dist[v] = nd
                        parent[v] = u
                        heapq.heappush(pq, (nd, v))
            if end not in dist:
                return None
            path = []
            cur = end
            while cur is not None:
                path.append(cur)
                cur = parent[cur]
            return list(reversed(path))

    def has_cycle(self) -> bool:
        """环检测。有向用三色标记，无向用 DFS 背边。"""
        with self._lock:
            if self._directed:
                WHITE, GRAY, BLACK = 0, 1, 2
                color = {v: WHITE for v in self._adj}

                def dfs(u) -> Any:
                    color[u] = GRAY
                    for v, _ in self._adj[u]:
                        if color[v] == GRAY:
                            return True
                        if color[v] == WHITE and dfs(v):
                            return True
                    color[u] = BLACK
                    return False

                return any(color[v] == WHITE and dfs(v) for v in self._adj)
            else:
                visited = set()

                def dfs(u: Any, parent) -> Any:
                    visited.add(u)
                    for v, _ in self._adj[u]:
                        if v not in visited:
                            if dfs(v, u):
                                return True
                        elif v != parent:
                            return True
                    return False

                return any(v not in visited and dfs(v, None) for v in self._adj)

    def topological_sort(self) -> list | None:
        """拓扑排序（Kahn 入度法）。无环返回顺序，有环返回 None。"""
        if not self._directed:
            return None
        with self._lock:
            in_degree = {v: 0 for v in self._adj}
            for u in self._adj:
                for v, _ in self._adj[u]:
                    in_degree[v] += 1
            q = deque([v for v, d in in_degree.items() if d == 0])
            order = []
            while q:
                u = q.popleft()
                order.append(u)
                for v, _ in self._adj[u]:
                    in_degree[v] -= 1
                    if in_degree[v] == 0:
                        q.append(v)
            return order if len(order) == len(self._adj) else None

    def connected_components(self) -> list[list]:
        """连通分量（无向）。"""
        if self._directed:
            # 简化：弱连通分量
            pass
        with self._lock:
            visited = set()
            comps = []
            for start in self._adj:
                if start in visited:
                    continue
                comp = []
                q = deque([start])
                visited.add(start)
                while q:
                    u = q.popleft()
                    comp.append(u)
                    for v, _ in self._adj[u]:
                        if v not in visited:
                            visited.add(v)
                            q.append(v)
                comps.append(comp)
            return comps

    def shortest_path(self, a: Any, b) -> list | None:
        """求 a 到 b 的最短路径（委托 dijkstra_path）。"""
        return self.dijkstra_path(a, b)

    def minimum_spanning_tree(self) -> list[tuple] | None:
        """Kruskal 最小生成树（仅无向图）。"""
        if self._directed:
            return None
        with self._lock:
            edges = []
            for u in self._adj:
                for v, w in self._adj[u]:
                    if u < v or not self._directed:
                        edges.append((w, u, v))
            edges.sort(key=lambda x: x[0])
            parent: dict = {}

            def find(x) -> Any:
                while parent.get(x, x) != x:
                    parent[x] = parent.get(parent.get(x, x), x)
                    x = parent[x]
                return x

            def union(x: Any, y) -> None:
                rx, ry = find(x), find(y)
                if rx != ry:
                    parent[rx] = ry

            mst: list[tuple] = []
            for w, u, v in edges:
                if find(u) != find(v):
                    union(u, v)
                    mst.append((u, v, w))
            return mst if mst else None

    def clear(self) -> None:
        with self._lock:
            self._adj = {}
            self._edge_count = 0

    def status(self) -> dict:
        return {
            "vertices": len(self._adj),
            "edges": self._edge_count,
            "directed": self._directed,
        }
