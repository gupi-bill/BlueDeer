"""Storyteller 数字生命故事讲述者。

职责：
- 持续监听 Environment.event_log，把每一条事件编织成一段故事章节
- 支持后台自动讲故事（start_auto_storyteller）
- 提供 tell / tell_recent / render_markdown / render_recent_text
- 用于 /story 页面：浏览器打开看到的是"森林里今天发生了什么"

零基础读者可以这样理解：
- 整个数字生命系统里发生的每一件事（出生、死亡、繁殖、接活、交活、
  饲养员干预……）都会被 Environment 记到 event_log。
- Storyteller 定期去 event_log 里"拉新"，把每条事件翻译成一句人话，
  存进自己的章节列表，再按需渲染成 markdown 或纯文本返回给前端。
"""

from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import datetime
import threading
from collections import deque

# ----------------------------------------------------------------------
# 故事章节模板（按事件类型分类）
# ----------------------------------------------------------------------

# 每个模板接收 data dict，返回 (title, content, actors)
_STORY_TEMPLATES = {
    "birth": lambda d: (
        f"新生命：{d.get('name', '?')}",
        (f"{d.get('name', '?')} 在此刻降临森林，"
        f"它是 {d.get('species', '?')} 家族的新成员，性别 {d.get('gender', '?')}。"),
        [d.get("name", "?")],
    ),
    "death": lambda d: (
        f"离世：{d.get('name', '?')}",
        (f"{d.get('name', '?')} 因 {d.get('reason', '未知')} 永远离开了森林，"
        f"它是一只 {d.get('species', '?')}。"),
        [d.get("name", "?")],
    ),
    "reproduction": lambda d: (
        f"喜得贵子：{d.get('child', '?')}",
        (f"{d.get('parents', ['?', '?'])[0]} 与 "
        f"{d.get('parents', ['?', '?'])[1]} 共同孕育了 {d.get('child', '?')}，"
        f"种群 {d.get('species', '?')} 又添新血。"),
        d.get("parents", []) + [d.get("child", "?")],
    ),
    "task_injected": lambda d: (
        f"新差事：{d.get('task_id', '?')}",
        (f"外部世界送来一份新活计 {d.get('task_id', '?')}，"
        f"类型 {d.get('task_type', '?')}，等待员工接单。"),
        [],
    ),
    "task_assigned": lambda d: (
        f"接单：{d.get('worker', '?')}",
        (f"{d.get('worker', '?')} 接下了 {d.get('task_id', '?')} "
        f"（{d.get('task_type', '?')}），开始干活。"),
        [d.get("worker", "?")],
    ),
    "task_completed": lambda d: (
        f"交活：{d.get('worker', '?')}",
        (
            (
                f"{d.get('worker', '?')} 出色地完成了 {d.get('task_id', '?')}，"
                f"赢得了奖励。"
            )
            if d.get("success")
            else (
                f"{d.get('worker', '?')} 在 {d.get('task_id', '?')} 上栽了跟头，"
                f"未能完成。"
            )
        ),
        [d.get("worker", "?")],
    ),
    "task_expired": lambda d: (
        f"超时：{d.get('task_id', '?')}",
        f"{d.get('task_id', '?')} 因迟迟无人接单而超时收回。",
        [],
    ),
    "intervene_feed": lambda d: (
        "饲养员：投食",
        (f"饲养员向森林投放了 {d.get('amount', 0)} 单位食物，"
        f"饥肠辘辘的动物们纷纷前来觅食。"),
        [],
    ),
    "intervene_drought": lambda d: (
        "干旱来袭",
        (f"一场 {d.get('severity', '?')} 级干旱席卷森林，"
        f"食物再生大幅放缓，动物们要做好过苦日子的准备。"),
        [],
    ),
    "intervene_cold_wave": lambda d: (
        "寒潮预警",
        (f"寒潮来袭，预计持续 {d.get('duration_hours', '?')} 小时，"
        f"动物们纷纷躲进巢穴取暖。"),
        [],
    ),
    "intervene_force_breed": lambda d: (
        "饲养员：撮合",
        (f"饲养员撮合 {d.get('parent_a', '?')} 与 {d.get('parent_b', '?')}，"
        f"{'成功' if d.get('ok') else '但未能成功'}繁育后代。"),
        [d.get("parent_a", "?"), d.get("parent_b", "?")],
    ),
    "intervene_isolate": lambda d: (
        "饲养员：隔离",
        f"{d.get('life_id', '?')} 被饲养员隔离观察，暂时无法与其他动物接触。",
        [d.get("life_id", "?")],
    ),
    "intervene_release": lambda d: (
        "饲养员：释放",
        f"{d.get('life_id', '?')} 解除隔离，重获自由。",
        [d.get("life_id", "?")],
    ),
    "lark_sing": lambda d: (
        "雀鸣清晨",
        (f"{d.get('singer', '?')} 唱起清晨的歌，森林中其他同伴受到鼓舞，"
        f"能量得到恢复。"),
        [d.get("singer", "?")],
    ),
}


