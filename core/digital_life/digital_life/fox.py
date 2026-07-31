"""狡黠狐狸 Fox：代码审查 / 测试员工。

特殊行为：prank_probe 恶作剧探针，偶尔骚扰其他个体。
commit 28：行为池——假装迷路 / 偷看测试结果 / 雪地打滚
"""
from __future__ import annotations

import random

from .digital_life_form import DigitalLifeForm, _load_sleep_config


class Fox(DigitalLifeForm):
    """狡黠狐狸。"""

    SPECIES_TEMPLATE: dict = {
        "species": "fox",
        "default_name": "狡黠狐狸",
        "metabolic_rate": 0.55,
        "hunger_rate": 0.5,
        "max_age_days": 365 * 10,
        "reproduction_age_min_days": 365 * 1,
        "reproduction_age_max_days": 365 * 8,
        "litter_size_min": 1,
        "litter_size_max": 3,
        "temperament": {"active": 0.7, "social": 0.5, "curious": 0.9},
        "color_variation": 0.12,
    }

    # commit 28：狐狸特有行为池
    # 1. 假装迷路：随机选一位同事，故意绕路然后回头狡黠一笑
    # 2. 偷看测试结果：找测试相关同事偷看，被发现耳朵耷拉
    # 3. 雪地打滚：冬季室外（zone=fox 测试迷宫）打滚，留下压痕
    BEHAVIOR_POOL: list[dict] = [
        {
            "name": "fake_lost",
            "label": "假装迷路",
            "trigger": {
                "energy_min": 50,
                "hunger_max": 60,
                "life_stages": ["JUVENILE", "ADULT", "MIDDLE"],
                "probability": 0.015,
            },
            "duration_sec": 30,        # 30 秒
            "cooldown_sec": 600,       # 10 分钟一次
            "animation": "walk",
            "particles": "smirk",
        },
        {
            "name": "peek_test",
            "label": "偷看测试结果",
            "trigger": {
                "energy_min": 40,
                "hunger_max": 70,
                "life_stages": ["ADULT", "MIDDLE"],
                "probability": 0.012,
            },
            "duration_sec": 60,        # 1 分钟
            "cooldown_sec": 1200,      # 20 分钟一次
            "animation": "work",
            "particles": "spy_glasses",
        },
        {
            "name": "snow_roll",
            "label": "雪地打滚",
            "trigger": {
                "energy_min": 60,
                "hunger_max": 50,
                "season": "winter",
                "life_stages": ["JUVENILE", "ADULT", "MIDDLE"],
                "probability": 0.03,
            },
            "duration_sec": 120,       # 2 分钟
            "cooldown_sec": 1800,      # 30 分钟一次
            "animation": "react",
            "particles": "snow_puff",
        },
    ]

    def __init__(self, name="狡黠狐狸", gender="male", environment=None,
                 birth_time=None, genome_override=None):
        genome = self._build_genome(genome_override)
        super().__init__(name=name, species="fox", gender=gender,
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
        sleep_cfg = _load_sleep_config().get("fox", {})
        for k in ("bedtime", "wakeup_time", "sleep_depth", "wake_on_emergency"):
            if k in sleep_cfg:
                genome[k] = sleep_cfg[k]
        if override:
            for k, v in override.items():
                genome[k] = v
        return genome

    def prank_probe(self, target) -> None:
        """恶作剧探针：骚扰目标个体。"""
        if target is None or target is self:
            return
        try:
            with target._lock:
                if target._alive:
                    target._remember(f"被 {self._name_obj} 探针骚扰")
        except Exception:
            pass

    def _socialize(self) -> None:
        """狐狸社交：30% 概率恶作剧。"""
        super()._socialize()
        if self._environment and random.random() < 0.3:
            with self._environment._lock:
                others = [lf for lf in self._environment.population
                          if lf is not self and getattr(lf, "_alive", False)]
            if others:
                self.prank_probe(random.choice(others))

    def job_skill(self) -> None:
        """狐狸的岗位技能：代码审查 / 测试。"""

    # ----- commit 28：行为钩子 -----

    def _on_behavior_start(self, cfg: dict) -> None:
        """行为开始时：选目标同事。"""
        bname = cfg["name"]
        if bname == "fake_lost" and self._environment is not None:
            # 选一位同 zone 同事当"迷路对象"
            others = [lf for lf in self._environment.population
                      if lf is not self and getattr(lf, "_alive", False)
                      and getattr(lf, "current_zone_id", "") == self.current_zone_id]
            self._fake_lost_target = random.choice(others) if others else None
        elif bname == "peek_test" and self._environment is not None:
            # 找测试相关同事（其他 fox 或 hedgehog）
            others = [lf for lf in self._environment.population
                      if lf is not self and getattr(lf, "_alive", False)
                      and getattr(lf, "species", "") in ("fox", "hedgehog")]
            self._peek_target = random.choice(others) if others else None
            self._peek_discovered = False  # 是否被发现

    def _on_behavior_tick(self, cfg: dict) -> None:
        """行为持续时：每秒效果。"""
        bname = cfg["name"]
        if bname == "fake_lost":
            # 消耗能量，向同事靠近
            self.energy = max(0.0, self.energy - 0.15)
        elif bname == "peek_test":
            # 偷看：5% 概率被发现
            self.energy = max(0.0, self.energy - 0.1)
            if not getattr(self, "_peek_discovered", False) and random.random() < 0.05:
                self._peek_discovered = True
                # 被发现 → 耳朵耷拉（mood 下降）
                self.mood_score = max(0.0, self.mood_score - 5.0)
                target = getattr(self, "_peek_target", None)
                if target is not None:
                    try:
                        with target._lock:
                            target._remember(f"{self._name_obj} 偷看了你的测试结果")
                    except Exception:
                        pass
        elif bname == "snow_roll":
            # 雪地打滚：能量缓慢恢复（快乐行为）
            self.energy = min(100.0, self.energy + 0.05)
            self.mood_score = min(100.0, self.mood_score + 0.1)

    def _on_behavior_end(self, cfg: dict, reason: str) -> None:
        """行为结束时：清理临时状态。"""
        bname = cfg["name"]
        if bname == "fake_lost":
            self._remember("假装迷路成功，回头狡黠一笑", importance="normal")
            self._fake_lost_target = None
        elif bname == "peek_test":
            if getattr(self, "_peek_discovered", False):
                self._remember("偷看测试结果被发现了，耳朵耷拉", importance="high")
            else:
                self._remember("成功偷看到了别人的测试结果", importance="normal")
            self._peek_target = None
            self._peek_discovered = False
        elif bname == "snow_roll":
            self._remember("在雪地上美美地打了个滚", importance="normal")

    def _create_child(self, genome, environment, birth_time) -> Fox:
        return Fox(
            name=f"{self._name_obj}的幼崽",
            gender=random.choice(["male", "female"]),
            environment=environment, birth_time=birth_time,
            genome_override=genome,
        )
