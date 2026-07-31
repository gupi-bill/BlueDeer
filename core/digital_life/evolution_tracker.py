"""进化追踪器 EvolutionTracker。

职责：
- 周期性拍快照（take_snapshot）
- 记录出生/死亡/繁殖事件
- 追踪世代号
- 基因漂移分析
- Shannon 多样性指数
- 主导策略分析
- 生存指标统计
- 历史持久化（save_history / load_history，原子写入）

零基础读者可以这样理解：
- EvolutionTracker 是公司的"HR 进化档案"。
- 每隔一段时间拍一张"现在公司长啥样"的快照。
- 谁生了孩子、谁去世了都记下来。
- 算一下公司里各种动物的多样性。
"""
from __future__ import annotations

import datetime
import json
import math
import os
import threading
import time
from collections import defaultdict, deque


class EvolutionSnapshot:
    """一个时间点的进化快照。"""

    __slots__ = ("generation", "global_stats", "species_stats", "timestamp")

    def __init__(self, timestamp, generation, species_stats, global_stats) -> None:
        self.timestamp = timestamp
        self.generation = generation
        self.species_stats = species_stats
        self.global_stats = global_stats

    def to_dict(self) -> dict:
        """序列化为可 JSON 化的 dict。"""
        return {
            "timestamp": self.timestamp,
            "generation": self.generation,
            "species_stats": self.species_stats,
            "global_stats": self.global_stats,
        }

    @classmethod
    def from_dict(cls, d: dict) -> EvolutionSnapshot:
        """从 dict 反序列化。"""
        return cls(
            timestamp=d.get("timestamp", time.time()),
            generation=d.get("generation", 0),
            species_stats=d.get("species_stats", {}),
            global_stats=d.get("global_stats", {}),
        )


