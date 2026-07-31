"""单例物种招募系统 RecruitSystem。

零基础读者可以这样理解：每个物种同时只能有 1 只员工活着。
死了就空着，需要走"招募"流程才能补充新个体。

招募规则（用户确认）：
1. 默认手动：监工在招募面板点击"开始招募"才启动
2. 超时自动：24 小时现实时间未手动启动 → 系统自动招募
3. 无资源消耗：只等时间，不扣森林印记/食物
4. 招募等待期：60 秒（biosphere 时间），等待结束后新个体入职
5. 新个体属性：随机性别、基于物种默认基因±10% 变异、birth_time=now
6. 招募期间：工位灰色蒙版 + 招募图标，新员工从大厅门口走入

状态机：
    ALIVE（活着）→ DEAD（死亡）→ PENDING（等待招募）→
    RECRUITING（招募中，60秒）→ ALIVE（新个体入职）
"""
from __future__ import annotations

import enum
import random
import threading
import time
from typing import Any


class SpeciesState(enum.Enum):
    """物种招募状态。"""
    ALIVE = "ALIVE"              # 当前有活体
    DEAD = "DEAD"                # 死亡，等待监工招募
    PENDING = "PENDING"          # 监工已触发招募，等待冷却
    RECRUITING = "RECRUITING"    # 招募中（走入动画期间）


# 默认招募参数
DEFAULT_RECRUIT_COOLDOWN = 60.0       # 招募冷却 60 秒
DEFAULT_AUTO_RECRUIT_TIMEOUT = 86400.0  # 24 小时现实时间自动招募


