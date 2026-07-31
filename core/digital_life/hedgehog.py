"""戒备猬 Hedgehog：安全审计员工。

特殊行为：health < 30 时自动防御蜷缩（defending=True）。
commit 28：行为池——巡视安全 / 缩球晒太阳 / 收集小物件
"""
from __future__ import annotations

import random

from .digital_life_form import DigitalLifeForm


class Hedgehog(DigitalLifeForm):
    """戒备猬。"""

    SPECIES_TEMPLATE: dict = {
        "species": "hedgehog",
        "default_name": "戒备猬",
        "metabolic_rate": 0.4,
        "hunger_rate": 0.35,
        "max_age_days": 365 * 7,
        "reproduction_age_min_days": 365 * 1,
        "reproduction_age_max_days": 365 * 5,
        "litter_size_min": 2,
        "litter_size_max": 5,
        "temperament": {"active": 0.4, "social": 0.3, "curious": 0.4},
        "color_variation": 0.08,
    }

    # commit 28：猬特有行为池
    # 1. 巡视安全：每隔 4 小时沿围墙走一圈，背刺半竖，遇异常全竖
    # 2. 缩球晒太阳：堡垒门口阳光足时，缩成刺球晒太阳，轻微滚动
    # 3. 收集小物件：随机捡起地上小东西（笔/回形针/螺丝），用刺叉起来带回堡垒
    BEHAVIOR_POOL: list[dict] = [
        {
            "name": "patrol_safety",
            "label": "巡视安全",
            "trigger": {
                "energy_min": 50,
                "hunger_max": 60,
                "life_stages": ["ADULT", "MIDDLE"],
                "probability": 0.015,
            },
            "duration_sec": 600,       # 10 分钟
            "cooldown_sec": 14400,     # 4 小时一次
            "animation": "walk",
            "particles": "sparkle",
        },
        {
            "name": "ball_sun_bathe",
            "label": "缩球晒太阳",
            "trigger": {
                "time_range": [10, 16],
                "energy_min": 30,
                "hunger_max": 70,
                "life_stages": ["JUVENILE", "ADULT", "MIDDLE", "ELDERLY"],
                "probability": 0.03,
            },
            "duration_sec": 600,       # 10 分钟
            "cooldown_sec": 3600,
            "animation": "idle",
            "particles": "feather_shine",
        },
        {
            "name": "collect_item",
            "label": "收集小物件",
            "trigger": {
                "energy_min": 50,
                "hunger_max": 60,
                "life_stages": ["JUVENILE", "ADULT", "MIDDLE"],
                "probability": 0.02,
            },
            "duration_sec": 120,       # 2 分钟
            "cooldown_sec": 1800,
            "animation": "work",
            "particles": "nut_bury",
        },
    ]

    __slots__ = ["defending"]

    def __init__(self, name="戒备猬", gender="female", environment=None,
                 birth_time=None, genome_override=None):
        self.defending = False
        genome = self._build_genome(genome_override)
        super().__init__(name=name, species="hedgehog", gender=gender,
                         genome=genome, environment=environment, birth_time=birth_time)

    def tick(self) -> None:
        """猬的 tick 额外处理防御状态。"""
        super().tick()
        # health < 30 自动防御
        if self.health < 30 and not self.defending:
            self.defending = True
            self._remember("蜷缩防御")
        elif self.health >= 50 and self.defending:
            self.defending = False
            self._remember("解除防御")

    def job_skill(self) -> None:
        """猬的岗位技能：安全审计。"""

    # ----- commit 28：行为钩子 -----

    def _on_behavior_tick(self, cfg: dict) -> None:
        """每秒效果。"""
        bname = cfg["name"]
        if bname == "patrol_safety":
            # 巡视：能量消耗，背刺半竖
            self.energy = max(0.0, self.energy - 0.1)
            # 5% 概率遇异常 → 完全竖刺（defending=True 短暂）
            if random.random() < 0.005:
                self.defending = True
        elif bname == "ball_sun_bathe":
            # 缩球晒太阳：能量恢复 +0.15/秒
            self.energy = min(100.0, self.energy + 0.15)
            self.mood_score = min(100.0, self.mood_score + 0.05)
        elif bname == "collect_item":
            # 收集：消耗能量
            self.energy = max(0.0, self.energy - 0.1)

    def _on_behavior_end(self, cfg: dict, reason: str) -> None:
        """结束时记录事件。"""
        bname = cfg["name"]
        if bname == "patrol_safety":
            self._remember("沿围墙巡视一圈，未发现异常", importance="normal")
            self.defending = False  # 巡视完恢复
        elif bname == "ball_sun_bathe":
            self._remember("缩成刺球在门口晒太阳", importance="normal")
        elif bname == "collect_item":
            # 随机捡起一个小物件
            item = random.choice(["笔", "回形针", "螺丝", "橡皮", "图钉"])
            self._remember(f"用刺叉起了一个{item}带回堡垒", importance="normal")

    def _create_child(self, genome, environment, birth_time) -> Hedgehog:
        return Hedgehog(
            name=f"{self._name_obj}的幼崽",
            gender=random.choice(["male", "female"]),
            environment=environment, birth_time=birth_time,
            genome_override=genome,
        )
