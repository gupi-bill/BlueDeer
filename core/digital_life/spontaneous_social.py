"""commit 33：自发社交对话系统。

零基础读者可以这样理解：
- 后台每 5-10 分钟扫描一次，找两只距离近、都没在忙的智能体。
- 有 15% 概率触发一次自发对话（2-4 轮），对话内容用 LLM 生成，降级用模板。
- 对话进行时，双方头顶交替出现对话气泡，监工走到附近不会打断。
- 重要对话结束后生成记忆碎片。
- 悲伤的智能体社交概率提升（被安慰），对话后 sadness 降低 joy 提升。

设计要点：
1. 单例 SpontaneousSocialSystem。
2. 对话生成 LLM 调用独立线程，不阻塞主循环。
3. 同一对智能体至少间隔 2 小时。
4. 对话气泡通过 env.push_dialogue_bubble 推送（复用现有机制）。
5. 联动：情感→社交（sadness 提升概率）；社交→碎片（重要对话生成）；碎片→情感（暂未实现）。
"""

from __future__ import annotations

import random
import threading
import time

from typing_extensions import Self
# ruff: noqa: S110, S112

# ====================================================================
# 触发参数
# ====================================================================
SCAN_INTERVAL_SEC = 600  # 每 10 分钟扫描一次
TRIGGER_PROBABILITY = 0.15  # 15% 概率触发
SAME_PAIR_COOLDOWN = 7200  # 同一对 2 小时冷却
DISTANCE_THRESHOLD = 5.0  # 距离阈值（格）
SADNESS_BOOST_THRESHOLD = 0.6  # 悲伤阈值（提升概率）
SADNESS_BOOST_PROB = 0.35  # 悲伤时概率提升到 35%

# 对话气泡显示间隔（秒）
BUBBLE_INTERVAL_SEC = 3.0

# ====================================================================
# 互动类型
# ====================================================================
INTERACTION_DIALOGUE = "dialogue"  # 闲聊（默认）
INTERACTION_COOPERATION = "cooperation"  # 合作：效率加成
INTERACTION_GOSSIP = "gossip"  # 八卦：信息传播
INTERACTION_SHARING = "resource_sharing"  # 资源共享

# ====================================================================
# 物种亲疏矩阵（稀疏：只记 notable 关系）
# 正值 = 倾向于合作互补，负值 = 竞争/紧张
# ====================================================================
SPECIES_AFFINITY: dict[tuple[str, str], float] = {
    ("butterfly", "squirrel"): 0.6,  # 设计+码农
    ("beaver", "raven"): 0.5,  # 建筑+匠人
    ("deer", "kite"): 0.5,  # 领导+战略
    ("badger", "hare"): 0.4,  # 文化+财务
    ("deer", "lark"): 0.3,  # 领导指导雀创作
    ("fox", "squirrel"): 0.3,  # PM+码农
    ("butterfly", "fox"): 0.3,  # 设计+PM
    ("beaver", "hedgehog"): -0.4,  # 建筑动土 vs 运维稳定
    ("kite", "fox"): -0.3,  # 战略 vs PM路线之争
    ("squirrel", "hare"): -0.2,  # 花钱 vs 管钱
}


def _get_affinity(species_a: str, species_b: str) -> float:
    key = tuple(sorted([species_a, species_b]))
    return SPECIES_AFFINITY.get(key, 0.0)


def _pick_interaction_type(species_a: str, species_b: str, zone_id: str) -> str:
    aff = _get_affinity(species_a, species_b)
    if aff >= 0.4:
        return INTERACTION_COOPERATION
    if aff <= -0.3:
        return INTERACTION_DIALOGUE
    if zone_id in ("deer",) and random.random() < 0.3:
        return INTERACTION_GOSSIP
    return INTERACTION_DIALOGUE