class EvolutionTracker:
    """进化追踪器。"""

    HISTORY_PATH = os.path.join(
        os.path.dirname(__file__), "..", "..", "snapshot", "evolution_history.json"
    )

    def __init__(self, environment) -> None:
        """初始化追踪器。

        Args:
            environment: 被追踪的 Environment 实例（Borg 单例）。
        """
        self._lock = threading.RLock()
        self._env = environment
        # 历史快照：上限 10000，避免内存爆炸
        self._snapshots: deque = deque(maxlen=10000)
        # 全局世代号（= 已观测到的最大子代 generation）
        self._generation = 0
        # 累计计数器
        self._birth_count = 0
        self._death_count = 0
        # 按物种累计
        self._species_births = defaultdict(int)
        self._species_deaths = defaultdict(int)
        self._species_reproductions = defaultdict(int)
        # 每物种最大世代
        self._max_generation_per_species = defaultdict(int)
        # 谱系：child_id -> (parent_a_id, parent_b_id)
        self._lineage: dict = {}

    # ------------------------------------------------------------------
    # 事件记录
    # ------------------------------------------------------------------

    def record_birth(self, life_form, parents: list = None) -> None:
        """记录出生事件。"""
        with self._lock:
            self._birth_count += 1
            species = getattr(life_form, "species", "unknown")
            self._species_births[species] += 1
            # 世代判定
            if parents:
                # 子代世代 = 父代最大世代 + 1
                parent_gens = []
                for p in parents:
                    p_id = id(p)
                    p_gen = 0
                    # 找父代在 lineage 中的世代
                    for cid, (pa, pb) in self._lineage.items():
                        if p_id in (pa, pb):
                            parent_gens.append(self._get_generation(cid))
                    if not parent_gens:
                        p_gen = 1  # 父代是初代
                    else:
                        p_gen = max(parent_gens) if parent_gens else 1
                gen = max(parent_gens) + 1 if parent_gens else 2
            else:
                gen = 1
            self._max_generation_per_species[species] = max(
                self._max_generation_per_species[species], gen)
            self._generation = max(self._generation, gen)
            # 谱系
            if parents:
                self._lineage[id(life_form)] = (id(parents[0]),
                                                id(parents[1]) if len(parents) > 1 else None)

    def record_death(self, life_form) -> None:
        """记录死亡事件。"""
        with self._lock:
            self._death_count += 1
            species = getattr(life_form, "species", "unknown")
            self._species_deaths[species] += 1

    def record_reproduction(self, parent_species: str) -> None:
        """记录繁殖事件。"""
        with self._lock:
            self._species_reproductions[parent_species] += 1

    def _get_generation(self, life_id: int) -> int:
        """通过 life_id 查世代号（简化版）。"""
        # ponytail: 总是返回 1 — 真实谱系递归查询未实现
        # upgrade: 用 self._lineage 做递归向上查找，给 biodiversity scoring 提供准确世代数据
        return 1

    # ------------------------------------------------------------------
    # 快照
    # ------------------------------------------------------------------

    def take_snapshot(self) -> EvolutionSnapshot:
        """拍一张当前进化快照。"""
        with self._lock:
            # 在 env._lock 内快照 population
            with self._env._lock:
                population = list(self._env.population)
                food = self._env.food_available

            # 按物种分组
            by_species: dict = defaultdict(list)
            for lf in population:
                if not getattr(lf, "_alive", False):
                    continue
                sp = getattr(lf, "species", "unknown")
                by_species[sp].append(lf)

            species_stats: dict = {}
            for sp, lives in by_species.items():
                if not lives:
                    continue
                energies = [getattr(l, "energy", 0) for l in lives]
                healths = [getattr(l, "health", 0) for l in lives]
                ages = []
                for l in lives:
                    try:
                        ages.append(l.age)
                    except Exception:
                        ages.append(0)
                species_stats[sp] = {
                    "count": len(lives),
                    "avg_energy": sum(energies) / len(energies),
                    "avg_health": sum(healths) / len(healths),
                    "avg_age_days": sum(ages) / len(ages),
                    "max_age_days": max(ages) if ages else 0,
                }

            # 全局统计
            total_alive = sum(s["count"] for s in species_stats.values())
            biodiversity = self._calc_shannon(species_stats)
            global_stats = {
                "total_alive": total_alive,
                "food_available": food,
                "biodiversity": biodiversity,
                "species_count": len(species_stats),
                "season": self._env.current_season(),
            }

            snap = EvolutionSnapshot(
                timestamp=time.time(),
                generation=self._generation,
                species_stats=species_stats,
                global_stats=global_stats,
            )
            self._snapshots.append(snap)
            return snap

    @staticmethod
    def _calc_shannon(species_stats: dict) -> float:
        """计算 Shannon 多样性指数 H = -Σ(p_i × ln(p_i))。"""
        total = sum(s["count"] for s in species_stats.values())
        if total <= 0:
            return 0.0
        h = 0.0
        for s in species_stats.values():
            p = s["count"] / total
            if p > 0:
                h -= p * math.log(p)
        return h

    # ------------------------------------------------------------------
    # 分析
    # ------------------------------------------------------------------

    def get_gene_drift(self, species: str, gene_name: str,
                       last_n: int = 20) -> list:
        """获取某物种某基因在最近 N 张快照中的漂移。

        简化版：返回每张快照该物种的平均能量（作为代理指标）。
        """
        with self._lock:
            snaps = list(self._snapshots)[-last_n:]
        drift = []
        for snap in snaps:
            sp_stat = snap.species_stats.get(species, {})
            if gene_name == "energy":
                drift.append(sp_stat.get("avg_energy"))
            elif gene_name == "health":
                drift.append(sp_stat.get("avg_health"))
            elif gene_name == "age":
                drift.append(sp_stat.get("avg_age_days"))
            else:
                drift.append(None)
        return drift

    def get_species_trend(self, species: str, last_n: int = 20) -> list:
        """获取某物种数量趋势。"""
        with self._lock:
            snaps = list(self._snapshots)[-last_n:]
        return [snap.species_stats.get(species, {}).get("count", 0) for snap in snaps]

    def get_survival_metrics(self, species: str = None) -> dict:
        """生存指标。"""
        with self._lock:
            if species:
                births = self._species_births.get(species, 0)
                deaths = self._species_deaths.get(species, 0)
                rate = deaths / births if births > 0 else 0
                return {
                    "species": species,
                    "births": births,
                    "deaths": deaths,
                    "survival_rate": 1 - rate,
                }
            return {
                "total_births": self._birth_count,
                "total_deaths": self._death_count,
                "by_species": {
                    "births": dict(self._species_births),
                    "deaths": dict(self._species_deaths),
                },
            }

    def get_dominant_strategy(self) -> dict:
        """主导策略：哪个物种数量最多。"""
        with self._lock:
            snaps = list(self._snapshots)
        if not snaps:
            return {}
        last = snaps[-1]
        species_counts = {sp: s["count"] for sp, s in last.species_stats.items()}
        if not species_counts:
            return {}
        dominant = max(species_counts.items(), key=lambda x: x[1])
        return {
            "dominant_species": dominant[0],
            "dominant_count": dominant[1],
            "all_counts": species_counts,
        }

    def get_biodiversity(self) -> dict:
        """生物多样性。"""
        with self._lock:
            snaps = list(self._snapshots)
        if not snaps:
            return {"shannon": 0.0, "trend": []}
        trend = [s.global_stats.get("biodiversity", 0) for s in snaps[-20:]]
        return {
            "shannon": trend[-1] if trend else 0.0,
            "trend": trend,
        }

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def save_history(self) -> None:
        """保存完整历史到 JSON（原子写入：tmp + os.replace）。"""
        with self._lock:
            path = self.HISTORY_PATH
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            data = {
                "snapshots": [s.to_dict() for s in self._snapshots],
                "counters": {
                    "generation": self._generation,
                    "birth_count": self._birth_count,
                    "death_count": self._death_count,
                    "species_births": dict(self._species_births),
                    "species_deaths": dict(self._species_deaths),
                    "species_reproductions": dict(self._species_reproductions),
                },
                "lineage_size": len(self._lineage),
                "saved_at": datetime.datetime.now().isoformat(),
            }
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)

    def load_history(self) -> None:
        """从 JSON 加载历史。"""
        with self._lock:
            path = self.HISTORY_PATH
            if not os.path.exists(path):
                return
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                return
            self._snapshots.clear()
            for snap_d in data.get("snapshots", []):
                self._snapshots.append(EvolutionSnapshot.from_dict(snap_d))
            counters = data.get("counters", {})
            self._generation = counters.get("generation", 0)
            self._birth_count = counters.get("birth_count", 0)
            self._death_count = counters.get("death_count", 0)
            self._species_births = defaultdict(int, counters.get("species_births", {}))
            self._species_deaths = defaultdict(int, counters.get("species_deaths", {}))
            self._species_reproductions = defaultdict(
                int, counters.get("species_reproductions", {}))

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """返回追踪器自身状态。"""
        with self._lock:
            return {
                "generation": self._generation,
                "snapshot_count": len(self._snapshots),
                "birth_count": self._birth_count,
                "death_count": self._death_count,
                "species_births": dict(self._species_births),
                "species_deaths": dict(self._species_deaths),
                "species_reproductions": dict(self._species_reproductions),
                "max_generation_per_species": dict(
                    self._max_generation_per_species),
                "lineage_size": len(self._lineage),
                "history_path": self.HISTORY_PATH,
            }
