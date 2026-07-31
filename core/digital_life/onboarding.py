"""commit 40：新手引导系统。

零基础读者可以这样理解：
- 第一次打开系统的人会一脸懵——这么多按钮、这么多动物，干啥的？
- 让灵音雀（最活泼的智能体）担任引导员，分 5 个阶段带新用户参观
- 引导完成后给监工发 50 印记奖励，记录到档案
- 之后 7 天偶尔弹小贴士

状态持久化：data/onboarding.json
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

_ONBOARDING_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "onboarding.json",
)

# 引导阶段
STAGE_WELCOME = "welcome"           # 第一阶段：欢迎
STAGE_MEET_TEAM = "meet_team"       # 第二阶段：认识同事
STAGE_FIRST_INTERACT = "first_interact"  # 第三阶段：第一次互动
STAGE_FIRST_TASK = "first_task"     # 第四阶段：第一个任务
STAGE_FREE_EXPLORE = "free_explore"  # 第五阶段：自由探索
STAGE_DONE = "done"                 # 已完成

STAGE_ORDER = [
    STAGE_WELCOME,
    STAGE_MEET_TEAM,
    STAGE_FIRST_INTERACT,
    STAGE_FIRST_TASK,
    STAGE_FREE_EXPLORE,
    STAGE_DONE,
]

# 入职奖励
ONBOARDING_REWARD_MARKS = 50

# 小贴士池（引导完成后 7 天内随机弹）
TIPS = [
    "你知道吗？松鼠最喜欢被投喂核桃。",
    "如果你连续 3 天不跟某个同事互动，他们会想念你的。",
    "按 G 键可以查看全公司概览面板。",
    "渡鸦记得所有已故同事的故事，你可以去资料库看看。",
    "按 P 键打开项目看板，按 E 键打开外部集成面板。",
    "按 I 键打开建议中心，看看智能体们想到了什么好主意。",
    "鹿·忧郁是团队领导，遇到问题可以先找她。",
    "海狸是运维专家，部署相关的事情都找他。",
    "狐狸虽然毒舌，但测试工作做得非常认真。",
    "蝴蝶的审美一流，UI 相关的事情可以放心交给她。",
    "按 M 键可以打开消息中心，查看历史对话。",
    "兔·霜耳负责统计分析，想看数据找她准没错。",
]


class OnboardingManager:
    """新手引导管理器（单例）。

    所有引导状态通过此管理器查询/推进。
    前端通过 API 拉取当前阶段、推进阶段、跳过引导。
    """
    _instance: OnboardingManager | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._biosphere_ref: Any = None
        # 引导状态
        self._completed: bool = False            # 是否已完成引导
        self._current_stage: str = STAGE_WELCOME  # 当前阶段
        self._stage_started_ts: float = 0.0       # 当前阶段开始时间
        self._completed_ts: float = 0.0           # 完成时间
        self._skipped: bool = False                # 是否跳过
        # 小贴士
        self._tips_enabled: bool = True            # 是否显示小贴士
        self._last_tip_ts: float = 0.0             # 上次弹贴士时间
        self._tip_shown_count: int = 0             # 已显示的贴士数
        self._load()

    @classmethod
    def get_instance(cls) -> OnboardingManager:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def set_biosphere(self, bio: Any) -> None:
        self._biosphere_ref = bio

    # ---------------- 持久化 ----------------

    def _load(self) -> None:
        try:
            if os.path.exists(_ONBOARDING_PATH):
                with open(_ONBOARDING_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._completed = bool(data.get("completed", False))
                self._current_stage = data.get("current_stage", STAGE_WELCOME)
                self._stage_started_ts = float(data.get("stage_started_ts", 0.0))
                self._completed_ts = float(data.get("completed_ts", 0.0))
                self._skipped = bool(data.get("skipped", False))
                self._tips_enabled = bool(data.get("tips_enabled", True))
                self._last_tip_ts = float(data.get("last_tip_ts", 0.0))
                self._tip_shown_count = int(data.get("tip_shown_count", 0))
        except Exception:
            pass

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(_ONBOARDING_PATH), exist_ok=True)
            with self._lock:
                data = {
                    "completed": self._completed,
                    "current_stage": self._current_stage,
                    "stage_started_ts": self._stage_started_ts,
                    "completed_ts": self._completed_ts,
                    "skipped": self._skipped,
                    "tips_enabled": self._tips_enabled,
                    "last_tip_ts": self._last_tip_ts,
                    "tip_shown_count": self._tip_shown_count,
                }
            with open(_ONBOARDING_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------------- 状态查询 ----------------

    def get_status(self) -> dict:
        """返回当前引导状态。"""
        with self._lock:
            return {
                "completed": self._completed,
                "current_stage": self._current_stage,
                "stage_index": STAGE_ORDER.index(self._current_stage) if self._current_stage in STAGE_ORDER else 0,
                "stage_total": len(STAGE_ORDER) - 1,  # 不含 done
                "stage_started_ts": self._stage_started_ts,
                "completed_ts": self._completed_ts,
                "skipped": self._skipped,
                "tips_enabled": self._tips_enabled,
                "tip_shown_count": self._tip_shown_count,
                "should_show_onboarding": (not self._completed and not self._skipped),
            }

    def is_first_run(self) -> bool:
        """是否需要触发引导（未完成且未跳过）。"""
        return (not self._completed) and (not self._skipped)

    # ---------------- 阶段控制 ----------------

    def start(self) -> dict:
        """开始引导（重置到第一阶段）。"""
        with self._lock:
            self._completed = False
            self._skipped = False
            self._current_stage = STAGE_WELCOME
            self._stage_started_ts = time.time()
        self._save()
        return self.get_status()

    def next_stage(self) -> dict:
        """推进到下一阶段。"""
        with self._lock:
            if self._current_stage in STAGE_ORDER:
                idx = STAGE_ORDER.index(self._current_stage)
                if idx < len(STAGE_ORDER) - 1:
                    self._current_stage = STAGE_ORDER[idx + 1]
                    self._stage_started_ts = time.time()
                # 推进到 done 时标记完成
                if self._current_stage == STAGE_DONE:
                    self._completed = True
                    self._completed_ts = time.time()
                    self._grant_reward()
            else:
                self._current_stage = STAGE_WELCOME
                self._stage_started_ts = time.time()
        self._save()
        return self.get_status()

    def skip(self) -> dict:
        """跳过所有引导。"""
        with self._lock:
            self._skipped = True
            self._completed = True  # 跳过也算完成，不再触发
            self._current_stage = STAGE_DONE
            self._completed_ts = time.time()
        self._save()
        return self.get_status()

    def set_stage(self, stage: str) -> dict:
        """直接设置到某个阶段（前端跳转用）。"""
        with self._lock:
            if stage in STAGE_ORDER:
                self._current_stage = stage
                self._stage_started_ts = time.time()
                if stage == STAGE_DONE:
                    self._completed = True
                    self._completed_ts = time.time()
                    self._grant_reward()
        self._save()
        return self.get_status()

    def toggle_tips(self, enabled: bool | None = None) -> dict:
        """开/关小贴士。"""
        with self._lock:
            if enabled is None:
                self._tips_enabled = not self._tips_enabled
            else:
                self._tips_enabled = bool(enabled)
        self._save()
        return self.get_status()

    # ---------------- 奖励 ----------------

    def _grant_reward(self) -> None:
        """完成引导后给监工发奖励。"""
        if self._biosphere_ref is None:
            return
        try:
            env = self._biosphere_ref.env
            # env 有 marks 字段（监工印记）
            if hasattr(env, "marks"):
                env.marks = float(getattr(env, "marks", 0.0)) + ONBOARDING_REWARD_MARKS
        except Exception:
            pass

    # ---------------- 小贴士 ----------------

    def maybe_get_tip(self) -> str | None:
        """如果到了弹贴士的时间，返回一条贴士；否则 None。

        规则：引导完成后 7 天内，每 30 分钟弹一次（实际前端可更慢）。
        """
        with self._lock:
            if not self._tips_enabled:
                return None
            if not self._completed:
                return None
            # 7 天后不再弹
            if time.time() - self._completed_ts > 7 * 86400:
                return None
            # 距离上次弹 < 30 分钟，不弹
            if time.time() - self._last_tip_ts < 1800:
                return None
            self._last_tip_ts = time.time()
            self._tip_shown_count += 1
        self._save()
        import random
        return random.choice(TIPS)


def get_onboarding_manager() -> OnboardingManager:
    """获取 OnboardingManager 单例。"""
    return OnboardingManager.get_instance()
