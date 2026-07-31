"""渡鸦 Raven：归档 / 记忆员工。

特殊行为：跨代记忆，die 时把记忆写入 raven_archive 全局列表。
commit 28：行为池——梳羽 / 摆弄闪亮物 / 讲古 / 高飞眺望
"""
from __future__ import annotations

import random
import time

from .digital_life_form import DigitalLifeForm, _load_sleep_config

# 渡鸦跨代记忆档案（模块级全局，所有渡鸦共享）
raven_archive: list = []


class Raven(DigitalLifeForm):
    """渡鸦。"""

    SPECIES_TEMPLATE: dict = {
        "species": "raven",
        "default_name": "渡鸦",
        "metabolic_rate": 0.35,
        "hunger_rate": 0.3,
        "max_age_days": 365 * 40,  # 渡鸦很长寿
        "reproduction_age_min_days": 365 * 3,
        "reproduction_age_max_days": 365 * 30,
        "litter_size_min": 1,
        "litter_size_max": 2,
        "temperament": {"active": 0.4, "social": 0.3, "curious": 0.7},
        "color_variation": 0.05,
    }

    # commit 28：渡鸦特有行为池（4 个）
    # 1. 梳理羽毛：早晚各一次（6-9 / 18-21），用喙整理飞羽
    # 2. 摆弄闪亮物：随机叼起金属物品观赏
    # 3. 讲古：夜晚 20-24 时，向周围同事讲述已故同事往事
    # 4. 高飞眺望：飞到最高处俯瞰公司，更新全局记忆
    BEHAVIOR_POOL: list[dict] = [
        {
            "name": "groom_feathers",
            "label": "梳理羽毛",
            "trigger": {
                "time_range": [6, 9],   # 早晨 6-9 点
                "energy_min": 40,
                "hunger_max": 70,
                "life_stages": ["JUVENILE", "ADULT", "MIDDLE", "ELDERLY"],
                "probability": 0.06,
            },
            "duration_sec": 300,       # 5 分钟
            "cooldown_sec": 7200,      # 2 小时一次（早晚各一次靠时间范围）
            "animation": "idle",
            "particles": "feather_shine",
        },
        {
            "name": "groom_feathers_evening",
            "label": "梳理羽毛",
            "trigger": {
                "time_range": [18, 21],  # 傍晚 18-21 点
                "energy_min": 40,
                "hunger_max": 70,
                "life_stages": ["JUVENILE", "ADULT", "MIDDLE", "ELDERLY"],
                "probability": 0.06,
            },
            "duration_sec": 300,
            "cooldown_sec": 7200,
            "animation": "idle",
            "particles": "feather_shine",
        },
        {
            "name": "play_shiny",
            "label": "摆弄闪亮物",
            "trigger": {
                "energy_min": 50,
                "hunger_max": 60,
                "life_stages": ["ADULT", "MIDDLE", "ELDERLY"],
                "probability": 0.01,
            },
            "duration_sec": 180,       # 3 分钟
            "cooldown_sec": 1800,      # 30 分钟一次
            "animation": "work",
            "particles": "sparkle",
        },
        {
            "name": "tell_story",
            "label": "讲古",
            "trigger": {
                "time_range": [20, 24], # 夜晚 20-24 点
                "energy_min": 30,
                "hunger_max": 70,
                "life_stages": ["MIDDLE", "ELDERLY"],
                "probability": 0.025,
            },
            "duration_sec": 300,       # 5 分钟
            "cooldown_sec": 3600,      # 1 小时一次
            "animation": "idle",
            "particles": "story_bubble",
        },
        {
            "name": "fly_high",
            "label": "高飞眺望",
            "trigger": {
                "energy_min": 60,
                "hunger_max": 50,
                "life_stages": ["ADULT", "MIDDLE"],
                "probability": 0.008,
            },
            "duration_sec": 120,       # 2 分钟
            "cooldown_sec": 7200,      # 2 小时一次
            "animation": "work",
            "particles": "feather_drop",
        },
    ]

    def __init__(self, name="渡鸦", gender="female", environment=None,
                 birth_time=None, genome_override=None):
        genome = self._build_genome(genome_override)
        super().__init__(name=name, species="raven", gender=gender,
                         genome=genome, environment=environment, birth_time=birth_time)
        # 继承档案
        self._inherit_archive()

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
        sleep_cfg = _load_sleep_config().get("raven", {})
        for k in ("bedtime", "wakeup_time", "sleep_depth", "wake_on_emergency"):
            if k in sleep_cfg:
                genome[k] = sleep_cfg[k]
        if override:
            for k, v in override.items():
                genome[k] = v
        return genome

    def _inherit_archive(self) -> None:
        """继承前代渡鸦的档案（前 5 条）。"""
        for entry in raven_archive[-5:]:
            self.memory_long_term.append(dict(entry))

    def recall(self, keyword: str = "") -> list:
        """检索记忆。"""
        if not keyword:
            return list(self.memory_long_term)[-10:]
        return [m for m in self.memory_long_term if keyword in m.get("text", "")]

    def _die(self, reason: str) -> None:
        """死亡时把记忆写入档案。"""
        # 先把当前记忆存档
        archive_entry = {
            "name": self._name_obj,
            "memory_count": len(self.memory_long_term),
            "last_memory": (self.memory_long_term[-1] if self.memory_long_term else None),
        }
        raven_archive.append(archive_entry)
        super()._die(reason)

    def job_skill(self) -> None:
        """渡鸦的岗位技能：归档记忆。"""
        self._remember("归档本时段记忆")

    # ----- commit 28：行为钩子 -----

    def _on_behavior_start(self, cfg: dict) -> None:
        """行为开始时：选讲古内容 / 闪亮物。"""
        bname = cfg["name"]
        if bname == "tell_story":
            # 从档案里挑一段往事讲
            if raven_archive:
                entry = random.choice(raven_archive[-10:])
                self._story_subject = entry.get("name", "前代渡鸦")
            else:
                self._story_subject = None
        elif bname == "play_shiny":
            # 随机挑一个闪亮物
            self._shiny_object = random.choice(
                ["钥匙", "硬币", "USB 接口头", "螺丝", "回形针", "纽扣电池"])

    def _on_behavior_tick(self, cfg: dict) -> None:
        """行为持续时：每秒效果。"""
        bname = cfg["name"]
        if bname == "groom_feathers" or bname == "groom_feathers_evening":
            # 梳羽：能量缓慢恢复，每秒 +0.05
            self.energy = min(100.0, self.energy + 0.05)
        elif bname == "play_shiny":
            # 玩闪亮物：心情上升
            self.mood_score = min(100.0, self.mood_score + 0.1)
        elif bname == "tell_story":
            # 讲古：每 30 秒写入一条听众记忆
            if int(time.time()) % 30 == 0 and self._environment is not None:
                # 找同 zone 的听众
                listeners = [lf for lf in self._environment.population
                             if lf is not self and getattr(lf, "_alive", False)
                             and getattr(lf, "current_zone_id", "") == self.current_zone_id]
                subject = getattr(self, "_story_subject", None) or "前代渡鸦"
                for listener in listeners[:3]:  # 最多 3 个听众
                    try:
                        with listener._lock:
                            listener._remember(
                                f"听 {self._name_obj} 讲述了 {subject} 的往事",
                                importance="normal")
                    except Exception:
                        pass
        elif bname == "fly_high":
            # 高飞：能量消耗，但记忆 +1
            self.energy = max(0.0, self.energy - 0.2)
            if random.random() < 0.05:
                self._remember("从高空俯瞰公司，记下了新布局", importance="normal")

    def _on_behavior_end(self, cfg: dict, reason: str) -> None:
        """行为结束时：记录特殊事件。"""
        bname = cfg["name"]
        if bname in ("groom_feathers", "groom_feathers_evening"):
            self._remember("仔细梳理了每一根飞羽", importance="normal")
        elif bname == "play_shiny":
            obj = getattr(self, "_shiny_object", "闪亮物")
            self._remember(f"摆弄了一会儿 {obj}，又放回原处", importance="normal")
            self._shiny_object = None
        elif bname == "tell_story":
            subject = getattr(self, "_story_subject", None) or "前代渡鸦"
            self._remember(f"讲述了 {subject} 的往事", importance="high")
            self._story_subject = None
        elif bname == "fly_high":
            self._remember("完成高空俯瞰，更新了全局记忆", importance="high")

    def _create_child(self, genome, environment, birth_time) -> Raven:
        return Raven(
            name=f"{self._name_obj}的幼崽",
            gender=random.choice(["male", "female"]),
            environment=environment, birth_time=birth_time,
            genome_override=genome,
        )
