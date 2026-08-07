"""智能体生病与急救系统（commit 34）。

零基础读者可以这样理解：
- 智能体不再只是老死，还可能感冒、过劳、心碎、感染
- 病情随时间发展，可能传播给同事
- 监工需要主动救治：强制休息/喂药/隔离/请同事照顾
- 重度流感濒死时必须急救（消耗森林印记 + 多人协作），失败则死亡
- 全公司可能爆发"森林流感"疫情

5 种疾病：
  cold / overwork / data_infection / severe_flu / heartbreak
"""

from __future__ import annotations

import random
import threading
import time

# ----------------------------------------------------------------------
# 疾病定义
# ----------------------------------------------------------------------


class Illness:
    """一种疾病实例（附在某只智能体身上）。

    __slots__ 限制内存占用，零基础读者可以理解为"这只智能体当前得的病"。
    """

    __slots__ = (
        "color",
        "contagion_prob",
        "contagion_radius",
        "contagious",
        "duration_days",
        "efficiency_factor",
        "energy_recovery_factor",
        "fatal",
        "health_delta_per_day",
        "immunity_gain",
        "kind",
        "label",
        "mortality_rate",
        "next_sneeze_ts",
        "sneeze",
        "start_ts",
        "symptoms",
    )

    def __init__(
        self,
        kind: str,
        label: str,
        duration_days: float,
        fatal: bool = False,
        mortality_rate: float = 0.0,
        symptoms: list[str] | None = None,
        health_delta_per_day: float = 0.0,
        energy_recovery_factor: float = 1.0,
        efficiency_factor: float = 1.0,
        contagious: bool = False,
        contagion_radius: float = 3.0,
        contagion_prob: float = 0.2,
        sneeze: bool = False,
        color: str = "#a0a0a0",
        immunity_gain: float = 0.5,
    ) -> None:
        self.kind = kind
        self.label = label
        self.start_ts = time.time()
        self.duration_days = duration_days
        self.fatal = fatal
        self.mortality_rate = mortality_rate
        self.symptoms = symptoms or []
        self.health_delta_per_day = health_delta_per_day
        self.energy_recovery_factor = energy_recovery_factor
        self.efficiency_factor = efficiency_factor
        self.contagious = contagious
        self.contagion_radius = contagion_radius
        self.contagion_prob = contagion_prob
        self.sneeze = sneeze
        self.color = color
        self.immunity_gain = immunity_gain
        self.next_sneeze_ts = time.time() + random.uniform(5, 15)

    def is_expired(self) -> bool:
        """是否已到康复时间。"""
        elapsed_days = (time.time() - self.start_ts) / 86400.0
        return elapsed_days >= self.duration_days

    def elapsed_days(self) -> float:
        return (time.time() - self.start_ts) / 86400.0

    def remaining_days(self) -> float:
        return max(0.0, self.duration_days - self.elapsed_days())

    def should_sneeze(self) -> bool:
        """是否到了打喷嚏时间（用于前端粒子效果）。"""
        if not self.sneeze:
            return False
        now = time.time()
        if now >= self.next_sneeze_ts:
            self.next_sneeze_ts = now + random.uniform(8, 20)
            return True
        return False

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "label": self.label,
            "start_ts": self.start_ts,
            "duration_days": self.duration_days,
            "elapsed_days": round(self.elapsed_days(), 2),
            "remaining_days": round(self.remaining_days(), 2),
            "fatal": self.fatal,
            "mortality_rate": self.mortality_rate,
            "symptoms": list(self.symptoms),
            "health_delta_per_day": self.health_delta_per_day,
            "efficiency_factor": self.efficiency_factor,
            "contagious": self.contagious,
            "color": self.color,
        }


