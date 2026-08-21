"""雪兔 Hare：审计 / 资源核算员工。

特殊行为：count_tokens 数 token，30% 额外产胎概率。
commit 28：行为池——挖雪洞 / 蹬后腿 / 数数
"""

from __future__ import annotations

import random
from typing import ClassVar

from .digital_life_form import DigitalLifeForm


class Hare(DigitalLifeForm):
    """雪兔。"""

    SPECIES_TEMPLATE: ClassVar[dict] = {
        "species": "hare",
        "default_name": "雪兔",
        "metabolic_rate": 0.45,
        "hunger_rate": 0.4,
        "max_age_days": 365 * 9,
        "reproduction_age_min_days": 365 * 1,
        "reproduction_age_max_days": 365 * 7,
        "litter_size_min": 2,
        "litter_size_max": 6,
        "temperament": {"active": 0.7, "social": 0.4, "curious": 0.5},
        "color_variation": 0.1,
    }

    # commit 28：雪兔特有行为池
    # 1. 挖雪洞：冬季在算盘雪原挖洞钻进去只露耳朵，保暖同时监听数据
    # 2. 蹬后腿：开心时突然高高跳起，空中转体（即时动作）
    # 3. 数数：空闲时耳朵微抖，吐小数字气泡默默统计资源
    BEHAVIOR_POOL: ClassVar[list[dict]] = [
        {
            "name": "dig_snow_hole",
            "label": "挖雪洞",
            "trigger": {
                "energy_min": 30,
                "hunger_max": 60,
                "season": "winter",
                "life_stages": ["ADULT", "MIDDLE"],
                "probability": 0.02,
            },
            "duration_sec": 900,  # 15 分钟
            "cooldown_sec": 7200,
            "animation": "idle",
            "particles": "snow_puff",
        },
        {
            "name": "kick_leg",
            "label": "蹬后腿",
            "trigger": {
                "energy_min": 60,
                "hunger_max": 50,
                "life_stages": ["JUVENILE", "ADULT", "MIDDLE"],
                "probability": 0.012,
            },
            "duration_sec": 5,  # 即时动作
            "cooldown_sec": 600,
            "animation": "react",
            "particles": "smirk",
        },
        {
            "name": "counting",
            "label": "数数",
            "trigger": {
                "energy_min": 50,
                "hunger_max": 50,
                "life_stages": ["ADULT", "MIDDLE", "ELDERLY"],
                "probability": 0.015,
            },
            "duration_sec": 180,  # 3 分钟
            "cooldown_sec": 1800,
            "animation": "idle",
            "particles": "story_bubble",
        },
    ]

    def __init__(
        self,
        name="雪兔",
        gender="male",
        environment=None,
        birth_time=None,
        genome_override=None,
    ):
        genome = self._build_genome(genome_override)
        super().__init__(
            name=name,
            species="hare",
            gender=gender,
            genome=genome,
            environment=environment,
            birth_time=birth_time,
        )

    def reproduce(self, partner):
        """雪兔 30% 额外产胎概率：繁殖出双倍幼崽。

        注意：第二次调 super().reproduce 会再扣双方 energy，
        可能因能量不足失败，这是可接受的设计。
        """
        child = super().reproduce(partner)
        if child is not None and random.random() < 0.3:
            extra = super().reproduce(partner)
            if extra is not None:
                self._remember("雪兔额外产胎")
        return child

    def count_tokens(self, text: str) -> int:
        """数 token（简化：按词数）。"""
        return len(text.split())

    def job_skill(self) -> None:
        """雪兔的岗位技能：审计 / 资源核算。"""

    # ----- commit 28：行为钩子 -----

    def _on_behavior_start(self, cfg: dict) -> None:
        """行为开始：数数时初始化计数起点。"""
        if cfg["name"] == "counting":
            self._count_start = random.randint(10000, 99999)

    def _on_behavior_tick(self, cfg: dict) -> None:
        """每秒效果。"""
        bname = cfg["name"]
        if bname == "dig_snow_hole":
            # 雪洞保暖：能量恢复 +0.1/秒
            self.energy = min(100.0, self.energy + 0.1)
        elif bname == "kick_leg":
            # 蹬后腿：消耗能量，mood +2
            self.energy = max(0.0, self.energy - 0.5)
            self.mood_score = min(100.0, self.mood_score + 2.0)
        elif bname == "counting":
            # 数数：每秒 +1（默默统计）
            self.energy = max(0.0, self.energy - 0.02)

    def _on_behavior_end(self, cfg: dict, reason: str) -> None:
        """结束时记录事件。"""
        bname = cfg["name"]
        if bname == "dig_snow_hole":
            self._remember("挖了个雪洞钻进去保暖", importance="normal")
        elif bname == "kick_leg":
            self._remember("开心地蹬了蹬后腿，高高跳起", importance="normal")
        elif bname == "counting":
            start = getattr(self, "_count_start", 10000)
            end = start + 180  # 3 分钟 ≈ 180 秒
            self._remember(f"默默数到了 {end}", importance="normal")

    def _create_child(self, genome, environment, birth_time) -> Hare:
        return Hare(
            name=f"{self._name_obj}的幼崽",
            gender=random.choice(["male", "female"]),
            environment=environment,
            birth_time=birth_time,
            genome_override=genome,
        )