# ====================================================================
# 预置对话库（降级用）
# ====================================================================
# 按关系标签 + 物种 + 场景 筛选
DIALOGUE_TEMPLATES: list[dict] = [
    {
        "tags": ["挚友"],
        "lines": [
            ("{a}", "嘿，又见面了。"),
            ("{b}", "是啊，今天过得怎么样？"),
            ("{a}", "还行，就是有点累。"),
            ("{b}", "我也是。要不要一起去休息室坐会儿？"),
        ],
    },
    {
        "tags": ["搭档"],
        "lines": [
            ("{a}", "上次那个任务我们配合得不错。"),
            ("{b}", "是啊，下次还一起？"),
            ("{a}", "当然。"),
        ],
    },
    {
        "tags": [],  # 通用
        "lines": [
            ("{a}", "今天天气不错。"),
            ("{b}", "嗯，难得的好天气。"),
            ("{a}", "要不要出去走走？"),
            ("{b}", "好啊，正好我也想透透气。"),
        ],
    },
    {
        "tags": [],
        "lines": [
            ("{a}", "你最近看起来有点累。"),
            ("{b}", "是有点，工作压力大。"),
            ("{a}", "别太拼了，注意身体。"),
            ("{b}", "谢谢，你也是。"),
        ],
    },
    {
        "tags": [],
        "lines": [
            ("{a}", "听说昨天你解决了那个难题？"),
            ("{b}", "运气好而已。"),
            ("{a}", "谦虚了。"),
        ],
    },
    {
        "tags": ["挚友"],
        "lines": [
            ("{a}", "我在想，要是没有你这个朋友，我会怎样？"),
            ("{b}", "别傻了，我一直在。"),
            ("{a}", "嗯，谢谢你。"),
        ],
    },
]


def pick_dialogue_template(tags: list[str]) -> dict:
    """根据关系标签挑选对话模板。优先匹配标签，无匹配则通用。"""
    # 优先找带匹配标签的
    for tpl in DIALOGUE_TEMPLATES:
        if tpl["tags"] and any(t in tags for t in tpl["tags"]):
            if random.random() < 0.7:  # 70% 概率用第一个匹配的
                return tpl
    # 否则用通用的
    general = [t for t in DIALOGUE_TEMPLATES if not t["tags"]]
    return random.choice(general) if general else DIALOGUE_TEMPLATES[0]


def format_dialogue(tpl: dict, name_a: str, name_b: str) -> list[dict]:
    """格式化对话模板，返回 [{speaker, text}, ...]。"""
    lines = []
    for speaker, text in tpl["lines"]:
        spk_name = name_a if speaker == "{a}" else name_b
        lines.append({"speaker": spk_name, "text": text})
    return lines


# ====================================================================
# SpontaneousSocialSystem 单例
# ====================================================================