class RecruitSystem:
    """单例物种招募系统。

    跟踪 11 物种的存活状态，死亡后进入等待招募，
    监工手动招募或 24 小时超时自动招募。
    """

    __slots__ = [
        "_auto_timeout",
        "_death_times",
        "_environment",
        "_lock",
        "_names_map",
        "_on_recruit_complete",
        "_recruit_cooldown",
        "_recruit_start_times",
        "_species_cls_map",
        "_states",
    ]

    def __init__(
        self,
        species_cls_map: dict[str, type],
        names_map: dict[str, str],
        environment,
        recruit_cooldown: float = DEFAULT_RECRUIT_COOLDOWN,
        auto_timeout: float = DEFAULT_AUTO_RECRUIT_TIMEOUT,
    ) -> None:
        """初始化招募系统。

        Args:
            species_cls_map: {species: DigitalLifeForm 子类}。
            names_map: {species: 默认名字}（如 "deer": "鹿·忧郁"）。
            environment: 共享 Environment 实例。
            recruit_cooldown: 招募冷却时间（秒）。
            auto_timeout: 死亡后多少秒自动招募（默认 24 小时）。
        """
        self._states: dict[str, SpeciesState] = {
            sp: SpeciesState.ALIVE for sp in species_cls_map}
        self._death_times: dict[str, float] = {}
        self._recruit_start_times: dict[str, float] = {}
        self._lock = threading.RLock()
        self._recruit_cooldown = recruit_cooldown
        self._auto_timeout = auto_timeout
        self._species_cls_map = dict(species_cls_map)
        self._names_map = dict(names_map)
        self._environment = environment
        self._on_recruit_complete = None  # 回调：新员工入职后通知 Biosphere

    # ------------------------------------------------------------------
    # 事件回调
    # ------------------------------------------------------------------

    def on_death(self, species: str) -> None:
        """某物种死亡时调用。"""
        with self._lock:
            if species in self._states:
                self._states[species] = SpeciesState.DEAD
                self._death_times[species] = time.time()

    def set_on_recruit_complete(self, callback) -> None:
        """设置新员工入职完成回调（Biosphere 用）。"""
        self._on_recruit_complete = callback

    # ------------------------------------------------------------------
    # 监工操作
    # ------------------------------------------------------------------

    def start_recruit(self, species: str) -> dict:
        """监工手动启动招募。

        Args:
            species: 物种名。

        Returns:
            操作结果 dict。
        """
        with self._lock:
            if species not in self._states:
                return {"ok": False, "reason": "未知物种"}
            state = self._states[species]
            if state == SpeciesState.ALIVE:
                return {"ok": False, "reason": "该物种仍存活"}
            if state in (SpeciesState.PENDING, SpeciesState.RECRUITING):
                return {"ok": False, "reason": "已在招募中"}
            # DEAD → PENDING
            self._states[species] = SpeciesState.PENDING
            self._recruit_start_times[species] = time.time()
            return {
                "ok": True,
                "species": species,
                "state": self._states[species].value,
                "cooldown_sec": self._recruit_cooldown,
            }

    # ------------------------------------------------------------------
    # tick 推进
    # ------------------------------------------------------------------

    def tick(self) -> list[dict]:
        """每秒调用一次，推进招募状态机。

        Returns:
            本 tick 完成的招募事件列表（供 Biosphere 处理）。
        """
        completed: list[dict] = []
        with self._lock:
            now = time.time()
            for species, state in list(self._states.items()):
                if state == SpeciesState.DEAD:
                    # 检查超时自动招募
                    death_time = self._death_times.get(species, 0)
                    if now - death_time >= self._auto_timeout:
                        self._states[species] = SpeciesState.PENDING
                        self._recruit_start_times[species] = now
                        completed.append({
                            "type": "auto_recruit_started",
                            "species": species,
                            "reason": "24h_timeout",
                        })
                elif state == SpeciesState.PENDING:
                    # 检查冷却是否到
                    start = self._recruit_start_times.get(species, 0)
                    if now - start >= self._recruit_cooldown:
                        # 冷却结束 → RECRUITING（短暂状态，立即生成新个体）
                        self._states[species] = SpeciesState.RECRUITING
                        completed.append({
                            "type": "recruit_complete",
                            "species": species,
                        })
        return completed

    def complete_recruit(self, species: str) -> Any:
        """完成招募：生成新个体并返回（Biosphere 调用）。

        新个体属性：
        - 性别：随机 male/female
        - 基因：基于物种 SPECIES_TEMPLATE ±10% 变异
        - birth_time: now
        - 名字：沿用物种默认名字（如"鹿·忧郁"）

        Returns:
            新创建的 DigitalLifeForm 实例，或 None（状态不对时）。
        """
        with self._lock:
            if species not in self._states:
                return None
            if self._states[species] != SpeciesState.RECRUITING:
                return None
            cls = self._species_cls_map.get(species)
            if cls is None:
                return None
            # 随机性别
            gender = random.choice(["male", "female"])
            # 沿用物种默认名字
            name = self._names_map.get(species, species)
            # 生成新个体（cls 内部会基于 SPECIES_TEMPLATE 生成 genome）
            new_lf = cls(name=name, gender=gender, environment=self._environment)
            # ±10% 基因变异
            self._mutate_genome(new_lf, 0.1)
            # 状态回 ALIVE
            self._states[species] = SpeciesState.ALIVE
            self._recruit_start_times.pop(species, None)
            self._death_times.pop(species, None)
            return new_lf

    def _mutate_genome(self, life_form: Any, rate: float) -> None:
        """对生命体的 genome 做 ±rate 变异。"""
        genome = getattr(life_form, "genome", None)
        if not genome:
            return
        for key in ("metabolic_rate", "hunger_rate"):
            if key in genome:
                orig = genome[key]
                delta = orig * rate * (random.random() * 2 - 1)
                genome[key] = max(0.1, orig + delta)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_state(self, species: str) -> str:
        """获取某物种当前状态。"""
        with self._lock:
            return self._states.get(species, SpeciesState.ALIVE).value

    def get_all_states(self) -> dict[str, str]:
        """获取所有物种状态。"""
        with self._lock:
            return {sp: s.value for sp, s in self._states.items()}

    def get_recruit_progress(self, species: str) -> dict:
        """获取招募进度。"""
        with self._lock:
            state = self._states.get(species, SpeciesState.ALIVE)
            if state == SpeciesState.PENDING:
                start = self._recruit_start_times.get(species, 0)
                elapsed = time.time() - start
                return {
                    "species": species,
                    "state": state.value,
                    "elapsed_sec": round(elapsed, 1),
                    "remaining_sec": max(
                        0.0, self._recruit_cooldown - elapsed),
                    "progress_pct": min(
                        100.0, elapsed / self._recruit_cooldown * 100),
                }
            if state == SpeciesState.DEAD:
                death_time = self._death_times.get(species, 0)
                elapsed = time.time() - death_time
                return {
                    "species": species,
                    "state": state.value,
                    "since_death_sec": round(elapsed, 1),
                    "auto_recruit_in_sec": max(
                        0.0, self._auto_timeout - elapsed),
                }
            return {"species": species, "state": state.value}

    def status(self) -> dict:
        """返回招募系统状态。"""
        with self._lock:
            alive_count = sum(
                1 for s in self._states.values()
                if s == SpeciesState.ALIVE)
            dead_count = sum(
                1 for s in self._states.values()
                if s == SpeciesState.DEAD)
            pending_count = sum(
                1 for s in self._states.values()
                if s == SpeciesState.PENDING)
            recruiting_count = sum(
                1 for s in self._states.values()
                if s == SpeciesState.RECRUITING)
            return {
                "total_species": len(self._states),
                "alive": alive_count,
                "dead": dead_count,
                "pending": pending_count,
                "recruiting": recruiting_count,
                "states": {sp: s.value for sp, s in self._states.items()},
                "recruit_cooldown_sec": self._recruit_cooldown,
                "auto_timeout_sec": self._auto_timeout,
            }
