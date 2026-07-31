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
from dataclasses import dataclass, field, asdict
from typing import Any

from core.event_bus import EventBus
from core.harness import Harness
from core.task import Task, TaskStatus

logger = logging.getLogger("bluedeer.scheduler")

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
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._dag: Any = None
        self._load_jobs()

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
        self._save_jobs()
        logger.info("调度任务已添加: %s [%s]", job.id, job.cron)
        return job.id

    def remove_job(self, job_id: str) -> bool:
        """删除定时任务。"""
        if job_id in self._jobs:
            del self._jobs[job_id]
            self._save_jobs()
            logger.info("调度任务已删除: %s", job_id)
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
        self._save_jobs()
        return True

    def disable_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.enabled = False
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
        last_interval: dict[str, float] = {}
        while self._running:
            now = time.localtime()
            now_ts = time.time()
            for job in list(self._jobs.values()):
                if not job.enabled:
                    continue
                if job.interval_seconds > 0:
                    last = last_interval.get(job.id, 0.0)
                    if now_ts - last >= job.interval_seconds:
                        last_interval[job.id] = now_ts
                        logger.info("触发间隔任务: %s (每 %ds)", job.id, job.interval_seconds)
                        await self._fire(job)
                elif job.cron and self._match_cron(job.cron, now):
                    logger.info("触发定时任务: %s [%s]", job.id, job.cron)
                    await self._fire(job)
            await asyncio.sleep(60)

    async def _fire(self, job: JobDef) -> None:
        task = Task(
            type=job.task_type,
            payload=job.task_payload,
            assignee=job.assignee,
        )
        # DAG 依赖检查：前置未完成则跳过本轮
        if self._dag is not None and self._dag.has_node(job.id):
            completed = {
                tid for tid, r in self._harness._task_board.items()
                if r.status == TaskStatus.SUCCESS
            } if self._harness else set()
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
            t.tm_sec, t.tm_min, t.tm_hour, t.tm_mday,
            t.tm_mon, t.tm_wday,
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
                elif "-" in base:
                    base_start = int(base.split("-")[0])
                else:
                    base_start = int(base)
                if (val - base_start) % step_n == 0 and val >= base_start:
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
