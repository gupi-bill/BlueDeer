"""BlueDeer T-Digest：流式分位数估算。

evolution（数据维度 - R200）：
- 流式数据需实时查询分位数（p50、p99 延迟监控）
- 存全量数据排序太占内存
- T-Digest：把数据聚成若干"质心"（centroid），每个有均值和权重
- 质心大小自适应：中间大、两端小 → 两端分位数更准
- 误差可控，内存固定，是工业级分位数估算标准
- 与 Count-Min Sketch 互补：CMS 估算频率，T-Digest 估算分位数
"""

from __future__ import annotations

import threading


class _Centroid:
    """质心：均值 + 权重。"""

    __slots__ = ("mean", "weight")

    def __init__(self, mean: float, weight: int = 1):
        self.mean = mean
        self.weight = weight


class TDigest:
    """T-Digest：流式分位数估算。

    用法：
        td = TDigest(compression=100)
        for v in [1, 2, 3, ..., 1000]:
            td.add(v)
        td.quantile(0.5)   # 中位数近似
        td.quantile(0.99)  # p99
    """

    def __init__(self, compression: float = 100):
        if compression < 10:
            raise ValueError("compression >= 10")
        self._delta = compression  # 压缩参数（越大越准越占内存）
        self._centroids: list[_Centroid] = []  # 按 mean 排序
        self._total_weight = 0
        self._min = float("inf")
        self._max = float("-inf")
        self._lock = threading.RLock()

    def __len__(self) -> int:
        """总数据点数。"""
        return self._total_weight

    def centroid_count(self) -> int:
        """当前质心数。"""
        with self._lock:
            return len(self._centroids)

    @property
    def precision(self) -> float:
        """当前精度（compression 参数）。"""
        return self._delta

    def add(self, value: float, weight: int = 1) -> None:
        """添加数据点。"""
        if weight <= 0:
            raise ValueError("weight > 0")
        with self._lock:
            # 更新 min/max
            self._min = min(self._min, value)
            self._max = max(self._max, value)
            # 新质心
            self._centroids.append(_Centroid(value, weight))
            self._total_weight += weight
            # 达到阈值时压缩
            if len(self._centroids) > self._delta * 2:
                self._compress()

    def add_many(self, values) -> None:
        """批量添加。"""
        for v in values:
            self.add(v)

    def _compress(self) -> None:
        """合并质心：按 k-scale 控制。"""
        if len(self._centroids) < 2:
            return
        self._centroids.sort(key=lambda c: c.mean)
        new: list[_Centroid] = []
        cur = _Centroid(self._centroids[0].mean, self._centroids[0].weight)
        cum = cur.weight  # 已累计权重（含 cur）
        for i in range(1, len(self._centroids)):
            c = self._centroids[i]
            # q = cur 在分位数上的位置
            q = cum / self._total_weight
            # k-scale：质心最大权重（中间大，两端小）
            k = 4 * self._total_weight * q * (1 - q) / self._delta
            if cur.weight + c.weight <= k:
                # 合并
                tw = cur.weight + c.weight
                cur.mean = (cur.mean * cur.weight + c.mean * c.weight) / tw
                cur.weight = tw
            else:
                new.append(cur)
                cur = _Centroid(c.mean, c.weight)
            cum += c.weight
        new.append(cur)
        self._centroids = new

    def quantile(self, q: float) -> float:
        """估算分位数。q ∈ [0, 1]。"""
        if not (0 <= q <= 1):
            raise ValueError("q ∈ [0, 1]")
        with self._lock:
            if not self._centroids:
                return float("nan")
            if q == 0:
                return self._min
            if q == 1:
                return self._max
            if len(self._centroids) > self._delta:
                self._compress()
            if not self._centroids:
                return float("nan")
            # 保证有序
            self._centroids.sort(key=lambda c: c.mean)
            target = q * self._total_weight
            cumulative = 0.0
            n = len(self._centroids)
            for i, c in enumerate(self._centroids):
                next_cum = cumulative + c.weight
                if target <= next_cum:
                    # target 落在此质心区间
                    if i + 1 < n:
                        # 在质心内插值到下一个质心
                        # t = 0 在质心左边界, t = 1 在质心右边界
                        t = (target - cumulative) / c.weight if c.weight > 0 else 0
                        # 映射到 [-0.5, 0.5]（质心中心是 0）
                        t = t - 0.5
                        delta = self._centroids[i + 1].mean - c.mean
                        return c.mean + t * delta
                    return c.mean
                cumulative = next_cum
            return self._centroids[-1].mean

    def merge(self, other: TDigest) -> None:
        """合并另一个 digest。"""
        with self._lock:
            for c in other._centroids:
                self._centroids.append(_Centroid(c.mean, c.weight))
                self._total_weight += c.weight
            self._min = min(self._min, other._min)
            self._max = max(self._max, other._max)
            self._compress()

    def min(self) -> float:
        """最小值。"""
        with self._lock:
            return self._min if self._centroids else float("nan")

    def max(self) -> float:
        """最大值。"""
        with self._lock:
            return self._max if self._centroids else float("nan")

    def mean(self) -> float:
        """均值。"""
        with self._lock:
            if not self._centroids:
                return float("nan")
            return sum(c.mean * c.weight for c in self._centroids) / self._total_weight

    def status(self) -> dict:
        with self._lock:
            return {
                "total_weight": self._total_weight,
                "centroid_count": len(self._centroids),
                "compression": self._delta,
                "min": self._min if self._centroids else None,
                "max": self._max if self._centroids else None,
            }
