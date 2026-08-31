"""灵音雀 Lark：状态监控 / 广播员工。

特殊行为：sing 广播事件，同物种≥3 时代谢减半。
commit 28：行为池——洗澡 / 学舌 / 午间小睡
"""

from __future__ import annotations

import random
from typing import ClassVar

from .digital_life_form import DigitalLifeForm


class Lark(DigitalLifeForm):
    """灵音雀。"""

    SPECIES_TEMPLATE: ClassVar[dict] = {
        "species": "lark",
        "default_name": "灵音雀",
        "metabolic_rate": 0.38,
        "hunger_rate": 0.32,
        "max_age_days": 365 * 6,
        "reproduction_age_min_days": 365 * 1,
        "reproduction_age_max_days": 365 * 5,
        "litter_size_min": 2,
        "litter_size_max": 4,
        "temperament": {"active": 0.6, "social": 0.7, "curious": 0.5},
        "color_variation": 0.12,
    }

    # commit 28：雀特有行为池
    # 1. 洗澡：每天下午在溪流或水盆扑腾洗澡，甩水花
    # 2. 学舌：听到其他同事叫声后模仿一遍，然后得意跳一跳
    # 3. 午间小睡：每天 13-14 固定小憩，头缩进胸羽
    BEHAVIOR_POOL: ClassVar[list[dict]] = [
        {
            "name": "bath",
            "label": "洗澡",
            "trigger": {
                "time_range": [14, 17],
                "energy_min": 30,
                "hunger_max": 70,
                "life_stages": ["JUVENILE", "ADULT", "MIDDLE"],
                "probability": 0.03,
            },
            "duration_sec": 180,  # 3 分钟
            "cooldown_sec": 7200,
            "animation": "react",
            "particles": "snow_puff",
        },
        {
            "name": "mimicry",
            "label": "学舌",
            "trigger": {
                "energy_min": 40,
                "hunger_max": 60,
                "life_stages": ["JUVENILE", "ADULT", "MIDDLE"],
                "probability": 0.02,
            },
            "duration_sec": 30,  # 30 秒
            "cooldown_sec": 1200,
            "animation": "react",
            "particles": "story_bubble",
        },
        {
            "name": "noon_nap",
            "label": "午间小睡",
            "trigger": {
                "time_range": [13, 14],
                "energy_min": 0,
                "hunger_max": 80,
                "life_stages": ["JUVENILE", "ADULT", "MIDDLE", "ELDERLY"],
                "probability": 0.08,
            },
            "duration_sec": 600,  # 10 分钟（一整个小时段）
            "cooldown_sec": 7200,
            "animation": "idle",
            "particles": "feather_shine",
        },
    ]

    def __init__(
        self,
        name="灵音雀",
        gender="female",
        environment=None,
        birth_time=None,
        genome_override=None,
    ):
        genome = self._build_genome(genome_override)
        super().__init__(
            name=name,
            species="lark",
            gender=gender,
            genome=genome,
            environment=environment,
            birth_time=birth_time,
        )

    def sing(self, message: str) -> None:
        """鸣唱广播。"""
        if self._environment is not None:
            self._environment.broadcast_event(
                "lark_sing",
                {
                    "singer": self._name_obj,
                    "message": message,
                },
            )

    def tick(self) -> None:
        """雀的 tick：同物种≥3 时代谢减半。"""
        # 先调 super，然后调整
        super().tick()
        if self._environment is not None:
            with self._environment._lock:
                same_species = sum(
                    1
                    for lf in self._environment.population
                    if getattr(lf, "species", "") == "lark"
                    and getattr(lf, "_alive", False)
                )
            if same_species >= 3:
                # 代谢减半（恢复一点能量）
                self.energy = min(100.0, self.energy + 0.1)

    def job_skill(self) -> None:
        """雀的岗位技能：状态监控 / 广播。"""
        if random.random() < 0.1:
            self.sing("晨鸣广播")

    # ----- commit 28：行为钩子 -----

    def _on_behavior_start(self, cfg: dict) -> None:
        """行为开始：学舌时挑一句广播内容模仿。"""
        if cfg["name"] == "mimicry" and self._environment is not None:
            # 从最近事件中挑一条 lark_sing / daily_event 当模仿内容
            recent = list(self._environment.event_log)[-20:]
            candidates = [
                e
                for e in recent
                if e.get("type") in ("lark_sing", "daily_event")
                or "behavior" in e.get("type", "")
            ]
            if candidates:
                ev = random.choice(candidates)
                self._mimicry_text = (
                    ev.get("data", {}).get("message")
                    or ev.get("data", {}).get("desc")
                    or ev.get("data", {}).get("label")
                    or "叽叽喳喳"
                )
            else:
                self._mimicry_text = "叽叽喳喳"

    def _on_behavior_tick(self, cfg: dict) -> None:
        """每秒效果。"""
        bname = cfg["name"]
        if bname == "bath":
            # 洗澡：能量微降，mood +0.2
            self.energy = max(0.0, self.energy - 0.05)
            self.mood_score = min(100.0, self.mood_score + 0.2)
        elif bname == "mimicry":
            # 学舌：每 10 秒向同事广播一次模仿
            if self._environment is not None and random.random() < 0.1:
                text = getattr(self, "_mimicry_text", "叽叽喳喳")
                self._environment.broadcast_event(
                    "lark_mimicry",
                    {
                        "singer": self._name_obj,
                        "message": f"(模仿) {text}",
                    },
                )
        elif bname == "noon_nap":
            # 午间小睡：能量恢复 +0.3/秒
            self.energy = min(100.0, self.energy + 0.3)

    def _on_behavior_end(self, cfg: dict, reason: str) -> None:
        """结束时记录事件。"""
        bname = cfg["name"]
        if bname == "bath":
            self._remember("在水盆里扑腾洗澡，甩了一身水花", importance="normal")
        elif bname == "mimicry":
            text = getattr(self, "_mimicry_text", "叽叽喳喳")
            self._remember(f"模仿了一句「{text}」，得意地跳了跳", importance="normal")
            self._mimicry_text = None
        elif bname == "noon_nap":
            self._remember("午间小睡片刻，头缩进胸羽", importance="normal")

    def _create_child(self, genome, environment, birth_time) -> Lark:
        return Lark(
            name=f"{self._name_obj}的幼崽",
            gender=random.choice(["male", "female"]),
            environment=environment,
            birth_time=birth_time,
            genome_override=genome,
        )