# 疾病工厂：根据 kind 创建 Illness 实例
def create_illness(kind: str) -> Illness | None:
    """根据 kind 创建疾病。

    返回 None 表示 kind 未知。
    """
    table = {
        "cold": {
            "label": "普通感冒",
            "duration_days": 2.5,
            "fatal": False,
            "symptoms": ["打喷嚏", "动作变慢"],
            "health_delta_per_day": -2,
            "energy_recovery_factor": 0.7,
            "efficiency_factor": 0.7,
            "contagious": True,
            "contagon_radius": 3.0,
            "contagion_prob": 0.2,
            "sneeze": True,
            "color": "#a0c4e8",
            "immunity_gain": 0.5,
        },
        "overwork": {
            "label": "过劳",
            "duration_days": 1.0,
            "fatal": False,
            "symptoms": ["疲惫", "效率下降"],
            "health_delta_per_day": -5,
            "energy_recovery_factor": 0.5,
            "efficiency_factor": 0.5,
            "contagious": False,
            "sneeze": False,
            "color": "#8a8a8a",
            "immunity_gain": 0.2,
        },
        "data_infection": {
            "label": "数据感染",
            "duration_days": 1.5,
            "fatal": False,
            "symptoms": ["行为混乱", "对话错乱"],
            "health_delta_per_day": -1,
            "energy_recovery_factor": 0.8,
            "efficiency_factor": 0.4,
            "contagious": True,
            "contagon_radius": 2.0,
            "contagion_prob": 0.1,
            "sneeze": False,
            "color": "#a020a0",
            "immunity_gain": 0.6,
        },
        "severe_flu": {
            "label": "重度流感",
            "duration_days": 6.0,
            "fatal": True,
            "mortality_rate": 0.3,
            "symptoms": ["高烧", "卧床不起"],
            "health_delta_per_day": -10,
            "energy_recovery_factor": 0.3,
            "efficiency_factor": 0.1,
            "contagious": True,
            "contagon_radius": 3.5,
            "contagion_prob": 0.4,
            "sneeze": True,
            "color": "#d04040",
            "immunity_gain": 0.8,
        },
        "heartbreak": {
            "label": "心碎症",
            "duration_days": 10.0,
            "fatal": False,
            "symptoms": ["情感封闭", "拒绝社交"],
            "health_delta_per_day": -1,
            "energy_recovery_factor": 0.9,
            "efficiency_factor": 0.5,
            "contagious": False,
            "sneeze": False,
            "color": "#8060a0",
            "immunity_gain": 0.3,
        },
    }
    cfg = table.get(kind)
    if cfg is None:
        return None
    return Illness(kind=kind, **cfg)


# ----------------------------------------------------------------------
# 疾病系统（单例）
# ----------------------------------------------------------------------


