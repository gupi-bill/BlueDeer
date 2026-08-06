"""BlueDeer 定时调度系统：cron 式定时任务触发。

用法：
    scheduler = Scheduler(event_bus, harness)
    scheduler.add_job("每小时清理", "0 * * * *", "cleanup", {"max_age": 3600})
    await scheduler.start()
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from core.event_bus import EventBus
from core.harness import Harness
from core.task import Task, TaskStatus

logger = logging.getLogger("bluedeer.scheduler")

__all__ = ["JobDef", "Scheduler", "TimingWheel"]

_JOB_FILE = "data/scheduler_jobs.json"


@dataclass(slots=True)
class JobDef:
    """定时任务定义。

    cron 表达式格式：秒 分 时 日 月 周（标准 6 段 cron）。
    每段支持: 数字 / * / , / - / step(/)。
    interval_seconds 可选：设为 >0 时按固定间隔运行（替代 cron）。
    """

    id: str
    cron: str = ""
    interval_seconds: int = 0
    task_type: str = "general"
    task_payload: dict[str, Any] = field(default_factory=dict)
    assignee: str = ""
    enabled: bool = True
    description: str = ""


class TimingWheel:
    """时间轮：高效管理大量定时任务的到期触发。

    将时间划分为固定大小的槽（wheel slots），每个槽对应一个时间窗口。
    任务根据其 next_run_ts 被散列到对应槽中，时间轮以固定 tick 间隔前进。
    """

    def __init__(self, tick_interval: float = 1.0, num_slots: int = 86400) -> None:
        self._tick_interval = tick_interval
        self._num_slots = num_slots
        self._slots: list[list[tuple[str, float]]] = [[] for _ in range(num_slots)]
        self._cursor = 0
        self._epoch = time.time()

    def _slot_for(self, ts: float) -> int:
        if ts == float("inf"):
            return self._num_slots - 1
        return int((ts - self._epoch) // self._tick_interval) % self._num_slots

    def insert(self, job_id: str, next_ts: float) -> None:
        self._slots[self._slot_for(next_ts)].append((job_id, next_ts))

    def remove(self, job_id: str, next_ts: float) -> None:
        slot = self._slots[self._slot_for(next_ts)]
        slot[:] = [(jid, ts) for jid, ts in slot if jid != job_id]

    def advance(self) -> list[tuple[str, float]]:
        due = self._slots[self._cursor]
        self._slots[self._cursor] = []
        self._cursor = (self._cursor + 1) % self._num_slots
        return due

    def next_tick_in(self) -> float:
        slot_start = self._epoch + self._cursor * self._tick_interval
        elapsed = time.time() - slot_start
        return max(0.0, self._tick_interval - elapsed)

    def has_due(self) -> bool:
        return bool(self._slots[self._cursor])


class Scheduler:
    """定时调度器。

    在后台事件循环中每分钟 tick 一次，检查哪些 JobDef 到期，
    通过 EventBus 发布 ScheduledEvent 或通过 Harness 提交 Task。
    """

    def __init__(
        self,
        event_bus: EventBus,
        harness: Harness | None = None,
    ) -> None:
        self._bus = event_bus
        self._harness = harness
        self._jobs: dict[str, JobDef] = {}
        self._timing_wheel = TimingWheel()
        self._next_run: dict[str, float] = {}
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._dag: Any = None
        self._load_jobs()
        for job in self._jobs.values():
            self._reschedule(job, time.time())

    def set_dag(self, dag: Any) -> None:
        """绑定 DAG 依赖图。"""
        self._dag = dag

    # ---- 作业管理 ----

    def add_job(self, job: JobDef) -> str:
        """添加一个定时任务。

        Returns:
            任务 ID。
        """
        self._jobs[job.id] = job
        self._reschedule(job, time.time())
        self._save_jobs()
        logger.info("scheduler job added: %s [%s]", job.id, job.cron)
        return job.id

    def remove_job(self, job_id: str) -> bool:
        """删除定时任务。"""
        if job_id in self._jobs:
            del self._jobs[job_id]
            self._drop(job_id)
            self._save_jobs()
            logger.info("scheduler job removed: %s", job_id)
            return True
        return False

    def get_job(self, job_id: str) -> JobDef | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> dict[str, JobDef]:
        return dict(self._jobs)

    def enable_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.enabled = True
        self._reschedule(job, time.time())
        self._save_jobs()
        return True

    def disable_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.enabled = False
        self._defer(job_id)
        self._save_jobs()
        return True

    # ---- 启停控制 ----

    async def start(self) -> None:
        """启动调度器后台循环。"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("调度器已启动 (%d 个定时任务)", len(self._jobs))

    async def stop(self) -> None:
        """停止调度器。"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("调度器已停止")

    # ---- 内部循环 ----

    async def _run_loop(self) -> None:
        while self._running:
            due = self._timing_wheel.advance()
            now_ts = time.time()
            for job_id, due_ts in due:
                job = self._jobs.get(job_id)
                if job is None or not job.enabled:
                    continue
                if due_ts > now_ts:
                    self._timing_wheel.insert(job_id, due_ts)
                    continue
                now = time.localtime()
                if job.interval_seconds > 0:
                    logger.info("触发间隔任务: %s (每 %ds)", job.id, job.interval_seconds)
                    await self._safe_fire(job)
                    self._reschedule(job, now_ts)
                elif job.cron and self._match_cron(job.cron, now):
                    logger.info("触发定时任务: %s [%s]", job.id, job.cron)
                    await self._safe_fire(job)
                    self._reschedule(job, now_ts)
                else:
                    self._reschedule(job, now_ts)
            if not self._timing_wheel.has_due():
                await asyncio.sleep(self._timing_wheel.next_tick_in())

    async def _safe_fire(self, job: JobDef) -> None:
        """触发任务并隔离异常：单个 job 失败不让调度循环死掉。"""
        try:
            await self._fire(job)
        except Exception as e:
            logger.error("调度任务 %s 触发失败（已隔离，继续运行）: %s", job.id, e)

    # ---- Treap 优先队列（key=(next_run_ts, job_id)，value=job_id）----

    @staticmethod
    def _next_cron_checkpoint(now_ts: float) -> float:
        """cron 任务下一检查点：对齐到下一分钟整点。"""
        return (int(now_ts // 60) + 1) * 60

    def _reschedule(self, job: JobDef, now_ts: float) -> None:
        """按任务类型计算 next_run 并插入/更新时间轮。"""
        if not job.enabled:
            self._defer(job.id)
            return
        if job.interval_seconds > 0:
            next_ts = now_ts + job.interval_seconds
        else:
            next_ts = self._next_cron_checkpoint(now_ts)
        old = self._next_run.get(job.id)
        if old is not None:
            self._timing_wheel.remove(job.id, old)
        self._timing_wheel.insert(job.id, next_ts)
        self._next_run[job.id] = next_ts

    def _defer(self, job_id: str) -> None:
        """停用任务：推入无限远。"""
        old = self._next_run.pop(job_id, None)
        if old is not None:
            self._timing_wheel.remove(job_id, old)
        self._timing_wheel.insert(job_id, float("inf"))
        self._next_run[job_id] = float("inf")

    def _drop(self, job_id: str) -> None:
        """彻底移出时间轮。"""
        old = self._next_run.pop(job_id, None)
        if old is not None:
            self._timing_wheel.remove(job_id, old)

    async def _fire(self, job: JobDef) -> None:
        task = Task(
            type=job.task_type,
            payload=job.task_payload,
            assignee=job.assignee,
        )
        # DAG 依赖检查：前置未完成则跳过本轮
        if self._dag is not None and self._dag.has_node(job.id):
            completed = (
                {
                    tid
                    for tid, r in self._harness._task_board.items()
                    if r.status == TaskStatus.SUCCESS
                }
                if self._harness
                else set()
            )
            if not self._dag.ready(job.id, completed):
                logger.info("调度任务 %s 前置依赖未就绪，跳过本轮", job.id)
                return
        if self._harness:
            await self._harness.submit_task(task)
        else:
            await self._bus.publish(f"scheduler.{job.id}", task)

    # ---- cron 匹配 ----

    def _match_cron(self, expr: str, t: time.struct_time) -> bool:
        parts = expr.strip().split()
        if len(parts) != 6:
            logger.warning("cron 表达式格式错误（需要 6 段）: %s", expr)
            return False
        now_vals = [
            t.tm_sec,
            t.tm_min,
            t.tm_hour,
            t.tm_mday,
            t.tm_mon,
            t.tm_wday,
        ]
        for i, (field, val) in enumerate(zip(parts, now_vals)):
            if not self._match_field(field, val):
                return False
        return True

    @staticmethod
    def _match_field(field: str, val: int) -> bool:
        if field == "*":
            return True
        for part in field.split(","):
            if "/" in part:
                base, step = part.split("/", 1)
                step_n = int(step)
                if base == "*":
                    base_start = 0
                    base_end = None
                elif "-" in base:
                    base_start = int(base.split("-")[0])
                    base_end = int(base.split("-")[1])
                else:
                    base_start = int(base)
                    base_end = base_start
                if val < base_start:
                    continue
                if base_end is not None and val > base_end:
                    continue
                if (val - base_start) % step_n == 0:
                    return True
            elif "-" in part:
                lo, hi = part.split("-", 1)
                if int(lo) <= val <= int(hi):
                    return True
            else:
                if int(part) == val:
                    return True
        return False

    # ---- 持久化 ----

    def _load_jobs(self) -> None:
        try:
            from core.database import Database

            rows = Database().load_scheduler_jobs()
            for item in rows:
                job = JobDef(**item)
                self._jobs[job.id] = job
        except Exception as e:
            logger.warning("从数据库加载调度任务失败: %s", e)
        if not self._jobs:
            try:
                self._load_jobs_json()
            except Exception as e:
                logger.warning("从 JSON 文件加载调度任务失败: %s", e)

    def _save_jobs(self) -> None:
        try:
            raw = {jid: asdict(j) for jid, j in self._jobs.items()}
            from core.database import Database

            Database().save_scheduler_jobs(raw)
        except Exception as e:
            logger.warning("保存调度任务到数据库失败: %s", e)
        try:
            self._save_jobs_json()
        except Exception as e:
            logger.warning("保存调度任务到 JSON 文件失败: %s", e)

    # ---- JSON 文件持久化（数据库回退方案 + 可移植） ----

    def _load_jobs_json(self) -> None:
        if not os.path.exists(_JOB_FILE):
            return
        with open(_JOB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            job = JobDef(**item)
            if job.id not in self._jobs:
                self._jobs[job.id] = job

    def _save_jobs_json(self) -> None:
        os.makedirs(os.path.dirname(_JOB_FILE) or ".", exist_ok=True)
        raw = [asdict(j) for j in self._jobs.values()]
        with open(_JOB_FILE, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
