"""命名系统 NamingSystem。

职责：
- 给每个生命体分配唯一 ID（如 'deer-001'）
- 自动命名格式：姓氏·世代·名（如"鹿·初代·墨角"）
- 标记重要个体（marked）
- 记录生命事件历史
- 生命回顾 life_review
- 反查：id(life_form) → life_id（快速去重）

零基础读者可以这样理解：
- NamingSystem 是公司的人事档案系统。
- 每个员工有 ID（deer-001）和中文名（鹿·初代·墨角）。
- 可以把某个员工标"重点关注"。
- 员工的所有大事都记进档案。
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict

# 物种 → 中文姓氏
SPECIES_SURNAME = {
    "deer":      "鹿",
    "squirrel":  "鼠",
    "butterfly": "蝶",
    "fox":       "狐",
    "hedgehog":  "猬",
    "beaver":    "狸",
    "raven":     "鸦",
    "hare":      "兔",
    "badger":    "獾",
    "lark":      "雀",
    "kite":      "鸢",
}

# 世代 → 中文
GENERATION_CN = {
    1: "初代",
    2: "二代",
    3: "三代",
    4: "四代",
    5: "五代",
}

# 备用名字池（按物种）
NAME_POOL = {
    "deer":      ["墨角", "忧郁", "霜枝", "晨曦"],
    "squirrel":  ["栗壳", "坚果", "橡子", "枫叶"],
    "butterfly": ["绘羽", "彩翅", "粉鳞", "虹影"],
    "fox":       ["赤谋", "狡黠", "红尾", "智狐"],
    "hedgehog":  ["针客", "戒备", "刺甲", "蜷球"],
    "beaver":    ["大坝", "勤恳", "木工", "齿刃"],
    "raven":     ["黑卷", "夜羽", "墨眼", "古记"],
    "hare":      ["霜耳", "雪跃", "白足", "冰窟"],
    "badger":    ["土工", "地道", "掘洞", "暗行"],
    "lark":      ["清音", "晨歌", "羽铃", "鸣枝"],
    "kite":      ["天瞰", "盘旋", "云翼", "高空"],
}


class NamingSystem:
    """命名系统。"""

    def __init__(self):
        self._lock = threading.RLock()
        self._registry = {}                # life_id -> name
        self._counter = defaultdict(int)   # species -> count
        self._marked = set()               # 标记为重要的 life_id
        self._life_history = defaultdict(list)  # life_id -> [event dict]
        self._life_forms = {}              # life_id -> life_form 引用
        self._id_index = {}                # id(life_form) -> life_id（快速反查）

    # ------------------------------------------------------------------
    # 注册
    # ------------------------------------------------------------------

    def register(self, life_form) -> str:
        """注册生命体，返回分配的 ID（如 'deer-001'）。

        若已注册过，返回已有 ID（基于 id(life_form) 反查）。
        """
        with self._lock:
            oid = id(life_form)
            if oid in self._id_index:
                return self._id_index[oid]
            species = getattr(life_form, "species", "unknown")
            self._counter[species] += 1
            life_id = f"{species}-{self._counter[species]:03d}"
            self._id_index[oid] = life_id
            self._life_forms[life_id] = life_form
            self._life_history[life_id].append({
                "time": time.time(),
                "event": "registered",
                "data": {"species": species},
            })
            return life_id

    # ------------------------------------------------------------------
    # 命名
    # ------------------------------------------------------------------

    def name(self, life_form, custom_name: str | None = None) -> str:
        """为生命体命名。custom_name 为 None 时自动命名。

        自动命名格式：姓氏·世代·名（如"鹿·初代·墨角"）。
        世代判定：无 parents = 初代，有 parents = 二代。
        命名后同时更新 life_form._name_obj 字段。
        """
        with self._lock:
            oid = id(life_form)
            life_id = self._id_index.get(oid)
            if life_id is None:
                life_id = self.register(life_form)

            if custom_name:
                final_name = custom_name
            else:
                species = getattr(life_form, "species", "unknown")
                surname = SPECIES_SURNAME.get(species, "未")
                # 世代判定
                parents = getattr(life_form, "parents", [])
                gen_num = 1 if not parents else 2
                gen_cn = GENERATION_CN.get(gen_num, f"{gen_num}代")
                # 从池中随机取一个名字
                pool = NAME_POOL.get(species, ["无名"])
                # 用 life_id 末尾数字索引保证稳定
                try:
                    idx = int(life_id.split("-")[-1]) - 1
                except (ValueError, IndexError):
                    idx = 0
                given = pool[idx % len(pool)]
                final_name = f"{surname}·{gen_cn}·{given}"

            self._registry[life_id] = final_name
            # 同步更新 life_form 内部名字
            try:
                life_form._name_obj = final_name
            except (AttributeError, TypeError):
                pass
            self._life_history[life_id].append({
                "time": time.time(),
                "event": "named",
                "data": {"name": final_name},
            })
            return final_name

    # ------------------------------------------------------------------
    # 标记
    # ------------------------------------------------------------------

    def mark(self, life_id: str) -> None:
        """标记为重要个体。"""
        with self._lock:
            self._marked.add(life_id)
            self._life_history[life_id].append({
                "time": time.time(),
                "event": "marked",
                "data": {},
            })

    def unmark(self, life_id: str) -> None:
        """取消标记。"""
        with self._lock:
            self._marked.discard(life_id)

    def is_marked(self, life_id: str) -> bool:
        """是否被标记。"""
        with self._lock:
            return life_id in self._marked

    # ------------------------------------------------------------------
    # 事件记录
    # ------------------------------------------------------------------

    def record_event(self, life_id: str, event: str, data: dict | None = None) -> None:
        """记录生命事件到档案。"""
        with self._lock:
            self._life_history[life_id].append({
                "time": time.time(),
                "event": event,
                "data": dict(data) if data else {},
            })

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_name(self, life_id: str) -> str:
        """通过 ID 取名字。"""
        with self._lock:
            return self._registry.get(life_id, "未命名")

    def get_life_form(self, life_id: str):
        """通过 ID 获取生命体引用。"""
        with self._lock:
            return self._life_forms.get(life_id)

    def get_id(self, life_form) -> str | None:
        """通过 life_form 取 ID。"""
        with self._lock:
            return self._id_index.get(id(life_form))

    def all_ids(self) -> list:
        """返回所有已注册 ID。"""
        with self._lock:
            return list(self._life_forms.keys())

    def all_marked_ids(self) -> list:
        """返回所有已标记 ID。"""
        with self._lock:
            return list(self._marked)

    # ------------------------------------------------------------------
    # 生命回顾
    # ------------------------------------------------------------------

    def life_review(self, life_id: str) -> str:
        """生成生命回顾叙事文本。

        包含：诞生日期、性别俗名、生命阶段、当前状态、历史事件、是否存活。
        """
        with self._lock:
            lf = self._life_forms.get(life_id)
            name = self._registry.get(life_id, "未命名")
            history = list(self._life_history.get(life_id, []))
            marked = life_id in self._marked

        if lf is None:
            return f"{name}（{life_id}）：档案已失效"

        # 基本信息
        gender_cn = {"male": "雄", "female": "雌"}.get(getattr(lf, "gender", ""), "?")
        stage = getattr(lf, "life_stage", None)
        stage_val = stage.value if stage is not None else "?"
        alive = getattr(lf, "_alive", False)
        alive_cn = "存活" if alive else "已故"

        lines = [
            f"=== 生命回顾：{name}（{life_id}）===",
            f"性别：{gender_cn}",
            f"生命阶段：{stage_val}",
            f"状态：{alive_cn}",
            f"重要标记：{'是' if marked else '否'}",
            f"历史事件数：{len(history)}",
            "",
            "近期事件：",
        ]
        for ev in history[-10:]:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ev["time"]))
            lines.append(f"  [{ts}] {ev['event']} {ev.get('data', {})}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """返回命名系统状态摘要。"""
        with self._lock:
            return {
                "total_registered": len(self._life_forms),
                "total_named": len(self._registry),
                "marked_count": len(self._marked),
                "species_counts": dict(self._counter),
            }
