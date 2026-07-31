"""勤恳海狸 Beaver：架构设计 / 部署员工。

特殊行为：一夫一妻（partner_id），build_dam 修水坝。
commit 28：行为池——修补水坝 / 游泳 / 啃咬磨牙
"""
from __future__ import annotations

import random

from .digital_life_form import DigitalLifeForm, _load_sleep_config


class Beaver(DigitalLifeForm):
    """勤恳海狸。"""

    SPECIES_TEMPLATE: dict = {
        "species": "beaver",
        "default_name": "勤恳海狸",
        "metabolic_rate": 0.5,
        "hunger_rate": 0.45,
        "max_age_days": 365 * 15,
        "reproduction_age_min_days": 365 * 2,
        "reproduction_age_max_days": 365 * 12,
        "litter_size_min": 1,
        "litter_size_max": 3,
        "temperament": {"active": 0.6, "social": 0.5, "curious": 0.4},
        "color_variation": 0.1,
    }

    # commit 28：海狸特有行为池
    # 1. 修补水坝：每天检查加固水坝，添加新木料像素
    # 2. 游泳：夏天炎热时跳进溪流游泳，拍水花
    # 3. 啃咬磨牙：能量充足但无事时啃咬木制家具磨牙
    BEHAVIOR_POOL: list[dict] = [
        {
            "name": "repair_dam",
            "label": "修补水坝",
            "trigger": {
                "energy_min": 50,
                "hunger_max": 60,
                "life_stages": ["ADULT", "MIDDLE"],
                "probability": 0.02,
            },
            "duration_sec": 600,       # 10 分钟
            "cooldown_sec": 7200,      # 2 小时一次
            "animation": "work",
            "particles": "nut_bury",
        },
        {
            "name": "swim",
            "label": "游泳",
            "trigger": {
                "energy_min": 40,
                "hunger_max": 60,
                "season": "summer",
                "life_stages": ["JUVENILE", "ADULT", "MIDDLE"],
                "probability": 0.025,
            },
            "duration_sec": 300,       # 5 分钟
            "cooldown_sec": 3600,
            "animation": "react",
            "particles": "snow_puff",
        },
        {
            "name": "gnaw",
            "label": "啃咬磨牙",
            "trigger": {
                "energy_min": 70,
                "hunger_max": 40,
                "life_stages": ["ADULT", "MIDDLE"],
                "probability": 0.015,
            },
            "duration_sec": 180,       # 3 分钟
            "cooldown_sec": 1800,
            "animation": "work",
            "particles": "nut_bury",
        },
    ]

    def __init__(self, name="勤恳海狸", gender="male", environment=None,
                 birth_time=None, genome_override=None):
        genome = self._build_genome(genome_override)
        super().__init__(name=name, species="beaver", gender=gender,
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
        sleep_cfg = _load_sleep_config().get("beaver", {})
        for k in ("bedtime", "wakeup_time", "sleep_depth", "wake_on_emergency"):
            if k in sleep_cfg:
                genome[k] = sleep_cfg[k]
        if override:
            for k, v in override.items():
                genome[k] = v
        return genome

    def reproduce(self, partner):
        """海狸一夫一妻：必须已绑定 partner。"""
        # 简化：直接调基类
        return super().reproduce(partner)

    def build_dam(self) -> None:
        """修水坝（增加环境资源）。"""
        if self._environment is not None:
            with self._environment._lock:
                self._environment.food_available = min(
                    2000.0, self._environment.food_available + 5.0)
            self._remember("修水坝 +5 资源")

    def job_skill(self) -> None:
        """海狸的岗位技能：架构设计 / 部署。"""
        if random.random() < 0.05:
            self.build_dam()

    # ----- commit 28：行为钩子 -----

    def _on_behavior_tick(self, cfg: dict) -> None:
        """每秒效果。"""
        bname = cfg["name"]
        if bname == "repair_dam":
            # 修补水坝：每秒调 build_dam（+5 资源/次）的 1/5 概率版
            self.energy = max(0.0, self.energy - 0.1)
            if random.random() < 0.05 and self._environment is not None:
                with self._environment._lock:
                    self._environment.food_available = min(
                        2000.0, self._environment.food_available + 1.0)
        elif bname == "swim":
            # 游泳：能量恢复，mood +0.1
            self.energy = min(100.0, self.energy + 0.1)
            self.mood_score = min(100.0, self.mood_score + 0.1)
        elif bname == "gnaw":
            # 啃咬：消耗能量，hunger 微降（磨牙满足感）
            self.energy = max(0.0, self.energy - 0.15)
            self.hunger = max(0.0, self.hunger - 0.05)
            self.mood_score = min(100.0, self.mood_score + 0.05)

    def _on_behavior_end(self, cfg: dict, reason: str) -> None:
        """结束时记录事件。"""
        bname = cfg["name"]
        if bname == "repair_dam":
            self._remember("检查并加固了水坝，添加了新木料", importance="normal")
        elif bname == "swim":
            self._remember("在溪流里畅游了一番", importance="normal")
        elif bname == "gnaw":
            # 随机啃咬的家具
            item = random.choice(["桌角", "椅子腿", "门框", "铅笔", "木条"])
            self._remember(f"啃咬{item}磨了磨门牙", importance="normal")

    def _create_child(self, genome, environment, birth_time) -> Beaver:
        return Beaver(
            name=f"{self._name_obj}的幼崽",
            gender=random.choice(["male", "female"]),
            environment=environment, birth_time=birth_time,
            genome_override=genome,
        )