class IllnessSystem:
    """全局疾病系统：触发、传播、急救、疫情。

    单例模式：通过 get_illness_system() 获取。
    """

    _instance: IllnessSystem | None = None
    _instance_lock = threading.Lock()

    # 触发概率（每小时检查一次）
    TRIGGER_RAIN_COLD_PROB = 0.05  # 雨雪天户外久 → 感冒 5%
    TRIGGER_OVERWORK_PROB = 0.15  # 连续工作 > 8h → 过劳 15%
    TRIGGER_DATA_INFECT_PROB = 0.03  # 戒备猬失职 → 数据感染 3%
    TRIGGER_SEVERE_FLU_PROB = 0.20  # 冬季 + 感冒未治愈 → 重度流感 20%
    TRIGGER_HEARTBREAK_PROB = 0.50  # 最亲密同事死亡 → 心碎 50%
    TRIGGER_MEMORY_HEARTBREAK_PROB = 0.02  # 翻阅旧记忆 → 心碎 2%（联动）

    # 急救参数
    RESCUE_COST_MARKS = 20  # 急救消耗 20 森林印记
    RESCUE_SUCCESS_RATE = 0.8  # 急救成功率 80%
    RESCUE_WINDOW_HOURS = 2.0  # 濒死后 2 小时内必须急救

    # 疫情参数
    EPIDEMIC_MIN_SICK = 3  # 3 人以上同时感冒 → 疫情
    EPIDEMIC_DURATION_DAYS = 4.0  # 疫情持续 3-5 天
    EPIDEMIC_ANNUAL_PROB = 0.002  # 每小时检查时年化概率约 1-2 次

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._last_trigger_check: float = 0.0
        self._last_contagion_check: float = 0.0
        self._epidemic_active: bool = False
        self._epidemic_start_ts: float = 0.0
        self._epidemic_label: str = ""
        self._rescue_in_progress: dict[str, dict] = {}  # {agent_id: {...}}

    @classmethod
    def get_instance(cls) -> IllnessSystem:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ---------------- 触发检查（每小时） ----------------

    def check_triggers(
        self, population: list, weather: str = "sunny", season: str = "spring"
    ) -> list[dict]:
        """检查每只智能体是否触发生病。返回新触发的疾病事件列表。"""
        now = time.time()
        # 每小时检查一次
        if now - self._last_trigger_check < 3600:
            return []
        self._last_trigger_check = now
        events: list[dict] = []
        with self._lock:
            for lf in population:
                if not getattr(lf, "_alive", False):
                    continue
                # 已经有病了就跳过
                if getattr(lf, "illness", None) is not None:
                    continue
                # 物种特殊免疫
                species = getattr(lf, "species", "")
                # 渡鸦对数据感染免疫
                if species == "raven":
                    pass
                # 1. 雨雪天户外 → 感冒
                zone_id = getattr(lf, "current_zone_id", "") or ""
                is_outdoor = "outdoor" in zone_id or zone_id == ""
                if (
                    weather in ("light_rain", "heavy_rain", "snow")
                    and is_outdoor
                    and random.random() < self.TRIGGER_RAIN_COLD_PROB
                ):
                    self._infect(lf, "cold", events)
                    continue
                # 渡鸦对数据感染免疫，跳过数据感染检查
                if species == "raven":
                    continue
                # 2. 连续工作 > 8h → 过劳
                action = getattr(lf, "current_action", None)
                action_str = ""
                try:
                    action_str = action.value if action else ""
                except AttributeError:
                    action_str = str(action) if action else ""
                work_start = getattr(lf, "_work_continuous_start_ts", 0)
                if action_str == "WORK" and work_start > 0:
                    work_hours = (now - work_start) / 3600
                    if work_hours > 8 and random.random() < self.TRIGGER_OVERWORK_PROB:
                        self._infect(lf, "overwork", events)
                        continue
                # 3. 冬季 + 感冒未治愈 → 重度流感
                # （这里简化：当前是 cold 且冬季 → 概率升级）
                # 4. 数据感染（戒备猬失职时）—— 简化随机
                if (
                    species != "raven"
                    and random.random() < self.TRIGGER_DATA_INFECT_PROB * 0.01
                ):
                    self._infect(lf, "data_infection", events)
                    continue
                # 5. 心碎症：由死亡事件回调触发，这里不主动检查
            # 疫情检查
            self._check_epidemic(population, events)
        return events

    def _infect(self, lf, kind: str, events: list[dict]) -> None:
        """让 lf 感染 kind 病。"""
        illness = create_illness(kind)
        if illness is None:
            return
        try:
            lf.illness = illness
        except Exception:
            return
        # 写入持久记忆（联动 1：生病 → 核心记忆）
        try:
            from core.digital_life.persistent_memory import (
                get_memory_manager,
            )

            agent_id = f"{lf.species}-{lf._name_obj}"
            get_memory_manager().record_core_event(
                agent_id,
                f"生病了：{illness.label}（{illness.symptoms[0] if illness.symptoms else ''}）",
                tags=["illness", kind],
                meta={"kind": kind, "duration_days": illness.duration_days},
            )
        except Exception:
            pass
        # 主动消息通知监工
        try:
            from core.digital_life.active_messaging import trigger_active_message

            trigger_active_message(
                "health_crisis",
                sender=getattr(lf, "_name_obj", "?"),
                sender_species=getattr(lf, "species", "?"),
                detail=f"{illness.label}：{', '.join(illness.symptoms[:2])}",
                agent=lf,
            )
        except Exception:
            pass
        events.append(
            {
                "type": "illness_onset",
                "agent_name": getattr(lf, "_name_obj", "?"),
                "species": getattr(lf, "species", "?"),
                "kind": kind,
                "label": illness.label,
                "ts": time.time(),
            }
        )

    # ---------------- 心碎症（由死亡事件触发） ----------------

    def trigger_heartbreak_for_bereaved(self, deceased, population: list) -> list[dict]:
        """某智能体死亡后，触发亲密同事的心碎症。

        Args:
            deceased: 死亡的生命体
            population: 全种群
        """
        events: list[dict] = []
        dec_id = (
            f"{getattr(deceased, 'species', '?')}-{getattr(deceased, '_name_obj', '?')}"
        )
        with self._lock:
            for lf in population:
                if lf is deceased or not getattr(lf, "_alive", False):
                    continue
                if getattr(lf, "illness", None) is not None:
                    continue
                # 检查关系亲密程度
                rels = getattr(lf, "relationships", {}) or {}
                rel = rels.get(dec_id) or rels.get(getattr(deceased, "_name_obj", ""))
                affection = 0.0
                if isinstance(rel, dict):
                    affection = rel.get("affection", 0)
                if affection >= 0.6 and random.random() < self.TRIGGER_HEARTBREAK_PROB:
                    self._infect(lf, "heartbreak", events)
                    # 心碎的 sadness 锁定
                    try:
                        lf.emotional_state["sadness"] = max(
                            0.8, lf.emotional_state.get("sadness", 0)
                        )
                    except Exception:
                        pass
        return events

    # ---------------- 联动：翻阅旧记忆触发短暂心碎 ----------------

    def trigger_memory_heartbreak(self, lf) -> dict | None:
        """翻阅旧记忆时，极低概率触发短暂心碎（2 小时）。"""
        if getattr(lf, "illness", None) is not None:
            return None
        if random.random() > self.TRIGGER_MEMORY_HEARTBREAK_PROB:
            return None
        # 创建一个缩短版的心碎（2 小时 = 0.083 天）
        illness = create_illness("heartbreak")
        if illness is None:
            return None
        illness.duration_days = 2 / 24  # 2 小时
        try:
            lf.illness = illness
        except Exception:
            return None
        try:
            lf.emotional_state["sadness"] = max(
                0.7, lf.emotional_state.get("sadness", 0)
            )
        except Exception:
            pass
        return {
            "type": "memory_heartbreak",
            "agent_name": getattr(lf, "_name_obj", "?"),
            "species": getattr(lf, "species", "?"),
            "ts": time.time(),
        }

    # ---------------- 疾病传播（每 10 分钟） ----------------

    def check_contagion(self, population: list) -> list[dict]:
        """检查近距离智能体间的疾病传播。"""
        now = time.time()
        # 10 分钟检查一次
        if now - self._last_contagion_check < 600:
            return []
        self._last_contagion_check = now
        events: list[dict] = []
        with self._lock:
            # 找出所有生病且传染的
            contagious = []
            healthy = []
            for lf in population:
                if not getattr(lf, "_alive", False):
                    continue
                ill = getattr(lf, "illness", None)
                if ill is not None and ill.contagious:
                    contagious.append(lf)
                elif ill is None:
                    healthy.append(lf)
            for sick in contagious:
                sick_ill = sick.illness
                sick_zone = getattr(sick, "current_zone_id", "")
                for target in healthy:
                    if target is sick:
                        continue
                    # 必须同 zone
                    if getattr(target, "current_zone_id", "") != sick_zone:
                        continue
                    # 物种免疫
                    if sick_ill.kind == "data_infection" and target.species == "raven":
                        continue
                    # 戒备猬防御姿态降低感染概率
                    prob = sick_ill.contagion_prob
                    if target.species == "hedgehog":
                        prob *= 0.5
                    if random.random() < prob:
                        # 传播成功
                        self._infect(target, sick_ill.kind, events)
        return events

    # ---------------- 疾病进展（每秒） ----------------

    def tick_disease_progress(self, population: list, dt: float = 1.0) -> list[dict]:
        """每秒推进：健康下降、自愈、死亡检查。"""
        events: list[dict] = []
        with self._lock:
            for lf in population:
                if not getattr(lf, "_alive", False):
                    continue
                ill = getattr(lf, "illness", None)
                if ill is None:
                    continue
                # 健康下降（按 day 计算到秒）
                if ill.health_delta_per_day != 0:
                    delta = ill.health_delta_per_day * dt / 86400.0
                    try:
                        lf.health = max(0.0, min(100.0, lf.health + delta * 100))
                    except Exception:
                        pass
                # 重症濒死检查（健康 < 10 且致命）
                if ill.fatal and ill.health_delta_per_day < 0:
                    if lf.health < 10:
                        # 进入"濒死待急救"状态
                        if lf.species not in self._rescue_in_progress:
                            self._rescue_in_progress[lf._name_obj] = {
                                "start_ts": time.time(),
                                "kind": ill.kind,
                                "agent_name": lf._name_obj,
                            }
                            events.append(
                                {
                                    "type": "rescue_needed",
                                    "agent_name": lf._name_obj,
                                    "species": lf.species,
                                    "disease": ill.label,
                                    "ts": time.time(),
                                }
                            )
                            # 紧急桌面通知
                            try:
                                from core.digital_life.desktop_pet import (
                                    push_desktop_notification,
                                )

                                push_desktop_notification(
                                    f"急救警报：{lf._name_obj} 濒危！",
                                    f"{ill.label}导致健康仅剩 {lf.health:.0f}，"
                                    f"请在 2 小时内急救。",
                                    priority="urgent",
                                )
                            except Exception:
                                pass
                # 自愈检查
                if ill.is_expired():
                    self._cure(lf, reason="natural", events=events)
        # 检查急救超时
        self._check_rescue_timeout(population, events)
        return events

    def _cure(self, lf, reason: str, events: list[dict]) -> None:
        """治愈 lf 的疾病。"""
        ill = getattr(lf, "illness", None)
        if ill is None:
            return
        try:
            lf.illness = None
        except Exception:
            pass
        # 写入持久记忆（康复事件 → 核心记忆）
        try:
            from core.digital_life.persistent_memory import get_memory_manager

            agent_id = f"{lf.species}-{lf._name_obj}"
            get_memory_manager().record_core_event(
                agent_id,
                f"康复了：{ill.label}（原因：{reason}）",
                tags=["illness_recover", ill.kind, reason],
                meta={"kind": ill.kind, "reason": reason},
            )
        except Exception:
            pass
        # 心碎症康复 → 获得"坚韧"标签
        if ill.kind == "heartbreak":
            try:
                tags = lf.trauma_events
                if tags is not None and "坚韧" not in tags:
                    tags.append("坚韧")
            except Exception:
                pass
        events.append(
            {
                "type": "illness_cured",
                "agent_name": getattr(lf, "_name_obj", "?"),
                "species": getattr(lf, "species", "?"),
                "kind": ill.kind,
                "label": ill.label,
                "reason": reason,
                "ts": time.time(),
            }
        )

    def _check_rescue_timeout(self, population: list, events: list[dict]) -> None:
        """检查急救是否超时（2 小时未救 → 死亡）。"""
        now = time.time()
        to_remove = []
        for agent_name, info in list(self._rescue_in_progress.items()):
            if now - info["start_ts"] > self.RESCUE_WINDOW_HOURS * 3600:
                # 超时：找到这只智能体，判定死亡
                for lf in population:
                    if getattr(lf, "_name_obj", "") == agent_name and getattr(
                        lf, "_alive", False
                    ):
                        try:
                            lf.health = 0
                            lf._die("disease")
                        except Exception:
                            pass
                        events.append(
                            {
                                "type": "rescue_failed",
                                "agent_name": agent_name,
                                "disease": info.get("kind", ""),
                                "ts": now,
                            }
                        )
                        break
                to_remove.append(agent_name)
        for name in to_remove:
            self._rescue_in_progress.pop(name, None)

    # ---------------- 监工救治接口 ----------------

    def force_rest(self, lf) -> dict:
        """强制休息：锁定 REST 直到健康恢复到 60。"""
        ill = getattr(lf, "illness", None)
        if ill is None:
            return {"ok": False, "reason": "未生病"}
        try:
            lf.current_action = None  # 清空工作
            lf.resting_until = time.time() + 3600  # 休息 1 小时
            # 加速恢复
            ill.duration_days = min(ill.duration_days, ill.elapsed_days() + 0.5)
        except Exception:
            pass
        return {
            "ok": True,
            "action": "force_rest",
            "agent": getattr(lf, "_name_obj", "?"),
        }

    def give_medicine(self, lf, cost_marks: int = 5) -> dict:
        """喂药：消耗 5 印记，加速恢复 50%。"""
        ill = getattr(lf, "illness", None)
        if ill is None:
            return {"ok": False, "reason": "未生病"}
        # 缩短剩余时间 50%
        remaining = ill.remaining_days()
        ill.duration_days = ill.elapsed_days() + remaining * 0.5
        # 立刻加一点健康
        try:
            lf.health = min(100.0, lf.health + 10)
        except Exception:
            pass
        return {
            "ok": True,
            "action": "give_medicine",
            "agent": getattr(lf, "_name_obj", "?"),
            "cost_marks": cost_marks,
        }

    def isolate(self, lf) -> dict:
        """隔离：把智能体移到休息室（rest_area）。"""
        try:
            lf.current_zone_id = "rest_area"
            # 取消传染性（隔离后不再传染）
            ill = getattr(lf, "illness", None)
            if ill is not None:
                ill.contagious = False
        except Exception:
            pass
        return {"ok": True, "action": "isolate", "agent": getattr(lf, "_name_obj", "?")}

    def assign_caregiver(self, patient, caregiver) -> dict:
        """指派同事照顾：恢复速度 +30%。"""
        ill = getattr(patient, "illness", None)
        if ill is None:
            return {"ok": False, "reason": "未生病"}
        remaining = ill.remaining_days()
        ill.duration_days = ill.elapsed_days() + remaining * 0.7  # 缩短 30%
        # 照顾者 affection +
        try:
            from core.digital_life.persistent_memory import get_memory_manager

            agent_id = f"{caregiver.species}-{caregiver._name_obj}"
            get_memory_manager().record_core_event(
                agent_id,
                f"照顾了生病的 {patient._name_obj}（{ill.label}）",
                tags=["caregiver", ill.kind],
            )
        except Exception:
            pass
        return {
            "ok": True,
            "action": "assign_caregiver",
            "patient": getattr(patient, "_name_obj", "?"),
            "caregiver": getattr(caregiver, "_name_obj", "?"),
        }

    def emergency_rescue(self, patient, helpers: list, cost_marks: int = 20) -> dict:
        """急救：消耗 20 印记 + 多人协作，成功率 80%。

        Args:
            patient: 濒死智能体
            helpers: 协助的智能体列表（建议含鹿/渡鸦/海狸）
            cost_marks: 消耗的森林印记
        """
        ill = getattr(patient, "illness", None)
        if ill is None or not ill.fatal:
            return {"ok": False, "reason": "无需急救"}
        # 协助者越多成功率越高（每个 +5%，封顶 95%）
        success_rate = self.RESCUE_SUCCESS_RATE + min(0.15, len(helpers) * 0.05)
        success_rate = min(0.95, success_rate)
        if random.random() < success_rate:
            # 成功：直接治愈
            self._cure(patient, reason="rescue", events=[])
            # trust 永久 +0.3
            try:
                patient.fondness = min(100, (patient.fondness or 50) + 30)
            except Exception:
                pass
            # 写入"重生记忆"（永久核心记忆）
            try:
                from core.digital_life.persistent_memory import get_memory_manager

                agent_id = f"{patient.species}-{patient._name_obj}"
                get_memory_manager().record_core_event(
                    agent_id,
                    f"经历了濒死急救后重生（{ill.label}），对监工的信任永久加深",
                    tags=["rescue_rebirth", "trauma", "permanent"],
                    meta={"helpers": [getattr(h, "_name_obj", "?") for h in helpers]},
                )
            except Exception:
                pass
            # 移除急救中状态
            self._rescue_in_progress.pop(getattr(patient, "_name_obj", ""), None)
            return {
                "ok": True,
                "result": "success",
                "agent": getattr(patient, "_name_obj", "?"),
                "cost_marks": cost_marks,
                "helpers": [getattr(h, "_name_obj", "?") for h in helpers],
            }
        else:
            # 失败：智能体死亡
            try:
                patient.health = 0
                patient._die("rescue_failed")
            except Exception:
                pass
            self._rescue_in_progress.pop(getattr(patient, "_name_obj", ""), None)
            return {
                "ok": True,
                "result": "failed",
                "agent": getattr(patient, "_name_obj", "?"),
                "cost_marks": cost_marks,
            }

    # ---------------- 疫情事件 ----------------

    def _check_epidemic(self, population: list, events: list[dict]) -> None:
        """检查是否触发疫情。"""
        sick_count = sum(
            1
            for lf in population
            if getattr(lf, "_alive", False)
            and getattr(lf, "illness", None) is not None
            and getattr(lf, "illness", None).kind in ("cold", "severe_flu")
        )
        if (
            not self._epidemic_active
            and sick_count >= self.EPIDEMIC_MIN_SICK
            and random.random() < self.EPIDEMIC_ANNUAL_PROB
        ):
            self._epidemic_active = True
            self._epidemic_start_ts = time.time()
            self._epidemic_label = "森林流感"
            events.append(
                {
                    "type": "epidemic_start",
                    "label": self._epidemic_label,
                    "sick_count": sick_count,
                    "ts": time.time(),
                }
            )
        elif self._epidemic_active:
            # 检查疫情是否结束
            elapsed_days = (time.time() - self._epidemic_start_ts) / 86400
            if elapsed_days >= self.EPIDEMIC_DURATION_DAYS:
                self._epidemic_active = False
                events.append(
                    {
                        "type": "epidemic_end",
                        "label": self._epidemic_label,
                        "ts": time.time(),
                    }
                )

    def is_epidemic_active(self) -> bool:
        return self._epidemic_active

    # ---------------- 快照 ----------------

    def snapshot(self, population: list) -> dict:
        """供前端查询。"""
        sick_list = []
        rescue_list = []
        with self._lock:
            for lf in population:
                ill = getattr(lf, "illness", None)
                if ill is not None and getattr(lf, "_alive", False):
                    sick_list.append(
                        {
                            "agent_name": getattr(lf, "_name_obj", "?"),
                            "species": getattr(lf, "species", "?"),
                            "zone_id": getattr(lf, "current_zone_id", ""),
                            "health": round(float(getattr(lf, "health", 0)), 1),
                            "illness": ill.to_dict(),
                        }
                    )
            for name, info in self._rescue_in_progress.items():
                rescue_list.append(
                    {
                        "agent_name": name,
                        "elapsed_hours": round(
                            (time.time() - info["start_ts"]) / 3600, 2
                        ),
                        "remaining_hours": round(
                            self.RESCUE_WINDOW_HOURS
                            - (time.time() - info["start_ts"]) / 3600,
                            2,
                        ),
                    }
                )
        return {
            "sick_count": len(sick_list),
            "sick_agents": sick_list,
            "rescue_pending": rescue_list,
            "epidemic_active": self._epidemic_active,
            "epidemic_label": self._epidemic_label if self._epidemic_active else "",
            "rescue_cost_marks": self.RESCUE_COST_MARKS,
            "medicine_cost_marks": 5,
        }


# ----------------------------------------------------------------------
# 模块级便捷函数
# ----------------------------------------------------------------------


def get_illness_system() -> IllnessSystem:
    return IllnessSystem.get_instance()


def update_illness(
    population: list, dt: float = 1.0, weather: str = "sunny", season: str = "spring"
) -> list[dict]:
    """每秒调用：推进疾病进展 + 周期性检查触发/传播。"""
    sys = get_illness_system()
    events = sys.tick_disease_progress(population, dt)
    # 触发检查（内部每小时一次）
    events.extend(sys.check_triggers(population, weather=weather, season=season))
    # 传播检查（内部每 10 分钟一次）
    events.extend(sys.check_contagion(population))
    return events


def snapshot_illness(population: list) -> dict:
    return get_illness_system().snapshot(population)


# 同步写入核心记忆的便捷函数（避免循环导入）
def record_core_event_sync(
    agent_id: str, text: str, tags: list[str] | None = None
) -> None:
    try:
        from core.digital_life.persistent_memory import get_memory_manager

        get_memory_manager().record_core_event(agent_id, text, tags=tags)
    except Exception:
        pass
