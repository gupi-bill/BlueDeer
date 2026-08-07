"""较真松鼠 Squirrel：代码生成员工。

特殊行为：cache_food 缓存食物，饥荒时优先消耗自己的缓存。
commit 28：行为池——藏坚果 / 忘记藏哪儿了 / 炫耀代码
"""

from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import random
import time

from .digital_life_form import DigitalLifeForm


class Squirrel(DigitalLifeForm):
    """较真松鼠。"""

    SPECIES_TEMPLATE: dict = {
        "species": "squirrel",
        "default_name": "较真松鼠",
        "metabolic_rate": 0.6,
        "hunger_rate": 0.5,
        "max_age_days": 365 * 8,
        "reproduction_age_min_days": 365 * 1,
        "reproduction_age_max_days": 365 * 6,
        "litter_size_min": 2,
        "litter_size_max": 4,
        "temperament": {"active": 0.8, "social": 0.4, "curious": 0.7},
        "color_variation": 0.15,
    }

    # commit 28：松鼠特有行为池
    # 1. 藏坚果：能量充足时埋代码坚果（每秒 +0.1 food_cache）
    # 2. 忘记藏哪儿了：20% 概率翻找无果（消耗能量但不加 food_cache）
    # 3. 炫耀代码：工作完成后向同事展示，提升双方 mood_score
    BEHAVIOR_POOL: list[dict] = [
        {
            "name": "cache_food",
            "label": "藏坚果",
            "trigger": {
                "energy_min": 70,
                "hunger_max": 50,
                "life_stages": ["JUVENILE", "ADULT", "MIDDLE"],
                "probability": 0.04,  # 每次检查 4% 触发
            },
            "duration_sec": 180,  # 3 分钟
            "cooldown_sec": 600,  # 10 分钟一次
            "animation": "work",
            "particles": "nut_bury",
        },
        {
            "name": "forget_cache",
            "label": "忘记藏哪儿了",
            "trigger": {
                "energy_min": 40,
                "hunger_max": 60,
                "life_stages": ["JUVENILE", "ADULT", "MIDDLE"],
                "probability": 0.008,  # 0.8% 触发（稀有）
            },
            "duration_sec": 120,  # 2 分钟
            "cooldown_sec": 1800,  # 30 分钟一次
            "animation": "walk",
            "particles": "panic_sweat",
        },
        {
            "name": "show_off_code",
            "label": "炫耀代码",
            "trigger": {
                "energy_min": 50,
                "hunger_max": 60,
                "life_stages": ["ADULT", "MIDDLE"],
                "probability": 0.02,
            },
            "duration_sec": 60,  # 1 分钟
            "cooldown_sec": 900,  # 15 分钟一次
            "animation": "react",
            "particles": "rainbow_tail",
        },
    ]

    __slots__ = ["food_cache"]

    def __init__(
        self,
        name="较真松鼠",
        gender="female",
        environment=None,
        birth_time=None,
        genome_override=None,
    ):
        self.food_cache = 0.0
        genome = self._build_genome(genome_override)
        super().__init__(
            name=name,
            species="squirrel",
            gender=gender,
            genome=genome,
            environment=environment,
            birth_time=birth_time,
        )

    def cache_food(self, amount: float) -> None:
        """把食物存入颊袋缓存。"""
        self.food_cache += amount

    def _eat(self) -> None:
        """松鼠进食：优先消耗自己的缓存。"""
        if self.food_cache > 0:
            eat = min(self.food_cache, 10.0)
            self.food_cache -= eat
            self.hunger = max(0.0, self.hunger - eat)
            self.energy = min(100.0, self.energy + eat * 0.5)
            self._remember(f"吃缓存 {eat:.1f}")
        else:
            super()._eat()

    def job_skill(self) -> None:
        """松鼠的岗位技能：写代码（简化）。"""
        # 缓存食物的工作副产品
        if random.random() < 0.05:
            self.cache_food(1.0)

    # ----- commit 28：行为钩子 -----

    def _on_behavior_tick(self, cfg: dict) -> None:
        """行为持续时每秒调用：实现具体效果。"""
        bname = cfg["name"]
        if bname == "cache_food":
            # 藏坚果：每秒 +0.1 food_cache（3 分钟 ≈ 18 单位）
            self.food_cache += 0.1
        elif bname == "forget_cache":
            # 翻找：消耗能量，不加 food_cache
            self.energy = max(0.0, self.energy - 0.2)
        elif bname == "show_off_code":
            # 炫耀：每 10 秒找一位同事 +mood
            if int(time.time()) % 10 == 0 and self._environment is not None:
                others = [
                    lf
                    for lf in self._environment.population
                    if lf is not self
                    and getattr(lf, "_alive", False)
                    and getattr(lf, "current_zone_id", "") == self.current_zone_id
                ]
                if others:
                    target = random.choice(others)
                    try:
                        with target._lock:
                            target.mood_score = min(100.0, target.mood_score + 1.0)
                    except Exception:
                        logger.exception("Exception in block")
                        pass

    def _on_behavior_end(self, cfg: dict, reason: str) -> None:
        """行为结束时：记录特殊事件。"""
        bname = cfg["name"]
        if bname == "cache_food":
            self._remember(
                f"埋下了 {self.food_cache:.1f} 颗代码坚果", importance="high"
            )
        elif bname == "forget_cache" and reason == "finished":
            self._remember("翻找了半天也没找到自己藏的坚果…", importance="normal")
        elif bname == "show_off_code":
            self._remember("向同事炫耀了自己的代码成果", importance="normal")

    def _create_child(self, genome, environment, birth_time) -> Squirrel:
        return Squirrel(
            name=f"{self._name_obj}的幼崽",
            gender=random.choice(["male", "female"]),
            environment=environment,
            birth_time=birth_time,
            genome_override=genome,
        )
