"""小獾 Badger：工具路由员工。

特殊行为：dig_burrow 挖地道，explore 发现资源。
commit 28：行为池——挖新地道 / 倒着走 / 冲洗爪子
"""
from __future__ import annotations

import random

from .digital_life_form import DigitalLifeForm, _load_sleep_config


class Badger(DigitalLifeForm):
    """小獾。"""

    SPECIES_TEMPLATE: dict = {
        "species": "badger",
        "default_name": "小獾",
        "metabolic_rate": 0.42,
        "hunger_rate": 0.38,
        "max_age_days": 365 * 12,
        "reproduction_age_min_days": 365 * 1,
        "reproduction_age_max_days": 365 * 10,
        "litter_size_min": 1,
        "litter_size_max": 3,
        "temperament": {"active": 0.5, "social": 0.4, "curious": 0.6},
        "color_variation": 0.1,
    }

    # commit 28：獾特有行为池
    # 1. 挖新地道：空闲时随机选软地面挖掘，可能连通或死胡同
    # 2. 倒着走：偶尔倒着走几步（天性）
    # 3. 冲洗爪子：在溪流或饮水机旁用水冲洗前爪
    BEHAVIOR_POOL: list[dict] = [
        {
            "name": "dig_new_tunnel",
            "label": "挖新地道",
            "trigger": {
                "energy_min": 50,
                "hunger_max": 60,
                "life_stages": ["ADULT", "MIDDLE"],
                "probability": 0.02,
            },
            "duration_sec": 600,       # 10 分钟
            "cooldown_sec": 3600,
            "animation": "work",
            "particles": "nut_bury",
        },
        {
            "name": "walk_backwards",
            "label": "倒着走",
            "trigger": {
                "energy_min": 50,
                "hunger_max": 60,
                "life_stages": ["JUVENILE", "ADULT", "MIDDLE"],
                "probability": 0.01,
            },
            "duration_sec": 15,        # 短暂
            "cooldown_sec": 600,
            "animation": "walk",
            "particles": "smirk",
        },
        {
            "name": "wash_paws",
            "label": "冲洗爪子",
            "trigger": {
                "energy_min": 40,
                "hunger_max": 60,
                "life_stages": ["ADULT", "MIDDLE"],
                "probability": 0.015,
            },
            "duration_sec": 60,        # 1 分钟
            "cooldown_sec": 1800,
            "animation": "idle",
            "particles": "snow_puff",
        },
    ]

    def __init__(self, name="小獾", gender="male", environment=None,
                 birth_time=None, genome_override=None):
        genome = self._build_genome(genome_override)
        super().__init__(name=name, species="badger", gender=gender,
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
        sleep_cfg = _load_sleep_config().get("badger", {})
        for k in ("bedtime", "wakeup_time", "sleep_depth", "wake_on_emergency"):
            if k in sleep_cfg:
                genome[k] = sleep_cfg[k]
        if override:
            for k, v in override.items():
                genome[k] = v
        return genome

    def dig_burrow(self) -> None:
        """挖地道（增强环境容量，简化为加资源）。"""
        if self._environment is not None:
            with self._environment._lock:
                self._environment.food_available = min(
                    2000.0, self._environment.food_available + 2.0)
            self._remember("挖地道 +2 资源")

    def _explore(self) -> None:
        """獾的探索：30% 概率挖地道。"""
        super()._explore()
        if random.random() < 0.3:
            self.dig_burrow()

    def job_skill(self) -> None:
        """獾的岗位技能：工具路由。"""

    # ----- commit 28：行为钩子 -----

    def _on_behavior_start(self, cfg: dict) -> None:
        """行为开始：挖新地道时决定结局（连通 vs 死胡同）。"""
        if cfg["name"] == "dig_new_tunnel":
            self._tunnel_success = random.random() < 0.6  # 60% 概率连通

    def _on_behavior_tick(self, cfg: dict) -> None:
        """每秒效果。"""
        bname = cfg["name"]
        if bname == "dig_new_tunnel":
            # 挖地道：消耗能量，每秒 0.3% 概率给环境 +1 资源
            self.energy = max(0.0, self.energy - 0.2)
            if random.random() < 0.003 and self._environment is not None:
                with self._environment._lock:
                    self._environment.food_available = min(
                        2000.0, self._environment.food_available + 1.0)
        elif bname == "walk_backwards":
            # 倒着走：消耗能量
            self.energy = max(0.0, self.energy - 0.1)
        elif bname == "wash_paws":
            # 冲洗爪子：mood +0.2/秒
            self.mood_score = min(100.0, self.mood_score + 0.2)
            self.energy = max(0.0, self.energy - 0.05)

    def _on_behavior_end(self, cfg: dict, reason: str) -> None:
        """结束时记录事件。"""
        bname = cfg["name"]
        if bname == "dig_new_tunnel":
            if getattr(self, "_tunnel_success", False):
                self._remember("挖通了一条新地道，连通了两个入口", importance="high")
            else:
                self._remember("挖了个死胡同，下次再试", importance="normal")
            self._tunnel_success = None
        elif bname == "walk_backwards":
            self._remember("天性发作，倒着走了几步", importance="normal")
        elif bname == "wash_paws":
            self._remember("在溪流边把前爪搓洗干净了", importance="normal")

    def _create_child(self, genome, environment, birth_time) -> Badger:
        return Badger(
            name=f"{self._name_obj}的幼崽",
            gender=random.choice(["male", "female"]),
            environment=environment, birth_time=birth_time,
            genome_override=genome,
        )
