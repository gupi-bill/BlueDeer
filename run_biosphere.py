"""BlueDeer 森林公司主控 run_biosphere.py

把所有数字生命子系统粘合成一个完整公司：
- 创建 11 名员工（11 个物种各一只，名字按用户给定）
- 装配 Environment / NamingSystem / Observer / EvolutionTracker /
  EvolutionVisualizer / ExternalTaskSystem / Storyteller
- 启动所有生命线程 + 自动分配 + 自动讲故事 + 自动快照 + 自动存档
- 提供 CLI：run / status / story / report / inject / snapshot / tasks

零基础读者可以这样理解：这是整个森林公司的"启动器"。
运行 `python run_biosphere.py run`，11 只动物员工就开始上班了。
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import random
import signal
import sys
import threading
import time
from collections import deque

# ruff: noqa: S110, S112

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.digital_life import (
    TASK_TYPES,
    Badger,
    Beaver,
    Butterfly,
    Deer,
    Environment,
    EvolutionTracker,
    EvolutionVisualizer,
    ExternalTaskSystem,
    Fox,
    Hare,
    Hedgehog,
    Kite,
    Lark,
    MemoryArchive,
    NamingSystem,
    Observer,
    Raven,
    RecruitSystem,
    Squirrel,
    Storyteller,
)
from core.digital_life.digital_life_form import LifeStage

# 11 名员工的物种 + 名字 + 类映射
EMPLOYEES = [
    ("deer", "鹿·忧郁", Deer),
    ("squirrel", "鼠·栗壳", Squirrel),
    ("butterfly", "蝶·绘羽", Butterfly),
    ("fox", "狐·赤谋", Fox),
    ("hedgehog", "猬·针客", Hedgehog),
    ("beaver", "狸·大坝", Beaver),
    ("raven", "鸦·黑卷", Raven),
    ("hare", "兔·霜耳", Hare),
    ("badger", "獾·土工", Badger),
    ("lark", "雀·清音", Lark),
    ("kite", "鸢·天瞰", Kite),
]

DEFAULT_SAVE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "biosphere_save.json"
)

DEFAULT_ARCHIVE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "memory_archive"
)


class Biosphere:
    """森林公司总管：把所有子系统粘合在一起。"""

    __slots__ = [
        # commit 19 P0-3 新增：随机小事件循环线程
        "_daily_events_thread",
        "_death_watcher_thread",
        # commit 29 新增：环境生态循环线程
        "_eco_tick_thread",
        # commit 14 新增：内部事件队列（招募完成等）
        "_internal_events",
        "_last_death_processed",
        "_lock",
        "_raven_agent",
        "_router",
        "_running",
        "_save_path",
        "_save_thread",
        "_snapshot_thread",
        "_stop_event",
        "employees",
        "env",
        "evolution",
        # commit 11 新增：记忆归档 + 招募系统 + 死亡监听
        "memory_archive",
        "naming",
        "observer",
        "recruit_system",
        "storyteller",
        "tasks",
        "visualizer",
    ]

    def __init__(
        self, save_path: str | None = None, archive_dir: str | None = None, router=None
    ) -> None:
        self._save_path = save_path or DEFAULT_SAVE_PATH
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._save_thread = None
        self._snapshot_thread = None
        self._running = False
        self.employees: list = []
        # 子系统
        self.env = Environment()
        # commit 31：让生命体能反向拿到 Biosphere（用于查 router / 调 LLM）
        self.env._biosphere_ref = self
        self.naming = NamingSystem()
        self.observer = Observer(self.env, self.naming)
        self.evolution = EvolutionTracker(self.env)
        self.visualizer = EvolutionVisualizer(self.evolution)
        self.tasks = ExternalTaskSystem(self.env, self.observer, self.naming)
        self.storyteller = Storyteller(
            self.env, self.naming, self.observer, self.evolution, self.tasks
        )
        # commit 11：记忆归档 + 招募系统
        self.memory_archive = MemoryArchive(archive_dir or DEFAULT_ARCHIVE_DIR)
        species_cls_map = {sp: cls for sp, _, cls in EMPLOYEES}
        names_map = {sp: name for sp, name, _ in EMPLOYEES}
        self.recruit_system = RecruitSystem(
            species_cls_map=species_cls_map,
            names_map=names_map,
            environment=self.env,
        )
        self._death_watcher_thread = None
        self._router = router  # 可选：用于调 LLM 生成遗言
        self._raven_agent = None  # 延迟初始化（需要 router）
        self._last_death_processed: float = 0.0
        # commit 14：内部事件队列
        self._internal_events: list[dict] = []
        # commit 19 P0-3：随机小事件循环线程
        self._daily_events_thread = None
        # commit 29：环境生态循环线程
        self._eco_tick_thread = None

    # ------------------------------------------------------------------
    # 装配
    # ------------------------------------------------------------------

    def bootstrap(self, load: bool = True) -> bool:
        """创建 11 名员工并注册到命名系统。

        Args:
            load: True 时尝试从存档恢复（如存档存在）。

        Returns:
            True 表示从存档恢复，False 表示全新创建。
        """
        if load and os.path.exists(self._save_path):
            self.load()
            return True

        # 全新创建：先清空环境
        self.env.reset()
        for species, name, cls in EMPLOYEES:
            lf = cls(name=name, environment=self.env)
            # commit 11：初始 zone_id = 物种岗位 zone
            lf.set_zone(species)
            self.naming.register(lf)
            self.naming.name(lf, custom_name=name)
            self.employees.append(lf)
        return False

    def start(self) -> None:
        """启动所有生命线程 + 后台子系统。"""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._stop_event.clear()
        # 启动每只生命
        for lf in self.employees:
            if not lf.is_alive() and lf._alive:
                try:
                    lf.start()
                except RuntimeError:
                    # 重复启动保护
                    pass
        # 启动自动任务分配
        self.tasks.start_auto_assigner(interval=5.0)
        # 启动自动讲故事
        self.storyteller.start_auto_storyteller(interval=30.0)
        # 启动定期快照
        self._snapshot_thread = threading.Thread(
            target=self._snapshot_loop,
            args=(60.0,),
            daemon=True,
            name="biosphere-snapshot",
        )
        self._snapshot_thread.start()
        # 启动定期存档
        self._save_thread = threading.Thread(
            target=self._save_loop,
            args=(120.0,),
            daemon=True,
            name="biosphere-save",
        )
        self._save_thread.start()
        # commit 11：启动死亡监听 + 招募推进线程
        self._death_watcher_thread = threading.Thread(
            target=self._death_watcher_loop,
            daemon=True,
            name="biosphere-death-watcher",
        )
        self._death_watcher_thread.start()
        # commit 19 P0-3：启动随机小事件循环
        self._daily_events_thread = threading.Thread(
            target=self._daily_events_loop,
            daemon=True,
            name="biosphere-daily-events",
        )
        self._daily_events_thread.start()
        # commit 29：启动环境生态循环（每秒 regenerate + 天气/事件/统计 tick）
        self._eco_tick_thread = threading.Thread(
            target=self._eco_tick_loop,
            daemon=True,
            name="biosphere-eco-tick",
        )
        self._eco_tick_thread.start()

    def stop(self) -> None:
        """停止所有线程。"""
        self._stop_event.set()
        # 停止子系统
        self.tasks.stop_auto_assigner()
        self.storyteller.stop_auto_storyteller()
        # 停止每只生命
        for lf in self.employees:
            try:
                lf._stop_event.set()
            except Exception:
                pass
        # 等线程退出
        for lf in self.employees:
            try:
                if lf.is_alive():
                    lf.join(timeout=1.0)
            except Exception:
                pass
        # 最后存一次档
        try:
            self.save()
        except Exception:
            pass
        with self._lock:
            self._running = False

    # ------------------------------------------------------------------
    # 后台循环
    # ------------------------------------------------------------------

    def _snapshot_loop(self, interval: float) -> None:
        """定期拍进化快照。"""
        while not self._stop_event.is_set():
            try:
                self.evolution.take_snapshot()
            except Exception:
                pass
            self._stop_event.wait(interval)

    def _save_loop(self, interval: float) -> None:
        """定期存档。"""
        while not self._stop_event.is_set():
            self._stop_event.wait(interval)
            try:
                self.save()
            except Exception:
                pass

    def _death_watcher_tick(self) -> None:
        """死亡监听 + 招募推进单次步进。"""
        try:
            self._process_new_deaths()
            self._process_recruit_progress()
        except Exception:
            pass

    def _death_watcher_loop(self) -> None:
        """commit 11：死亡监听 + 招募推进循环。

        每秒做两件事：
        1. 扫描 death_log，发现新死亡 → 通知 recruit_system + 归档记忆
        2. 调 recruit_system.tick() 推进招募状态机，完成时生成新员工
        """
        while not self._stop_event.is_set():
            self._death_watcher_tick()
            self._stop_event.wait(1.0)

    def _process_new_deaths(self) -> None:
        """扫描 death_log，处理新死亡事件。"""
        with self._lock:
            death_log = list(self.env.death_log)
        for entry in death_log:
            if entry.get("time", 0) <= self._last_death_processed:
                continue
            species = entry.get("species", "")
            name = entry.get("name", "")
            # 1. 通知招募系统
            self.recruit_system.on_death(species)
            # 2. 归档记忆（找到对应的 life_form 对象）
            lf = self._find_employee_by_name(name)
            if lf is not None:
                self._archive_deceased(lf)
            self._last_death_processed = entry.get("time", time.time())

    def _find_employee_by_name(self, name: str):
        """按名字找员工（含已故）。"""
        with self._lock:
            for lf in self.employees:
                if lf._name_obj == name:
                    return lf
        return None

    def _archive_deceased(self, life_form) -> None:
        """归档逝者：调 LLM 生成摘要+遗言，写入 MemoryArchive。

        LLM 不可用时降级用模板。
        """
        # 尝试调 LLM 生成 life_summary + last_words
        life_summary, last_words = self._generate_epitaph(life_form)
        life_form.life_summary = life_summary
        life_form.last_words = last_words
        # 写入磁盘归档
        try:
            self.memory_archive.archive_deceased(
                life_form,
                life_summary=life_summary,
                last_words=last_words,
            )
        except Exception:
            pass

    def _generate_epitaph(self, life_form) -> tuple[str, str]:
        """调 LLM 生成生平摘要 + 遗言。

        LLM 不可用时降级用模板。

        Returns:
            (life_summary, last_words)
        """
        # 模板降级（无 router 或调 LLM 失败时用）
        template_summary = (
            f"{life_form._name_obj}（{life_form.species}）"
            f"活了 {life_form.age:.1f} 天，"
            f"性别 {life_form.gender}，"
            f"留下 {len(life_form.core_memory)} 条核心记忆。"
        )
        template_last_words = f"{life_form._name_obj} 静静地离开了森林公司。"

        if self._router is None:
            return template_summary, template_last_words

        # 尝试调 LLM
        try:
            import asyncio

            prompt = (
                f"你是 BlueDeer 森林公司的故事讲述者。"
                f"{life_form._name_obj}（物种：{life_form.species}，"
                f"性别：{life_form.gender}，年龄：{life_form.age:.1f} 天）"
                f"刚刚去世。\n"
                f"核心记忆：{life_form.core_memory[-5:]}\n\n"
                f"请用 50 字以内生成两段文本：\n"
                f"SUMMARY: 一句生平摘要\n"
                f"LAST_WORDS: 一句遗言\n"
            )
            loop = asyncio.new_event_loop()
            try:
                response = loop.run_until_complete(self._router.complete(prompt))
            finally:
                loop.close()
            text = str(response) if response else ""
            # 解析 SUMMARY / LAST_WORDS
            summary = template_summary
            last_words = template_last_words
            for line in text.split("\n"):
                line = line.strip()
                if line.startswith("SUMMARY:"):
                    summary = line[len("SUMMARY:") :].strip() or summary
                elif line.startswith("LAST_WORDS:"):
                    last_words = line[len("LAST_WORDS:") :].strip() or last_words
            return summary, last_words
        except Exception:
            return template_summary, template_last_words

    def _process_recruit_progress(self) -> None:
        """推进招募状态机，完成时生成新员工。"""
        completed = self.recruit_system.tick()
        for event in completed:
            if event.get("type") == "recruit_complete":
                species = event.get("species", "")
                new_lf = self.recruit_system.complete_recruit(species)
                if new_lf is not None:
                    with self._lock:
                        # 替换同物种的已故员工
                        self.employees = [
                            new_lf if (lf.species == species and not lf._alive) else lf
                            for lf in self.employees
                        ]
                        # 注册新员工
                        self.naming.register(new_lf)
                        self.naming.name(new_lf, custom_name=new_lf._name_obj)
                        new_lf.set_zone(species)
                    # 启动新员工线程
                    try:
                        new_lf.start()
                    except RuntimeError:
                        pass
                    # commit 14：推内部事件供 GameServer SSE 通道转发
                    self._internal_events.append(
                        {
                            "type": "recruit_completed",
                            "species": species,
                            "name": new_lf._name_obj,
                        }
                    )

    async def async_step(self) -> None:
        """异步非阻塞步进：推进生态、招募、死亡监控各一步。"""
        with self._lock:
            if not self._running:
                return
        self._process_recruit_progress()
        self._death_watcher_tick()
        if self._eco_tick_thread is not None and self._eco_tick_thread.is_alive():
            pass
        else:
            self.env._eco_tick()
        await asyncio.sleep(0)

    def pop_internal_events(self) -> list[dict]:
        """commit 14：取出内部累积的事件并清空。

        供 GameServer 在 SSE 推送时调用，把内部事件
        （招募完成等）合并到 events 通道推给前端。

        Returns:
            事件列表（已复制，调用方清空原队列）。
        """
        with self._lock:
            events = list(self._internal_events)
            self._internal_events.clear()
            return events

    # ------------------------------------------------------------------
    # commit 19 P0-3：随机小事件
    # ------------------------------------------------------------------

    # 事件类型表：type → (中文描述, 效果函数)
    # 效果函数签名：(life_form) → dict（返回事件 payload）
    _DAILY_EVENT_TYPES: list[tuple[str, str]] = [
        ("coffee_spill", "咖啡洒了，弄脏代码笔记"),
        ("bug_found", "突然发现一只真虫子爬过键盘"),
        ("inspiration", "灵光一闪，写出优雅代码片段"),
        ("nap_accident", "午休睡过头，被监工轻轻拍醒"),
        ("snack_gift", "前台送来一袋神秘零食"),
        ("quarrel", "和同事为代码风格吵了两句"),
        ("compliment", "被路过同事夸了一句"),
    ]

    def _eco_tick_loop(self) -> None:
        """commit 29：环境生态循环（每秒一次）。

        负责：
        - 调 env.regenerate() 食物/植物再生
        - 调 env.tick_weather() 天气切换检查
        - 调 env.tick_eco_events() 生态事件触发 + 清理
        - 调 env.tick_eco_stats() 生态统计更新
        - commit 33：调 env.tick_immersive_systems() 沉浸感三子系统
        """
        import time as _time

        while not self._stop_event.is_set():
            try:
                now_ts = _time.time()
                self.env.regenerate()
                self.env.tick_weather(now_ts)
                self.env.tick_eco_events(now_ts)
                self.env.tick_eco_stats(now_ts)
                # commit 33：沉浸感三子系统（情感光环 + 记忆碎片 + 自发社交）
                self.env.tick_immersive_systems(dt=1.0, router=self._router)
            except Exception:
                pass
            if self._stop_event.wait(1.0):
                return

    def _daily_events_loop(self) -> None:
        """commit 19 P0-3：随机小事件循环。

        每 60 秒触发一次随机小事件（模拟"每天 1-2 个微事件"，
        缩短到 60 秒以便观察）。事件随机选一个活体员工，
        应用效果（能量/情绪/好感/记忆）并推到 _internal_events
        让 SSE 转发到前端。
        """
        while not self._stop_event.is_set():
            # 60 秒一次
            if self._stop_event.wait(60.0):
                return
            try:
                self._trigger_random_event()
            except Exception:
                pass

    def _trigger_random_event(self) -> dict | None:
        """触发一次随机小事件，返回事件 payload。

        Returns:
            事件 dict，或 None（没有活体员工时）。
        """
        with self._lock:
            alive_emps = [lf for lf in self.employees if lf._alive]
        if not alive_emps:
            return None
        lf = random.choice(alive_emps)
        event_type, desc = random.choice(self._DAILY_EVENT_TYPES)
        # 按事件类型应用效果
        payload = self._apply_daily_event(lf, event_type, desc)
        # 推到内部事件队列（SSE 转发）
        with self._lock:
            self._internal_events.append(payload)
        return payload

    def _apply_daily_event(self, life_form, event_type: str, desc: str) -> dict:
        """对 life_form 应用 event_type 效果，返回事件 payload。

        Args:
            life_form: 受影响的员工。
            event_type: 事件类型。
            desc: 事件中文描述。

        Returns:
            事件 payload dict（含 type/name/species/effect/desc/time）。
        """
        effect: dict = {}
        with life_form._lock:
            if event_type == "coffee_spill":
                life_form.energy = max(0.0, life_form.energy - 10)
                life_form.mood_score = max(0.0, life_form.mood_score - 5)
                effect = {"energy": -10, "mood_score": -5}
            elif event_type == "bug_found":
                life_form.mood_score = min(100.0, life_form.mood_score + 5)
                effect = {"mood_score": +5}
            elif event_type == "inspiration":
                life_form.energy = min(100.0, life_form.energy + 5)
                life_form.mood_score = min(100.0, life_form.mood_score + 10)
                effect = {"energy": +5, "mood_score": +10}
            elif event_type == "nap_accident":
                life_form.mood_score = max(0.0, life_form.mood_score - 3)
                effect = {"mood_score": -3}
            elif event_type == "snack_gift":
                life_form.hunger = max(0.0, life_form.hunger - 20)
                life_form.fondness = min(100, life_form.fondness + 3)
                effect = {"hunger": -20, "fondness": +3}
            elif event_type == "quarrel":
                life_form.mood_score = max(0.0, life_form.mood_score - 8)
                effect = {"mood_score": -8}
            elif event_type == "compliment":
                life_form.mood_score = min(100.0, life_form.mood_score + 6)
                life_form.fondness = min(100, life_form.fondness + 1)
                effect = {"mood_score": +6, "fondness": +1}
            life_form._remember(f"小事件：{desc}", importance="normal")
        return {
            "type": "daily_event",
            "event_type": event_type,
            "desc": desc,
            "name": life_form._name_obj,
            "species": life_form.species,
            "effect": effect,
            "time": time.time(),
        }

    # ------------------------------------------------------------------
    # 操作
    # ------------------------------------------------------------------

    def inject_task(self, task_type: str, description: str = "") -> dict:
        """注入一个外部任务。"""
        task = self.tasks.inject(task_type, description=description)
        return task.to_dict()

    def status(self) -> dict:
        """整体状态。"""
        return {
            "running": self._running,
            "env": self.env.status(),
            "naming": {
                "registered": len(self.naming.all_ids()),
            },
            "tasks": self.tasks.status(),
            "storyteller": self.storyteller.status(),
            "evolution": self.evolution.status(),
            "employees": [
                {
                    "name": lf._name_obj,
                    "species": lf.species,
                    "alive": lf._alive,
                    "energy": round(lf.energy, 1),
                    "health": round(lf.health, 1),
                    "age_days": round(lf.age, 1),
                    "stage": lf.life_stage.value if lf.life_stage else None,
                    # commit 11 新增字段
                    "fondness": lf.fondness,
                    "current_zone_id": lf.current_zone_id,
                    "resting_until": lf.resting_until,
                    "core_memory_count": len(lf.core_memory),
                    "life_summary": lf.life_summary,
                    "last_words": lf.last_words,
                    "mood": lf.mood,
                    "current_action": lf.current_action.value,
                    "sleeping": lf.sleeping,
                    # commit 19 P0-1/P0-2 新增字段
                    "mood_score": round(lf.mood_score, 1),
                    "skills": list(lf.skills),
                    # commit 28：当前特有行为
                    "current_behavior": lf.current_behavior,
                    "current_behavior_label": (
                        (lf.current_behavior_cfg or {}).get("label", "")
                        if lf.current_behavior
                        else ""
                    ),
                    "behavior_particles": (
                        (lf.current_behavior_cfg or {}).get("particles", "")
                        if lf.current_behavior
                        else ""
                    ),
                    # commit 37：Agent 工具调用状态（前端用于头顶图标）
                    "agent_work_status": getattr(lf, "_tool_call_status", "") or "",
                    "agent_pending_tasks": len(
                        getattr(lf, "_pipeline_task_inbox", []) or []
                    ),
                    "bound_tools_count": len(getattr(lf, "bound_tools", []) or []),
                    # commit 39：非正式角色（前端 tooltip 显示徽章）
                    "informal_roles": list(getattr(lf, "informal_roles", []) or []),
                    # commit 40：突变（前端 tooltip 显示✨徽章）
                    "mutations": list(getattr(lf, "mutations", []) or []),
                }
                for lf in self.employees
            ],
            # commit 11 新增子系统状态
            "memory_archive": self.memory_archive.status(),
            "recruit_system": self.recruit_system.status(),
            # commit 19 P0-3：随机小事件统计
            "daily_events_enabled": self._daily_events_thread is not None
            and self._daily_events_thread.is_alive(),
        }

    def interact_with_employee(self, name: str, action: str, **kwargs) -> dict:
        """commit 11：监工与员工互动。

        Args:
            name: 员工名字。
            action: 互动类型（feed/greet/set_schedule/mark_focus/wake/forage）。
            **kwargs: 互动参数（如 bedtime/wakeup/duration_sec/amount）。

        Returns:
            互动结果 dict。
        """
        lf = self._find_employee_by_name(name)
        if lf is None:
            return {"ok": False, "reason": "员工不存在"}
        if action == "feed":
            return lf.interact_feed(amount=kwargs.get("amount", 20.0))
        if action == "greet":
            return lf.interact_greet()
        if action == "set_schedule":
            return lf.interact_set_schedule(
                bedtime=kwargs.get("bedtime", "23:00"),
                wakeup=kwargs.get("wakeup", "06:00"),
            )
        if action == "mark_focus":
            return lf.interact_mark_focus()
        if action == "wake":
            return lf.interact_wake()
        if action == "forage":
            return lf.start_foraging(duration_sec=kwargs.get("duration_sec", 30.0))
        return {"ok": False, "reason": f"未知动作: {action}"}

    def start_recruit(self, species: str) -> dict:
        """commit 11：监工手动启动招募。"""
        return self.recruit_system.start_recruit(species)

    def get_memory_archive_status(self) -> dict:
        """commit 11：记忆归档状态。"""
        return self.memory_archive.status()

    def list_deceased(self, species: str | None = None) -> list[dict]:
        """commit 11：列出逝者记忆。"""
        if species:
            return self.memory_archive.list_deceased(species)
        return self.memory_archive.all_deceased()

    def raven_narrate(self, species: str, index: int = -1) -> dict:
        """commit 13：渡鸦讲述某位逝者的故事。

        Args:
            species: 物种 ID。
            index: 逝者在物种归档中的索引（-1 表示最近一位）。

        Returns:
            {"ok": True, "narration": "...", "entry": {...}}
            失败返回 {"ok": False, "reason": "..."}
        """
        if index < 0:
            entry = self.memory_archive.get_latest(species)
        else:
            entry = self.memory_archive.get_deceased(species, index)
        if entry is None:
            return {"ok": False, "reason": "找不到该逝者"}

        # 模板降级（无 router 或调 LLM 失败时用）
        template = (
            f"渡鸦翻开档案：「{entry.get('name', '?')}，"
            f"{entry.get('species', '?')}，"
            f"活了 {entry.get('age_days', 0):.1f} 天。"
            f"{entry.get('life_summary', '')}"
            f"{entry.get('last_words', '')}」"
        )

        if self._router is None:
            return {"ok": True, "narration": template, "entry": entry}

        try:
            import asyncio

            memory_snippet = entry.get("core_memory", [])[-3:]
            prompt = (
                f"你是 BlueDeer 森林公司的渡鸦档案员鸦·黑卷，"
                f"正在向新同事讲述一位前辈的故事。\n"
                f"逝者：{entry.get('name', '?')}（{entry.get('species', '?')}）\n"
                f"生平：{entry.get('life_summary', '')}\n"
                f"遗言：{entry.get('last_words', '')}\n"
                f"核心记忆：{memory_snippet}\n\n"
                f"请用 80 字以内、第一人称讲述这位前辈的故事，"
                f"语气庄重而温暖。"
            )
            loop = asyncio.new_event_loop()
            try:
                response = loop.run_until_complete(self._router.complete(prompt))
            finally:
                loop.close()
            narration = str(response).strip() if response else ""
            if not narration:
                narration = template
            return {"ok": True, "narration": narration, "entry": entry}
        except Exception:
            return {"ok": True, "narration": template, "entry": entry}

    def story_text(self, n: int = 20) -> str:
        """最近 N 条故事文本。"""
        return self.storyteller.render_recent_text(n=n)

    def story_markdown(self, n: int | None = None) -> str:
        """故事 markdown 全量或限量。"""
        return self.storyteller.render_markdown(n=n)

    def evolution_report(self) -> str:
        """进化文本报告。"""
        return self.visualizer.render_text()

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def save(self, path: str | None = None) -> dict:
        """保存状态到 JSON（原子写入）。"""
        target = path or self._save_path
        data = {
            "version": 2,  # commit 11 升级到 v2（含新字段）
            "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "env": {
                "food_available": self.env.food_available,
                "death_log_size": len(self.env.death_log),
                "birth_log_size": len(self.env.birth_log),
            },
            "employees": [
                {
                    "name": lf._name_obj,
                    "species": lf.species,
                    "gender": lf.gender,
                    "birth_time": lf.birth_time,
                    "energy": lf.energy,
                    "health": lf.health,
                    "hunger": lf.hunger,
                    "alive": lf._alive,
                    "stage": lf.life_stage.value if lf.life_stage else None,
                    # commit 11 新增字段
                    "fondness": lf.fondness,
                    "current_zone_id": lf.current_zone_id,
                    "resting_until": lf.resting_until,
                    "core_memory": list(lf.core_memory),
                    "life_summary": lf.life_summary,
                    "last_words": lf.last_words,
                    "bedtime": lf.genome.get("bedtime", "23:00"),
                    "wakeup_time": lf.genome.get("wakeup_time", "06:00"),
                    # commit 39：长期目标管理 + 团队角色演化
                    "informal_roles": list(getattr(lf, "informal_roles", []) or []),
                    "project_contributions": dict(
                        getattr(lf, "project_contributions", {}) or {}
                    ),
                    "help_count": int(getattr(lf, "_help_count", 0) or 0),
                    "social_count": int(getattr(lf, "_social_count", 0) or 0),
                    "supervisor_interact_count": int(
                        getattr(lf, "_supervisor_interact_count", 0) or 0
                    ),
                    "teach_count": int(getattr(lf, "_teach_count", 0) or 0),
                    "crisis_resolved_count": int(
                        getattr(lf, "_crisis_resolved_count", 0) or 0
                    ),
                    "work_output": float(getattr(lf, "_work_output", 0.0) or 0.0),
                    # commit 40：进化突变
                    "mutations": list(getattr(lf, "mutations", []) or []),
                    "appearance_modifiers": dict(
                        getattr(lf, "appearance_modifiers", {}) or {}
                    ),
                    # commit 52-2：补全持久化字段（之前丢失，重启即清零）
                    "mood_score": float(getattr(lf, "mood_score", 50.0) or 50.0),
                    "emotional_state": dict(getattr(lf, "emotional_state", {}) or {}),
                    "skills": list(getattr(lf, "skills", []) or []),
                    "memory_recent": list(getattr(lf, "memory_recent", []) or []),
                    "memory_long_term": list(getattr(lf, "memory_long_term", []) or []),
                    "relationships": dict(getattr(lf, "relationships", {}) or {}),
                    "relationship_tags": dict(
                        getattr(lf, "relationship_tags", {}) or {}
                    ),
                    "wisdom": float(getattr(lf, "wisdom", 0.0) or 0.0),
                    "trauma_events": list(getattr(lf, "trauma_events", []) or []),
                    "retirement_wish": str(getattr(lf, "retirement_wish", "") or ""),
                    "wish_fulfilled": bool(
                        getattr(lf, "wish_fulfilled", False) or False
                    ),
                }
                for lf in self.employees
            ],
            "tasks_status": self.tasks.status(),
            "storyteller_status": self.storyteller.status(),
            # commit 11：招募系统状态
            "recruit_states": self.recruit_system.get_all_states(),
        }
        tmp = target + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, target)
        return {"path": target, "size": os.path.getsize(target)}

    def load(self, path: str | None = None) -> dict:
        """从 JSON 恢复状态。"""
        target = path or self._save_path
        if not os.path.exists(target):
            return {"ok": False, "reason": "save file not found"}
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 恢复环境
        env_data = data.get("env", {})
        with self.env._lock:
            self.env.food_available = env_data.get("food_available", 1000.0)

        # 恢复员工
        species_cls = {sp: cls for sp, _, cls in EMPLOYEES}
        for emp in data.get("employees", []):
            sp = emp.get("species")
            cls = species_cls.get(sp)
            if cls is None:
                continue
            lf = cls(
                name=emp.get("name", ""),
                gender=emp.get("gender", "female"),
                environment=self.env,
                birth_time=emp.get("birth_time", time.time()),
            )
            lf.energy = emp.get("energy", 80.0)
            lf.health = emp.get("health", 100.0)
            lf.hunger = emp.get("hunger", 20.0)
            lf._alive = emp.get("alive", True)
            stage_str = emp.get("stage")
            if stage_str:
                try:
                    lf.life_stage = LifeStage(stage_str)
                except ValueError:
                    pass
            # commit 11：恢复新字段
            lf.fondness = emp.get("fondness", 50)
            lf.current_zone_id = emp.get("current_zone_id", sp or "")
            lf.resting_until = emp.get("resting_until")
            lf.core_memory = list(emp.get("core_memory", []))
            lf.life_summary = emp.get("life_summary", "")
            lf.last_words = emp.get("last_words", "")
            # 恢复作息时间
            bedtime = emp.get("bedtime", "23:00")
            wakeup = emp.get("wakeup_time", "06:00")
            lf.genome["bedtime"] = bedtime
            lf.genome["wakeup_time"] = wakeup
            # commit 39：恢复长期目标管理 + 团队角色演化字段
            try:
                lf.informal_roles = list(emp.get("informal_roles", []) or [])
                lf.project_contributions = dict(
                    emp.get("project_contributions", {}) or {}
                )
                lf._help_count = int(emp.get("help_count", 0) or 0)
                lf._social_count = int(emp.get("social_count", 0) or 0)
                lf._supervisor_interact_count = int(
                    emp.get("supervisor_interact_count", 0) or 0
                )
                lf._teach_count = int(emp.get("teach_count", 0) or 0)
                lf._crisis_resolved_count = int(
                    emp.get("crisis_resolved_count", 0) or 0
                )
                lf._work_output = float(emp.get("work_output", 0.0) or 0.0)
                # commit 40：进化突变
                lf.mutations = list(emp.get("mutations", []) or [])
                lf.appearance_modifiers = dict(
                    emp.get("appearance_modifiers", {}) or {}
                )
                # commit 52-2：恢复之前丢失的持久化字段
                lf.mood_score = float(emp.get("mood_score", 50.0) or 50.0)
                saved_emo = emp.get("emotional_state") or {}
                if isinstance(saved_emo, dict) and saved_emo:
                    lf.emotional_state.update(saved_emo)
                lf.skills = list(emp.get("skills", []) or [])
                # memory_recent 是 deque，存为 list，恢复时重新装入 deque
                saved_recent = emp.get("memory_recent", []) or []
                try:
                    lf.memory_recent.extend(saved_recent)
                except Exception:
                    lf.memory_recent = deque(saved_recent, maxlen=100)
                lf.memory_long_term = list(emp.get("memory_long_term", []) or [])
                saved_rel = emp.get("relationships") or {}
                if isinstance(saved_rel, dict):
                    lf.relationships.update(saved_rel)
                saved_tags = emp.get("relationship_tags") or {}
                if isinstance(saved_tags, dict):
                    lf.relationship_tags.update(saved_tags)
                lf.wisdom = float(emp.get("wisdom", 0.0) or 0.0)
                lf.trauma_events = list(emp.get("trauma_events", []) or [])
                lf.retirement_wish = str(emp.get("retirement_wish", "") or "")
                lf.wish_fulfilled = bool(emp.get("wish_fulfilled", False) or False)
            except Exception:
                pass
            self.naming.register(lf)
            self.naming.name(lf, custom_name=emp.get("name", lf._name_obj))
            self.employees.append(lf)

        # commit 11：恢复招募系统状态
        recruit_states = data.get("recruit_states", {})
        if recruit_states:
            from core.digital_life.recruit_system import SpeciesState

            for sp, state_str in recruit_states.items():
                try:
                    new_state = SpeciesState(state_str)
                    self.recruit_system._states[sp] = new_state
                except (ValueError, KeyError):
                    pass
        return {"ok": True, "loaded": len(self.employees)}


# ----------------------------------------------------------------------
# CLI 命令
# ----------------------------------------------------------------------


async def _async_run_loop(bio: Biosphere, duration: float) -> None:
    """异步主循环：async_step 非阻塞步进。"""
    stop_event = threading.Event()
    _original_sigint = signal.getsignal(signal.SIGINT)

    def _sigint(*_):
        print("\n[*] 收到信号，停止中...")
        stop_event.set()

    signal.signal(signal.SIGINT, _sigint)
    try:
        if duration > 0:
            await asyncio.sleep(duration)
        else:
            while not stop_event.is_set():
                await bio.async_step()
                await asyncio.sleep(1.0)
    finally:
        signal.signal(signal.SIGINT, _original_sigint)
        bio.stop()


def cmd_run(args) -> int:
    """启动森林公司（异步主循环）。"""
    bio = Biosphere(save_path=args.save_path)
    loaded = bio.bootstrap(load=not args.no_load)
    bio.start()
    print(
        f"[*] BlueDeer 森林公司已启动：{len(bio.employees)} 名员工"
        f"（{'从存档恢复' if loaded else '全新创建'}）"
    )
    print(f"[*] 存档路径：{bio._save_path}")
    print("[*] Ctrl+C 停止")
    try:
        asyncio.run(_async_run_loop(bio, args.duration))
    except KeyboardInterrupt:
        bio.stop()
    return 0


def cmd_status(args) -> int:
    """打印状态。"""
    bio = Biosphere(save_path=args.save_path)
    bio.bootstrap(load=True)
    s = bio.status()
    print("=" * 60)
    print("BlueDeer 森林公司状态")
    print("=" * 60)
    print(f"运行中：{s['running']}")
    print(f"食物：{s['env']['food_available']}")
    print(f"种群：{s['env']['population_count']} 只")
    print(
        f"任务：待办 {s['tasks']['pending']} / 进行 {s['tasks']['running']} / "
        f"完成 {s['tasks']['completed']} / 失败 {s['tasks']['failed']}"
    )
    print(f"故事章节：{s['storyteller']['total_chapters']}")
    print(f"进化快照：{s['evolution']['snapshot_count']}")
    print("\n员工：")
    for emp in s["employees"]:
        print(
            f"  {emp['name']:8s}  物种={emp['species']:9s}  "
            f"阶段={emp['stage'] or '?':8s}  能量={emp['energy']:5.1f}  "
            f"健康={emp['health']:5.1f}  年龄={emp['age_days']}天  "
            f"{'存活' if emp['alive'] else '已故'}"
        )
    return 0


def cmd_story(args) -> int:
    """打印最近故事。"""
    bio = Biosphere(save_path=args.save_path)
    bio.bootstrap(load=True)
    print(bio.story_text(n=args.n))
    return 0


def cmd_report(args) -> int:
    """打印进化报告。"""
    bio = Biosphere(save_path=args.save_path)
    bio.bootstrap(load=True)
    print(bio.evolution_report())
    return 0


def cmd_inject(args) -> int:
    """注入一个任务。"""
    bio = Biosphere(save_path=args.save_path)
    bio.bootstrap(load=True)
    bio.start()
    result = bio.inject_task(args.task_type, description=args.desc)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # 给一点时间让任务跑完
    time.sleep(2.0)
    bio.stop()
    return 0


def cmd_snapshot(args) -> int:
    """生成快照并保存。"""
    bio = Biosphere(save_path=args.save_path)
    bio.bootstrap(load=True)
    snap = bio.evolution.take_snapshot()
    result = bio.save()
    print(f"[OK] 快照已生成，世代 {snap.generation}")
    print(f"[OK] 存档已保存：{result['path']} ({result['size']} 字节)")
    return 0


def cmd_list_tasks(args) -> int:
    """列出所有任务类型。"""
    print("支持的 11 种任务类型：")
    for tid, spec in TASK_TYPES.items():
        print(
            f"  {tid:14s}  物种={spec['species']:9s}  "
            f"难度={spec['difficulty']}  {spec['description']}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """构造 CLI 解析器。"""
    parser = argparse.ArgumentParser(
        prog="run_biosphere",
        description="BlueDeer 森林公司主控",
    )
    parser.add_argument(
        "--save-path",
        default=DEFAULT_SAVE_PATH,
        help=f"存档路径（默认 {DEFAULT_SAVE_PATH}）",
    )
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="启动森林公司")
    p_run.add_argument(
        "--duration", type=float, default=0, help="运行时长（秒），0=持续运行"
    )
    p_run.add_argument("--no-load", action="store_true", help="不加载存档，全新启动")
    p_run.set_defaults(func=cmd_run)

    p_status = sub.add_parser("status", help="打印当前状态")
    p_status.set_defaults(func=cmd_status)

    p_story = sub.add_parser("story", help="打印最近故事")
    p_story.add_argument("-n", type=int, default=20, help="显示条数")
    p_story.set_defaults(func=cmd_story)

    p_report = sub.add_parser("report", help="打印进化报告")
    p_report.set_defaults(func=cmd_report)

    p_inject = sub.add_parser("inject", help="注入一个任务")
    p_inject.add_argument("task_type", choices=list(TASK_TYPES.keys()), help="任务类型")
    p_inject.add_argument("--desc", default="", help="任务描述")
    p_inject.set_defaults(func=cmd_inject)

    p_snap = sub.add_parser("snapshot", help="生成快照并保存")
    p_snap.set_defaults(func=cmd_snapshot)

    p_tasks = sub.add_parser("tasks", help="列出所有任务类型")
    p_tasks.set_defaults(func=cmd_list_tasks)

    return parser


def main(argv: list | None = None) -> int:
    """CLI 入口。

    Args:
        argv: 命令行参数列表；None 表示用 sys.argv[1:]。
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