def _now_iso() -> str:
    """当前时间的 ISO 字符串。"""
    return datetime.datetime.now().isoformat(timespec="seconds")


def _human_time(iso: str) -> str:
    """ISO 时间转人类可读格式。"""
    try:
        dt = datetime.datetime.fromisoformat(iso)
        return dt.strftime("%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return iso


class Storyteller:
    """数字生命故事讲述者。"""

    __slots__ = [
        "_auto_thread",
        "_chapters",
        "_env",
        "_evolution",
        "_last_event_count",
        "_lock",
        "_naming",
        "_observer",
        "_stop_event",
        "_tasks",
    ]

    def __init__(
        self,
        environment,
        naming=None,
        observer=None,
        evolution_tracker=None,
        external_tasks=None,
    ) -> None:
        """初始化 Storyteller。

        Args:
            environment: 共享 Environment，事件源。
            naming: 可选 NamingSystem，用于把 ID 翻译成名字。
            observer: 可选 Observer，用于读取干预历史。
            evolution_tracker: 可选 EvolutionTracker，用于读取种群快照。
            external_tasks: 可选 ExternalTaskSystem，用于读取任务绩效。
        """
        self._env = environment
        self._naming = naming
        self._observer = observer
        self._evolution = evolution_tracker
        self._tasks = external_tasks
        self._lock = threading.RLock()
        self._chapters: deque = deque(maxlen=2000)
        self._last_event_count = 0
        self._auto_thread = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # 章节生成
    # ------------------------------------------------------------------

    def _make_chapter(
        self,
        category: str,
        title: str,
        content: str,
        actors: list | None = None,
        time_iso: str | None = None,
    ) -> dict:
        """构造一个章节 dict。"""
        return {
            "time": time_iso or _now_iso(),
            "category": category,
            "title": title,
            "content": content,
            "actors": list(actors or []),
        }

    def _event_to_chapter(self, event: dict) -> dict | None:
        """把一条 event_log 事件转成章节，未知事件返回 None。"""
        etype = event.get("type", "")
        data = event.get("data", {}) or {}
        template = _STORY_TEMPLATES.get(etype)
        if template is None:
            return None
        try:
            title, content, actors = template(data)
        except Exception:
            return None
        return self._make_chapter(
            category=etype,
            title=title,
            content=content,
            actors=actors,
            time_iso=event.get("time") or _now_iso(),
        )

    def poll_events(self) -> int:
        """从 event_log 拉取新事件并转成章节，返回新增章节数。

        用 _last_event_count 记录上次处理到哪，避免重复讲故事。
        """
        with self._env._lock:
            events = list(self._env.event_log)
        current_count = len(events)
        if current_count <= self._last_event_count:
            return 0
        new_events = events[self._last_event_count :]
        self._last_event_count = current_count

        new_chapters = 0
        with self._lock:
            for ev in new_events:
                chapter = self._event_to_chapter(ev)
                if chapter is not None:
                    self._chapters.append(chapter)
                    new_chapters += 1
        return new_chapters

    def daily_summary(self) -> dict:
        """生成一份当前森林日报章节。"""
        with self._env._lock:
            food = round(self._env.food_available, 1)
            pop_total = len(self._env.population)
            deaths = len(self._env.death_log)
            births = len(self._env.birth_log)

        # 按物种统计
        status = self._env.population_status()
        by_species = status.get("by_species", {})

        # 拼接物种分布
        if by_species:
            species_line = "、".join(
                f"{sp} {cnt}" for sp, cnt in sorted(by_species.items())
            )
        else:
            species_line = "空无一物"

        content = (
            f"此刻森林中有 {pop_total} 只动物（{species_line}），"
            f"累计出生 {births} 次、死亡 {deaths} 次，"
            f"食物储备 {food} 单位。"
        )

        # 任务绩效
        if self._tasks is not None:
            ts = self._tasks.status()
            content += (
                f" 任务方面：待办 {ts.get('pending', 0)} 个，"
                f"进行中 {ts.get('running', 0)} 个，"
                f"已完成 {ts.get('completed', 0)} 个，"
                f"失败 {ts.get('failed', 0)} 个。"
            )

        chapter = self._make_chapter(
            category="daily_summary",
            title="森林日报",
            content=content,
        )
        with self._lock:
            self._chapters.append(chapter)
        return chapter

    # ------------------------------------------------------------------
    # 后台自动讲故事
    # ------------------------------------------------------------------

    def start_auto_storyteller(self, interval: float = 30.0) -> None:
        """启动后台故事线程，每 interval 秒拉一次新事件，每 60 次写一次日报。"""
        with self._lock:
            if self._auto_thread is not None and self._auto_thread.is_alive():
                return
            self._stop_event.clear()
            t = threading.Thread(
                target=self._auto_loop,
                args=(float(interval),),
                daemon=True,
                name="storyteller-auto",
            )
            self._auto_thread = t
            t.start()

    def stop_auto_storyteller(self) -> None:
        """停止后台故事线程。"""
        self._stop_event.set()
        t = self._auto_thread
        if t is not None and t.is_alive():
            t.join(timeout=2.0)
        with self._lock:
            self._auto_thread = None

    def _auto_loop(self, interval: float) -> None:
        """后台循环：拉新事件 + 每 60 次写一次日报。"""
        cycle = 0
        while not self._stop_event.is_set():
            try:
                self.poll_events()
                cycle += 1
                if cycle % 60 == 0:
                    self.daily_summary()
            except Exception:
                logger.exception("Exception in block")
                pass
            self._stop_event.wait(interval)

    # ------------------------------------------------------------------
    # 查询 / 渲染
    # ------------------------------------------------------------------

    def tell(self) -> list:
        """返回所有章节（按时间顺序）。"""
        with self._lock:
            return list(self._chapters)

    def tell_recent(self, n: int = 20) -> list:
        """返回最近 N 条章节。"""
        with self._lock:
            return list(self._chapters)[-n:] if n > 0 else []

    def tell_by_category(self, category: str, n: int = 50) -> list:
        """按分类过滤章节。"""
        with self._lock:
            matched = [c for c in self._chapters if c["category"] == category]
        return matched[-n:] if n > 0 else matched

    def render_markdown(self, n: int | None = None) -> str:
        """渲染为 markdown 文本。

        Args:
            n: 只渲染最近 N 条，None=全部。
        """
        chapters = self.tell_recent(n) if n is not None else self.tell()
        if not chapters:
            return "# 森林故事\n\n*森林还很安静，没有任何故事发生。*\n"
        lines = ["# 森林故事", ""]
        for c in chapters:
            t = _human_time(c["time"])
            lines.append(f"## {t} · {c['title']}")
            lines.append("")
            lines.append(c["content"])
            if c["actors"]:
                lines.append("")
                lines.append(f"*相关角色：{', '.join(c['actors'])}*")
            lines.append("")
        return "\n".join(lines)

    def render_recent_text(self, n: int = 20) -> str:
        """渲染为纯文本（最近 N 条），适合终端打印。"""
        chapters = self.tell_recent(n)
        if not chapters:
            return "=== 森林故事 ===\n  (暂无)\n"
        lines = ["=== 森林故事（最近 %d 条） ===" % len(chapters)]
        for c in chapters:
            t = _human_time(c["time"])
            lines.append(f"  [{t}] {c['title']}")
            lines.append(f"    {c['content']}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """整体状态。"""
        with self._lock:
            chapters = list(self._chapters)
        by_cat: dict[str, int] = {}
        for c in chapters:
            by_cat[c["category"]] = by_cat.get(c["category"], 0) + 1
        return {
            "total_chapters": len(chapters),
            "by_category": by_cat,
            "last_event_count": self._last_event_count,
            "auto_storyteller_running": (
                self._auto_thread is not None and self._auto_thread.is_alive()
            ),
        }
