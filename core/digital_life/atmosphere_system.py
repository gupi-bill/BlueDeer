"""commit 33：情感氛围可视化系统。

零基础读者可以这样理解：
- 每只动物周围有一圈"情绪光环"——快乐是金色、悲伤是蓝色、焦虑是灰色脉冲、满足是绿色。
- 当两只动物靠近到光环重叠，光环颜色会缓慢融合，直观看到情感传染。
- 如果某个区域长时间充满某种情绪（如休息室一直很满足），地面会染上极淡的色调，形成"情感地标"。
- 在快乐区域会偶尔飘起金色像素光点，悲伤区域会飘落淡蓝碎屑。

设计要点：
1. 单例 AtmosphereSystem，全局共享状态。
2. 每秒扫描种群，计算每个生命体的光环颜色和半径。
3. 区域氛围累积：每个 zone 维护一个 {情绪: 强度} 字典，按时间衰减+累积。
4. 渲染数据生成：snapshot() 返回前端可直接绘制的数据结构。
5. 性能：仅在情感值变化 > 0.1 时重新计算；粒子总数上限 50。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import random
import threading
import time

from typing_extensions import Self

# ====================================================================
# 情感 → 颜色映射
# ====================================================================
# 6 维情感对应的 RGB（前端用 rgba 显示，alpha 由强度决定）
EMOTION_COLORS: dict[str, tuple[int, int, int]] = {
    "joy": (255, 196, 87),  # 暖金色
    "sadness": (130, 170, 230),  # 淡蓝色
    "anxiety": (160, 160, 170),  # 灰色
    "contentment": (140, 210, 150),  # 柔绿色
    "loneliness": (180, 180, 200),  # 灰蓝
    "curiosity": (200, 150, 220),  # 紫色
}

# 主导情感触发阈值（超过该值才显现为光环）
EMOTION_AURA_THRESHOLD: dict[str, float] = {
    "joy": 0.6,
    "sadness": 0.5,
    "anxiety": 0.6,
    "contentment": 0.7,
    "loneliness": 0.8,
    "curiosity": 0.8,
}


def get_dominant_emotion(emotional_state: dict) -> tuple[str, float] | None:
    """返回主导情感及其值。无显著情感时返回 None。

    主导情感需达到 EMOTION_AURA_THRESHOLD 才会显现。
    """
    candidates: list[tuple[str, float]] = []
    for emo, val in emotional_state.items():
        threshold = EMOTION_AURA_THRESHOLD.get(emo, 0.8)
        if val >= threshold:
            candidates.append((emo, float(val)))
    if not candidates:
        return None
    # 取最大值
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0]


def get_secondary_emotion(
    emotional_state: dict, exclude: str
) -> tuple[str, float] | None:
    """返回次要情感（用于光环边缘渐变）。"""
    candidates: list[tuple[str, float]] = []
    for emo, val in emotional_state.items():
        if emo == exclude:
            continue
        threshold = EMOTION_AURA_THRESHOLD.get(emo, 0.8)
        if val >= threshold:
            candidates.append((emo, float(val)))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0]


def emotion_to_rgba(emo: str, intensity: float, alpha_mult: float = 1.0) -> str:
    """把情感 + 强度转为 CSS rgba 字符串。"""
    r, g, b = EMOTION_COLORS.get(emo, (200, 200, 200))
    alpha = max(0.0, min(1.0, intensity * 0.45 * alpha_mult))
    return f"rgba({r},{g},{b},{alpha:.3f})"


# ====================================================================
# 氛围粒子
# ====================================================================
# 粒子类型：golden_float（金色上升）/ blue_fall（蓝色飘落）/ gray_jitter（灰色抖动）
class AtmosphereParticle:
    __slots__ = ("kind", "life", "max_life", "size", "vx", "vy", "x", "y")

    def __init__(self, x: float, y: float, kind: str):
        self.x = x
        self.y = y
        self.kind = kind
        if kind == "golden_float":
            # 金色光点：缓慢上升
            self.vx = (random.random() - 0.5) * 0.05
            self.vy = -0.05 - random.random() * 0.05
            self.size = 2 + random.random() * 2
            self.max_life = 2.5 + random.random() * 2.0
        elif kind == "blue_fall":
            # 蓝色碎屑：缓慢飘落
            self.vx = (random.random() - 0.5) * 0.08
            self.vy = 0.03 + random.random() * 0.04
            self.size = 1 + random.random() * 1.5
            self.max_life = 3.0 + random.random() * 2.0
        else:  # gray_jitter
            # 灰色锯齿抖动：原地小范围抖
            self.vx = 0.0
            self.vy = 0.0
            self.size = 1 + random.random() * 1
            self.max_life = 1.5 + random.random() * 1.0
        self.life = self.max_life


# ====================================================================
# AtmosphereSystem 单例
# ====================================================================


class AtmosphereSystem:
    """情感氛围系统（单例）。

    全局管理：
    - 每个生命体的光环渲染数据
    - 区域氛围累积（zone → {情绪: 强度}）
    - 氛围粒子池（上限 50）
    """

    _instance: AtmosphereSystem | None = None
    _instance_lock = threading.Lock()

    # 默认设置（可被用户覆盖）
    DEFAULT_SETTINGS: dict = {
        "aura_intensity": 0.7,  # 光环强度 0-1
        "particle_density": "medium",  # 少/中/多
        "show_aura": True,
        "show_particles": True,
        "show_zone_aura": True,
    }

    PARTICLE_LIMIT: int = 50

    def __new__(cls, *args, **kwargs) -> Self:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._init_once()
                    cls._instance = obj
        return cls._instance

    def _init_once(self) -> None:
        self._lock = threading.RLock()
        # 光环数据缓存：{agent_name: {emo, intensity, secondary_emo, secondary_intensity, radius, x, y, color}}
        self._aura_cache: dict[str, dict] = {}
        # 上次情感值快照（用于检测变化 > 0.1）
        self._last_emotion_snapshot: dict[str, dict] = {}
        # 区域氛围累积：{zone_id: {emo: intensity}}
        self._zone_aura: dict[str, dict] = {}
        # 氛围粒子池
        self._particles: list[AtmosphereParticle] = []
        # 上次粒子生成时间
        self._last_particle_spawn: float = 0.0
        # 设置
        self._settings: dict = dict(self.DEFAULT_SETTINGS)
        # 上次 snapshot 时间（用于节流）
        self._last_snapshot_ts: float = 0.0
        self._last_snapshot: dict = {"auras": [], "particles": [], "zone_aura": {}}

    # ---------------- mood_transition / current_atmosphere ----------------

    _mood_transition_cache: dict = {}
    _mood_transition_speed: float = 0.05

    def mood_transition(
        self, agent_name: str, target_mood: dict, speed: float = 0.05
    ) -> dict:
        with self._lock:
            prev = self._mood_transition_cache.get(agent_name, {})
            if not prev:
                self._mood_transition_cache[agent_name] = dict(target_mood)
                return dict(target_mood)
            smoothed = {}
            for emo, val in target_mood.items():
                old = prev.get(emo, 0.0)
                diff = val - old
                step = diff * speed
                smoothed[emo] = round(old + step, 3)
            self._mood_transition_cache[agent_name] = smoothed
            return smoothed

    @property
    def current_atmosphere(self) -> dict:
        with self._lock:
            if not self._zone_aura:
                return {"dominant": "neutral", "score": 0.5, "zones": {}}
            all_scores: list[float] = []
            zone_scores = {}
            emotion_total: dict[str, float] = {}
            for zid, aura in self._zone_aura.items():
                if aura:
                    dom = max(aura, key=aura.get)
                    score = sum(aura.values()) / len(aura)
                    for emo, val in aura.items():
                        emotion_total[emo] = emotion_total.get(emo, 0) + val
                else:
                    dom = "neutral"
                    score = 0.5
                zone_scores[zid] = {
                    "dominant": dom,
                    "score": round(score, 3),
                    "raw": dict(aura),
                }
                all_scores.append(score)
            global_score = sum(all_scores) / len(all_scores) if all_scores else 0.5
            global_dominant = (
                max(emotion_total, key=emotion_total.get)
                if emotion_total
                else "neutral"
            )
            return {
                "dominant": global_dominant,
                "score": round(global_score, 3),
                "zones": zone_scores,
            }

    # ---------------- 设置管理 ----------------

    def update_settings(self, settings: dict) -> None:
        """更新沉浸感设置。"""
        with self._lock:
            for k, v in settings.items():
                if k in self._settings:
                    self._settings[k] = v

    def get_settings(self) -> dict:
        return dict(self._settings)

    # ---------------- 主更新入口 ----------------

    def update(self, population: list, dt: float = 1.0) -> None:
        """每秒调用一次：更新光环数据 + 区域累积 + 粒子。

        Args:
            population: 当前存活的生命体列表
            dt: 时间步长（秒）
        """
        if not self._settings.get("show_aura", True):
            with self._lock:
                self._aura_cache.clear()
            return

        with self._lock:
            new_auras: dict[str, dict] = {}
            zone_emotion_accum: dict[str, dict[str, float]] = (
                {}
            )  # {zone_id: {emo: total_intensity}}

            for lf in population:
                if not getattr(lf, "_alive", False):
                    continue
                name = getattr(lf, "_name_obj", "") or str(id(lf))
                emo_state = getattr(lf, "emotional_state", {})
                if not emo_state:
                    continue

                # 检查情感值是否变化 > 0.1（性能优化：未变化则复用缓存）
                last_state = self._last_emotion_snapshot.get(name, {})
                changed = any(
                    abs(emo_state.get(k, 0) - last_state.get(k, 0)) > 0.1
                    for k in emo_state
                )
                if not changed and name in self._aura_cache:
                    new_auras[name] = self._aura_cache[name]
                    # 仍要参与 zone 累积
                    aura = self._aura_cache[name]
                    zone_id = getattr(lf, "current_zone_id", "") or "outdoor"
                    if aura.get("emo"):
                        zone_emotion_accum.setdefault(zone_id, {})
                        zone_emotion_accum[zone_id][aura["emo"]] = (
                            zone_emotion_accum[zone_id].get(aura["emo"], 0)
                            + aura["intensity"]
                        )
                    continue

                # 重新计算光环
                dom = get_dominant_emotion(emo_state)
                if dom is None:
                    # 无显著情感，不显示光环
                    self._last_emotion_snapshot[name] = dict(emo_state)
                    continue
                dom_emo, dom_val = dom
                sec = get_secondary_emotion(emo_state, dom_emo)
                sec_emo = sec[0] if sec else None
                sec_val = sec[1] if sec else 0.0

                # 光环半径：3-5 格，按情感强度
                radius = 3.0 + dom_val * 2.0
                # 光环颜色
                color = emotion_to_rgba(
                    dom_emo, dom_val, self._settings["aura_intensity"]
                )

                # 获取位置（用 zone 中心 + 偏移，这里用 ix/iy 模拟）
                # 前端会从 emp._wx/_wy 拿到真实位置，这里仅传 species+name
                species = getattr(lf, "species", "unknown")
                zone_id = getattr(lf, "current_zone_id", "") or "outdoor"

                aura_data = {
                    "name": name,
                    "species": species,
                    "emo": dom_emo,
                    "intensity": dom_val,
                    "secondary_emo": sec_emo,
                    "secondary_intensity": sec_val,
                    "radius": radius,
                    "color": color,
                    "zone_id": zone_id,
                    "anxiety_pulse": dom_emo == "anxiety",  # 焦虑需脉冲
                }
                new_auras[name] = aura_data
                self._last_emotion_snapshot[name] = dict(emo_state)

                # 累积到 zone
                zone_emotion_accum.setdefault(zone_id, {})
                zone_emotion_accum[zone_id][dom_emo] = (
                    zone_emotion_accum[zone_id].get(dom_emo, 0) + dom_val
                )

            self._aura_cache = new_auras

            # ---------------- 区域氛围累积 ----------------
            # 每个 zone 的情绪按时间衰减+新增累积
            for zone_id, emos in zone_emotion_accum.items():
                cur = self._zone_aura.setdefault(zone_id, {})
                for emo, val in emos.items():
                    cur[emo] = cur.get(emo, 0) * 0.95 + val * 0.05  # 缓慢累积
            # 衰减未在该 tick 出现的 zone
            for zone_id in list(self._zone_aura.keys()):
                if zone_id not in zone_emotion_accum:
                    cur = self._zone_aura[zone_id]
                    for emo in list(cur.keys()):
                        cur[emo] *= 0.97
                        if cur[emo] < 0.05:
                            del cur[emo]
                    if not cur:
                        del self._zone_aura[zone_id]

            # ---------------- 粒子生成 ----------------
            if (
                self._settings.get("show_particles", True)
                and len(self._particles) < self.PARTICLE_LIMIT
            ):
                self._spawn_particles(zone_emotion_accum, dt)

            # 更新粒子位置
            self._update_particles(dt)

    def _spawn_particles(self, zone_emotion_accum: dict, dt: float) -> None:
        """根据区域情绪生成粒子。"""
        density = self._settings.get("particle_density", "medium")
        spawn_rate = {"low": 0.05, "medium": 0.15, "high": 0.30}.get(density, 0.15)
        now = time.time()
        if now - self._last_particle_spawn < 1.0 / spawn_rate:
            return
        self._last_particle_spawn = now
        # 从有显著情绪的 zone 中随机选一个生成粒子
        candidates = []
        for zone_id, emos in zone_emotion_accum.items():
            for emo, val in emos.items():
                if val > 0.5:
                    candidates.append((zone_id, emo, val))
        if not candidates:
            return
        zone_id, emo, _ = random.choice(candidates)
        # 在 zone 中心附近生成粒子（用 zone_id 的哈希作为伪坐标）
        base_x = (hash(zone_id) % 100) * 0.5
        base_y = (hash(zone_id + "y") % 100) * 0.5
        if emo == "joy":
            kind = "golden_float"
        elif emo == "sadness":
            kind = "blue_fall"
        elif emo == "anxiety":
            kind = "gray_jitter"
        elif emo == "contentment":
            kind = "golden_float"  # 满足也用金色（更柔和）
        else:
            return
        for _ in range(3):
            x = base_x + (random.random() - 0.5) * 4
            y = base_y + (random.random() - 0.5) * 4
            self._particles.append(AtmosphereParticle(x, y, kind))
        if len(self._particles) > self.PARTICLE_LIMIT:
            self._particles = self._particles[-self.PARTICLE_LIMIT :]

    def _update_particles(self, dt: float) -> None:
        """更新粒子位置 + 生命周期。"""
        alive: list[AtmosphereParticle] = []
        for p in self._particles:
            p.life -= dt
            if p.life <= 0:
                continue
            if p.kind == "gray_jitter":
                # 抖动：随机偏移
                p.x += (random.random() - 0.5) * 0.15
                p.y += (random.random() - 0.5) * 0.15
            else:
                p.x += p.vx
                p.y += p.vy
            alive.append(p)
        self._particles = alive

    # ---------------- 渲染数据 ----------------

    def snapshot(self) -> dict:
        """生成前端可直接使用的渲染数据。

        Returns:
            {
                "auras": [{name, species, emo, intensity, secondary_emo,
                          secondary_intensity, radius, color, anxiety_pulse}, ...],
                "zone_aura": {zone_id: {emo: intensity}},
                "particles": [{x, y, kind, life, max_life, size}, ...],
                "settings": {...},
            }
        """
        with self._lock:
            auras = list(self._aura_cache.values())
            zone_aura = {z: dict(e) for z, e in self._zone_aura.items()}
            particles = [
                {
                    "x": p.x,
                    "y": p.y,
                    "kind": p.kind,
                    "life": p.life,
                    "max_life": p.max_life,
                    "size": p.size,
                }
                for p in self._particles
            ]
            return {
                "auras": auras,
                "zone_aura": zone_aura,
                "particles": particles,
                "settings": dict(self._settings),
            }


# ====================================================================
# 模块级便捷函数
# ====================================================================

_singleton: AtmosphereSystem | None = None


def get_atmosphere() -> AtmosphereSystem:
    """获取全局 AtmosphereSystem 单例。"""
    global _singleton
    if _singleton is None:
        _singleton = AtmosphereSystem()
    return _singleton


def update_atmosphere(population: list, dt: float = 1.0) -> None:
    """便捷接口：更新氛围系统。"""
    try:
        get_atmosphere().update(population, dt)
    except Exception:
        logger.exception("Exception in block")


def snapshot_atmosphere() -> dict:
    """便捷接口：获取渲染数据。"""
    try:
        return get_atmosphere().snapshot()
    except Exception:
        return {"auras": [], "zone_aura": {}, "particles": [], "settings": {}}
