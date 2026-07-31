"""青鸢 Kite：任务规划员工。

特殊行为：survey 俯瞰团队，updraft 上升气流给团队加成。
commit 28：行为池——高空盘旋 / 整理羽毛 / 俯冲假动作
"""
from __future__ import annotations

import random

from .digital_life_form import DigitalLifeForm, _load_sleep_config


class Kite(DigitalLifeForm):
    """青鸢。"""

    SPECIES_TEMPLATE: dict = {
        "species": "kite",
        "default_name": "青鸢",
        "metabolic_rate": 0.4,
        "hunger_rate": 0.35,
        "max_age_days": 365 * 14,
        "reproduction_age_min_days": 365 * 2,
        "reproduction_age_max_days": 365 * 10,
        "litter_size_min": 1,
        "litter_size_max": 3,
        "temperament": {"active": 0.7, "social": 0.4, "curious": 0.6},
        "color_variation": 0.1,
    }

    # commit 28：鸢特有行为池
    # 1. 高空盘旋：每隔 2 小时飞到最高空盘旋 5 分钟，纯粹享受气流
    # 2. 整理羽毛：停在高枝用喙整理翼下羽毛，偶尔扯下旧羽
    # 3. 俯冲假动作：突然收翅俯冲，快触地时猛然拉起（纯粹好玩）
    BEHAVIOR_POOL: list[dict] = [
        {
            "name": "hover_high",
            "label": "高空盘旋",
            "trigger": {
                "energy_min": 60,
                "hunger_max": 50,
                "life_stages": ["JUVENILE", "ADULT", "MIDDLE"],
                "probability": 0.015,
            },
            "duration_sec": 300,       # 5 分钟
            "cooldown_sec": 7200,      # 2 小时一次
            "animation": "work",
            "particles": "feather_drop",
        },
        {
            "name": "groom_wings",
            "label": "整理羽毛",
            "trigger": {
                "energy_min": 40,
                "hunger_max": 60,
                "life_stages": ["JUVENILE", "ADULT", "MIDDLE", "ELDERLY"],
                "probability": 0.02,
            },
            "duration_sec": 240,       # 4 分钟
            "cooldown_sec": 3600,
            "animation": "idle",
            "particles": "feather_shine",
        },
        {
            "name": "dive_fake",
            "label": "俯冲假动作",
            "trigger": {
                "energy_min": 70,
                "hunger_max": 40,
                "life_stages": ["JUVENILE", "ADULT", "MIDDLE"],
                "probability": 0.012,
            },
            "duration_sec": 10,        # 10 秒
            "cooldown_sec": 900,
            "animation": "react",
            "particles": "smirk",
        },
    ]

    def __init__(self, name="青鸢", gender="male", environment=None,
                 birth_time=None, genome_override=None):
        genome = self._build_genome(genome_override)
        super().__init__(name=name, species="kite", gender=gender,
                         genome=genome, environment=environment, birth_time=birth_time)

    def _build_genome(self, override):
        genome = {}
        for k, v in self.SPECIES_TEMPLATE.items():
            genome[k] = dict(v) if isinstance(v, dict) else v
        for k in ("metabolic_rate", "hunger_rate", "max_age_days",
                  "reproduction_age_min_days", "reproduction_age_max_days",
                  "color_variation"):
            if k in genome and isinstance(genome[k], (int, float)):
                mutation = 1.0 + random.uniform(-0.05, 0.05)
                genome[k] = type(genome[k])(genome[k] * mutation)
        sleep_cfg = _load_sleep_config().get("kite", {})
        for k in ("bedtime", "wakeup_time", "sleep_depth", "wake_on_emergency"):
            if k in sleep_cfg:
                genome[k] = sleep_cfg[k]
        if override:
            for k, v in override.items():
                genome[k] = v
        return genome

    def survey(self) -> dict:
        """俯瞰团队，返回种群快照。"""
        if self._environment is None:
            return {}
        with self._environment._lock:
            return {
                "total": len(self._environment.population),
                "alive": sum(1 for lf in self._environment.population
                             if getattr(lf, "_alive", False)),
            }

    def updraft(self) -> None:
        """上升气流：给团队所有成员加能量。"""
        if self._environment is None:
            return
        with self._environment._lock:
            snapshot = list(self._environment.population)
        for lf in snapshot:
            try:
                with lf._lock:
                    if getattr(lf, "_alive", False):
                        lf.energy = min(100.0, lf.energy + 1.0)
            except Exception:
                pass
        self._remember("上升气流给团队 +1 能量")

    def job_skill(self) -> None:
        """青鸢的岗位技能：任务规划。"""
        if random.random() < 0.05:
            self.updraft()

    # ----- commit 28：行为钩子 -----

    def _on_behavior_tick(self, cfg: dict) -> None:
        """每秒效果。"""
        bname = cfg["name"]
        if bname == "hover_high":
            # 高空盘旋：消耗能量，mood +0.3（纯粹的快乐）
            self.energy = max(0.0, self.energy - 0.2)
            self.mood_score = min(100.0, self.mood_score + 0.3)
        elif bname == "groom_wings":
            # 整理羽毛：能量恢复 +0.05，5% 概率扯下一根旧羽
            self.energy = min(100.0, self.energy + 0.05)
            if random.random() < 0.005 and self._environment is not None:
                self._environment.broadcast_event("feather_shed", {
                    "name": self._name_obj,
                    "species": "kite",
                    "zone_id": self.current_zone_id,
                })
        elif bname == "dive_fake":
            # 俯冲：消耗大量能量，mood 大涨
            self.energy = max(0.0, self.energy - 1.0)
            self.mood_score = min(100.0, self.mood_score + 1.0)

    def _on_behavior_end(self, cfg: dict, reason: str) -> None:
        """结束时记录事件。"""
        bname = cfg["name"]
        if bname == "hover_high":
            self._remember("飞到最高空盘旋了一会儿，享受气流", importance="normal")
        elif bname == "groom_wings":
            self._remember("在高枝上整理了翼下羽毛", importance="normal")
        elif bname == "dive_fake":
            self._remember("做了一个俯冲假动作，快触地时猛然拉起", importance="normal")

    def _create_child(self, genome, environment, birth_time) -> Kite:
        return Kite(
            name=f"{self._name_obj}的幼崽",
            gender=random.choice(["male", "female"]),
            environment=environment, birth_time=birth_time,
            genome_override=genome,
        )
