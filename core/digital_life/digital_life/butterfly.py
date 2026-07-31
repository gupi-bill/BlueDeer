"""彩纹蝶 Butterfly：UI 设计员工。

特殊行为：完全变态发育 LARVA→PUPA→ADULT 三阶段。
commit 28：行为池——晒太阳 / 访花 / 求偶舞
"""
from __future__ import annotations

import random

from .digital_life_form import DigitalLifeForm, _load_sleep_config


class Butterfly(DigitalLifeForm):
    """彩纹蝶。"""

    SPECIES_TEMPLATE: dict = {
        "species": "butterfly",
        "default_name": "彩纹蝶",
        "metabolic_rate": 0.3,
        "hunger_rate": 0.3,
        "max_age_days": 30,  # 蝶寿命短
        "reproduction_age_min_days": 7,
        "reproduction_age_max_days": 25,
        "litter_size_min": 3,
        "litter_size_max": 8,
        "temperament": {"active": 0.6, "social": 0.5, "curious": 0.8},
        "color_variation": 0.3,
    }

    # commit 28：蝶特有行为池
    # 1. 晒太阳：白天 10-14，飞到穹顶最亮处展翅，加速能量恢复
    # 2. 访花：在花丛飞舞，传播鳞粉，偶尔触发"配色灵感"
    # 3. 求偶舞：春季成年蝶随机触发，跳 8 字舞释放彩色鳞粉
    BEHAVIOR_POOL: list[dict] = [
        {
            "name": "sun_bathe",
            "label": "晒太阳",
            "trigger": {
                "time_range": [10, 14],
                "energy_min": 20,
                "hunger_max": 70,
                "life_stages": ["ADULT"],
                "probability": 0.05,
            },
            "duration_sec": 1200,      # 20 分钟
            "cooldown_sec": 7200,
            "animation": "idle",
            "particles": "feather_shine",
        },
        {
            "name": "flower_visit",
            "label": "访花",
            "trigger": {
                "energy_min": 30,
                "hunger_max": 60,
                "life_stages": ["ADULT"],
                "probability": 0.04,
            },
            "duration_sec": 300,
            "cooldown_sec": 1800,
            "animation": "walk",
            "particles": "rainbow_tail",
        },
        {
            "name": "courtship_dance",
            "label": "求偶舞",
            "trigger": {
                "energy_min": 60,
                "hunger_max": 40,
                "season": "spring",
                "life_stages": ["ADULT"],
                "probability": 0.015,
            },
            "duration_sec": 120,       # 2 分钟
            "cooldown_sec": 3600,
            "animation": "react",
            "particles": "rainbow_tail",
        },
    ]

    __slots__ = ["metamorphosis_stage"]

    def __init__(self, name="彩纹蝶", gender="female", environment=None,
                 birth_time=None, genome_override=None):
        self.metamorphosis_stage = "LARVA"
        genome = self._build_genome(genome_override)
        super().__init__(name=name, species="butterfly", gender=gender,
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
        sleep_cfg = _load_sleep_config().get("butterfly", {})
        for k in ("bedtime", "wakeup_time", "sleep_depth", "wake_on_emergency"):
            if k in sleep_cfg:
                genome[k] = sleep_cfg[k]
        if override:
            for k, v in override.items():
                genome[k] = v
        return genome

    def tick(self) -> None:
        """蝶的 tick 额外处理变态发育。"""
        super().tick()
        # 根据年龄推进变态阶段
        age_days = self.age
        if self.metamorphosis_stage == "LARVA" and age_days > 3:
            self.metamorphosis_stage = "PUPA"
            self._remember("化蛹")
        elif self.metamorphosis_stage == "PUPA" and age_days > 7:
            self.metamorphosis_stage = "ADULT"
            self._remember("羽化成蝶")

    def job_skill(self) -> None:
        """蝶的岗位技能：UI 设计（散播鳞粉）。"""

    # ----- commit 28：行为钩子 -----

    def _on_behavior_tick(self, cfg: dict) -> None:
        """每秒效果。"""
        bname = cfg["name"]
        if bname == "sun_bathe":
            # 晒太阳：能量快速恢复 +0.3/秒
            self.energy = min(100.0, self.energy + 0.3)
            self.mood_score = min(100.0, self.mood_score + 0.05)
        elif bname == "flower_visit":
            # 访花：每 10 秒 mood +1，5% 概率触发"配色灵感"
            self.energy = max(0.0, self.energy - 0.05)
            if random.random() < 0.005:  # 每秒 0.5% 概率
                self._remember("访花时发现了新配色灵感", importance="high")
                self.mood_score = min(100.0, self.mood_score + 5.0)
        elif bname == "courtship_dance":
            # 求偶舞：消耗能量，但 mood 大涨
            self.energy = max(0.0, self.energy - 0.15)
            self.mood_score = min(100.0, self.mood_score + 0.3)

    def _on_behavior_end(self, cfg: dict, reason: str) -> None:
        """结束时记录事件。"""
        bname = cfg["name"]
        if bname == "sun_bathe":
            self._remember("在穹顶最亮处展翅晒太阳", importance="normal")
        elif bname == "flower_visit":
            self._remember("在花丛间访花，传播了鳞粉", importance="normal")
        elif bname == "courtship_dance":
            self._remember("跳了一段 8 字求偶舞", importance="high")

    def _create_child(self, genome, environment, birth_time) -> Butterfly:
        return Butterfly(
            name=f"{self._name_obj}的幼虫",
            gender=random.choice(["male", "female"]),
            environment=environment, birth_time=birth_time,
            genome_override=genome,
        )