class SpontaneousSocialSystem:
    """自发社交系统（单例）。"""

    _instance: SpontaneousSocialSystem | None = None
    _instance_lock = threading.Lock()

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
        # 上次扫描时间
        self._last_scan_ts: float = 0.0
        # 同一对智能体的上次对话时间：{(name_a, name_b): ts}
        self._pair_cooldowns: dict[tuple, float] = {}
        # 当前活跃的对话：[{a, b, lines, current_idx, next_bubble_ts, env, finished, summary}]
        self._active_dialogues: list[dict] = []
        # 已完成的精彩对话摘录（10 分钟后可查看）
        # [{a, b, lines, time, available_ts, summary}]
        self._dialogue_archive: list[dict] = []
        # 合作 buff 追踪：{name: expiry_ts}
        self._coop_buffs: dict[str, float] = {}
        # 八卦传播追踪：{name: last_gossip_ts}
        self._last_gossip_ts: dict[str, float] = {}
        # 设置
        self._settings: dict = {
            "frequency": "medium",  # low/medium/high
            "bubble_speed": "medium",  # slow/medium/fast
        }

    # ---------------- 设置 ----------------

    def update_settings(self, settings: dict) -> None:
        with self._lock:
            for k, v in settings.items():
                if k in self._settings:
                    self._settings[k] = v

    def get_settings(self) -> dict:
        return dict(self._settings)

    def _get_scan_interval(self) -> float:
        freq = self._settings.get("frequency", "medium")
        return {"low": 900, "medium": 600, "high": 300}.get(freq, 600)

    def _get_bubble_interval(self) -> float:
        speed = self._settings.get("bubble_speed", "medium")
        return {"slow": 4.5, "medium": 3.0, "fast": 1.8}.get(speed, 3.0)

    # ---------------- 主扫描入口 ----------------

    def scan_and_trigger(self, population: list, env=None, router=None) -> int:
        """扫描种群，触发自发对话。

        Args:
            population: 当前存活的生命体列表
            env: Environment 实例（用于推送气泡）
            router: LLM router（可选，None 则用模板降级）

        Returns:
            本次扫描触发的对话数
        """
        now = time.time()
        interval = self._get_scan_interval()
        if now - self._last_scan_ts < interval:
            return 0
        self._last_scan_ts = now

        # 筛选候选：存活、非睡眠、非工作
        candidates = []
        for lf in population:
            if not getattr(lf, "_alive", False):
                continue
            if getattr(lf, "sleeping", False):
                continue
            if (
                getattr(lf, "current_action", None)
                and str(getattr(lf, "current_action", "")) == "ActionState.WORK"
            ):
                continue
            candidates.append(lf)

        if len(candidates) < 2:
            return 0

        triggered = 0
        # 随机配对（避免一次扫描触发太多，最多 3 对）
        random.shuffle(candidates)
        used = set()
        for i, a in enumerate(candidates):
            if a._name_obj in used:
                continue
            for b in candidates[i + 1 :]:
                if b._name_obj in used:
                    continue
                # 距离检查（用 zone 是否相同近似，因为这里拿不到精确坐标）
                if getattr(a, "current_zone_id", "") != getattr(
                    b, "current_zone_id", ""
                ):
                    continue
                pair = tuple(sorted([a._name_obj, b._name_obj]))
                # 冷却检查
                last_ts = self._pair_cooldowns.get(pair, 0)
                if now - last_ts < SAME_PAIR_COOLDOWN:
                    continue
                # 概率触发：悲伤时提升
                a_sad = a.emotional_state.get("sadness", 0) > SADNESS_BOOST_THRESHOLD
                b_sad = b.emotional_state.get("sadness", 0) > SADNESS_BOOST_THRESHOLD
                prob = SADNESS_BOOST_PROB if (a_sad or b_sad) else TRIGGER_PROBABILITY
                if random.random() > prob:
                    continue
                # 确定互动类型
                zone_id = getattr(a, "current_zone_id", "outdoor")
                ia_type = _pick_interaction_type(a.species, b.species, zone_id)
                # 触发互动
                self._start_interaction(a, b, ia_type, env, router)
                self._pair_cooldowns[pair] = now
                used.add(a._name_obj)
                used.add(b._name_obj)
                triggered += 1
                break  # a 已配对，跳出内层循环
            if triggered >= 3:
                break
        return triggered

    # ---------------- 启动一次互动 ----------------

    def _start_interaction(self, a, b, ia_type: str, env, router) -> None:
        """启动一次互动（异步，不阻塞主循环）。"""

        def _generate():
            lines = self._generate_dialogue_lines(a, b, router)
            if not lines:
                return
            interaction = {
                "a": a,
                "b": b,
                "type": ia_type,
                "lines": lines,
                "current_idx": 0,
                "next_bubble_ts": time.time(),
                "env": env,
                "finished": False,
                "summary": "",
                "start_time": time.time(),
                "generated_fragment": False,
            }
            with self._lock:
                self._active_dialogues.append(interaction)

        t = threading.Thread(target=_generate, daemon=True)
        t.start()

    def _generate_dialogue_lines(self, a, b, router) -> list[dict]:
        """生成对话内容。优先 LLM，降级模板。"""
        # LLM 生成（可选）
        if router is not None:
            try:
                lines = self._generate_via_llm(a, b, router)
                if lines:
                    return lines
            except Exception:
                pass
        # 模板降级
        tags = []
        rel_tags = getattr(a, "relationship_tags", {}).get(b._name_obj, [])
        tags.extend(rel_tags)
        tpl = pick_dialogue_template(tags)
        return format_dialogue(tpl, a._name_obj, b._name_obj)

    def _generate_via_llm(self, a, b, router) -> list[dict] | None:
        """通过 LLM 生成对话。返回 [{speaker, text}, ...] 或 None。"""
        import asyncio

        prompt = self._build_llm_prompt(a, b)
        try:
            loop = asyncio.new_event_loop()
            try:
                resp = loop.run_until_complete(
                    router.complete_with_failover("dialogue", prompt, a._name_obj)
                )
            finally:
                loop.close()
            if not resp:
                return None
            # 简单解析：每行 "名字：内容" 或 "名字:内容"
            lines = []
            for line in resp.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                # 尝试解析 "名字：内容"
                for sep in ("：", ":", " - ", " -"):
                    if sep in line:
                        spk, txt = line.split(sep, 1)
                        spk = spk.strip()
                        txt = txt.strip()
                        if spk in (a._name_obj, b._name_obj):
                            lines.append({"speaker": spk, "text": txt})
                        break
                if len(lines) >= 4:
                    break
            return lines if lines else None
        except Exception:
            return None

    def _build_llm_prompt(self, a, b) -> str:
        """构建 LLM prompt。"""
        a_emo = a.emotional_state
        b_emo = b.emotional_state
        rel = getattr(a, "relationships", {}).get(b._name_obj, {})
        tags = getattr(a, "relationship_tags", {}).get(b._name_obj, [])
        zone = getattr(a, "current_zone_id", "outdoor")
        return f"""你是 {a._name_obj}（{a.species}）和 {b._name_obj}（{b.species}），你们在 {zone} 区域偶遇了。

{a._name_obj} 当前情感：joy={a_emo.get('joy',0):.2f}, sadness={a_emo.get('sadness',0):.2f}, anxiety={a_emo.get('anxiety',0):.2f}
{b._name_obj} 当前情感：joy={b_emo.get('joy',0):.2f}, sadness={b_emo.get('sadness',0):.2f}, anxiety={b_emo.get('anxiety',0):.2f}
关系：好感={rel.get('affection',0):.2f}, 信任={rel.get('trust',0):.2f}, 标签={tags}

请生成 2-4 轮简短对话（每轮一行，格式："名字：内容"），自然、口语化，体现双方性格和当前情感。
不要解释，直接输出对话。"""

    # ---------------- 每秒更新（推气泡） ----------------

    def update(self, dt: float = 1.0) -> None:
        """每秒调用：推进活跃对话的气泡推送。"""
        now = time.time()
        bubble_interval = self._get_bubble_interval()
        with self._lock:
            still_active = []
            for d in self._active_dialogues:
                if d["finished"]:
                    continue
                # 推送当前气泡
                if now >= d["next_bubble_ts"]:
                    if d["current_idx"] < len(d["lines"]):
                        line = d["lines"][d["current_idx"]]
                        # 推送到 env 的对话气泡队列
                        env = d["env"]
                        if env is not None:
                            try:
                                env.push_dialogue_bubble(
                                    speaker=line["speaker"],
                                    text=line["text"],
                                    target="",
                                )
                            except Exception:
                                pass
                        d["current_idx"] += 1
                        d["next_bubble_ts"] = now + bubble_interval
                    else:
                        # 对话结束
                        d["finished"] = True
                        self._on_dialogue_finished(d)
                still_active.append(d)
            # 移除已完成的（保留一会儿供状态查询，10 分钟后归档）
            self._active_dialogues = [
                d
                for d in still_active
                if not (d["finished"] and now - d.get("end_ts", now) > 600)
            ]

    def _on_dialogue_finished(self, d: dict) -> None:
        """互动结束后的处理：按类型分派效果。"""
        d["end_ts"] = time.time()
        ia_type = d.get("type", INTERACTION_DIALOGUE)

        if ia_type == INTERACTION_COOPERATION:
            self._apply_cooperation_effects(d)
        elif ia_type == INTERACTION_GOSSIP:
            self._apply_gossip_effects(d)
        elif ia_type == INTERACTION_SHARING:
            self._apply_sharing_effects(d)
        else:
            self._apply_dialogue_effects(d)

        # 所有类型都归档 + 碎片生成
        self._archive_interaction(d)

    def _apply_dialogue_effects(self, d: dict) -> None:
        """闲聊效果：情感改善 + 关系微升（原有逻辑）。"""
        a, b = d["a"], d["b"]
        try:
            a.emotional_state["sadness"] = max(
                0, a.emotional_state.get("sadness", 0) - 0.1
            )
            a.emotional_state["joy"] = min(1.0, a.emotional_state.get("joy", 0) + 0.08)
            b.emotional_state["sadness"] = max(
                0, b.emotional_state.get("sadness", 0) - 0.1
            )
            b.emotional_state["joy"] = min(1.0, b.emotional_state.get("joy", 0) + 0.08)
        except Exception:
            pass
        try:
            for src, tgt in [(a, b), (b, a)]:
                rel = src.relationships.setdefault(tgt._name_obj, {})
                rel["affection"] = min(1.0, rel.get("affection", 0) + 0.02)
                rel["familiarity"] = min(1.0, rel.get("familiarity", 0) + 0.03)
        except Exception:
            pass

    def _apply_cooperation_effects(self, d: dict) -> None:
        """合作效果：双方获得 1 小时效率 buff + 更大的关系提升。"""
        a, b = d["a"], d["b"]
        now = time.time()
        expiry = now + 3600
        with self._lock:
            self._coop_buffs[a._name_obj] = expiry
            self._coop_buffs[b._name_obj] = expiry
        try:
            for src, tgt in [(a, b), (b, a)]:
                rel = src.relationships.setdefault(tgt._name_obj, {})
                rel["affection"] = min(1.0, rel.get("affection", 0) + 0.06)
                rel["familiarity"] = min(1.0, rel.get("familiarity", 0) + 0.08)
                rel["trust"] = min(1.0, rel.get("trust", 0) + 0.05)
        except Exception:
            pass

    def _apply_gossip_effects(self, d: dict) -> None:
        """八卦效果：大幅提升 familiarity，模拟信息交换。"""
        a, b = d["a"], d["b"]
        now = time.time()
        try:
            for src, tgt in [(a, b), (b, a)]:
                rel = src.relationships.setdefault(tgt._name_obj, {})
                rel["familiarity"] = min(1.0, rel.get("familiarity", 0) + 0.12)
                rel["affection"] = min(1.0, rel.get("affection", 0) + 0.03)
        except Exception:
            pass
        with self._lock:
            self._last_gossip_ts[a._name_obj] = now
            self._last_gossip_ts[b._name_obj] = now

    def _apply_sharing_effects(self, d: dict) -> None:
        """资源共享效果：暂用对话效果代替（纯占位，留升级接口）。"""
        self._apply_dialogue_effects(d)

    def _archive_interaction(self, d: dict) -> None:
        """归档互动记录 + 生成记忆碎片。"""
        a, b = d["a"], d["b"]
        archive_entry = {
            "a": a._name_obj,
            "a_species": a.species,
            "b": b._name_obj,
            "b_species": b.species,
            "lines": d["lines"],
            "time": d["start_time"],
            "available_ts": time.time() + 600,  # 10 分钟后
            "summary": d["summary"],
            "zone_id": getattr(a, "current_zone_id", "outdoor"),
        }
        self._dialogue_archive.append(archive_entry)
        # 限制归档大小
        if len(self._dialogue_archive) > 100:
            self._dialogue_archive = self._dialogue_archive[-100:]

        # 联动：在对话地点生成记忆碎片（social_dialogue 类型）
        try:
            from core.digital_life.memory_fragment import spawn_fragment

            # 用 a 的当前 zone 作为坐标（简化处理，前端会在 zone 中心附近显示）
            zone_id = getattr(a, "current_zone_id", "outdoor")
            # 坐标用 zone 哈希生成伪坐标（实际显示由前端按 zone 中心+随机偏移）
            import hashlib

            hash_val = int(hashlib.md5(zone_id.encode()).hexdigest()[:8], 16)
            fx = (hash_val % 100) * 0.5
            fy = ((hash_val >> 8) % 100) * 0.5
            spawn_fragment(
                frag_type="social_dialogue",
                x=fx,
                y=fy,
                zone_id=zone_id,
                agent_name=a._name_obj,
                agent_species=a.species,
                detail=b._name_obj,
                related_agent_name=b._name_obj,
            )
        except Exception:
            pass

    # ---------------- 查询 ----------------

    def get_active_dialogues(self) -> list[dict]:
        """返回当前活跃的对话（供调试/状态查询）。"""
        with self._lock:
            return [
                {
                    "a": d["a"]._name_obj,
                    "b": d["b"]._name_obj,
                    "lines_count": len(d["lines"]),
                    "current_idx": d["current_idx"],
                    "finished": d["finished"],
                }
                for d in self._active_dialogues
            ]

    def get_recent_dialogues(self, limit: int = 20) -> list[dict]:
        """返回最近的精彩对话摘录（10 分钟前的才能查看）。"""
        now = time.time()
        with self._lock:
            available = [
                {
                    "a": d["a"],
                    "a_species": d["a_species"],
                    "b": d["b"],
                    "b_species": d["b_species"],
                    "lines": d["lines"],
                    "time": d["time"],
                    "summary": d["summary"],
                    "zone_id": d["zone_id"],
                }
                for d in self._dialogue_archive
                if d["available_ts"] <= now
            ]
            return available[-limit:]

    def snapshot(self) -> dict:
        """生成前端渲染数据。"""
        with self._lock:
            return {
                "active_count": len(self._active_dialogues),
                "active": self.get_active_dialogues(),
                "archive_count": len(self._dialogue_archive),
                "settings": dict(self._settings),
            }


# ====================================================================
# 模块级便捷函数
# ====================================================================

_singleton: SpontaneousSocialSystem | None = None


def get_social() -> SpontaneousSocialSystem:
    global _singleton
    if _singleton is None:
        _singleton = SpontaneousSocialSystem()
    return _singleton


def scan_social(population: list, env=None, router=None) -> int:
    try:
        return get_social().scan_and_trigger(population, env, router)
    except Exception:
        return 0


def update_social(dt: float = 1.0) -> None:
    try:
        get_social().update(dt)
    except Exception:
        pass


def snapshot_social() -> dict:
    try:
        return get_social().snapshot()
    except Exception:
        return {"active_count": 0, "active": [], "archive_count": 0, "settings": {}}
