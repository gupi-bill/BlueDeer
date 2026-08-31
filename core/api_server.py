"""BlueDeer RESTful API Server：外部系统集成接口。

提供任务提交、看板查询、调度管理、Webhook 管理等 REST API。
可在独立进程运行，也可挂载到 web_server 的 FastAPI 应用。
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query, Request

from core.config import get_config
from core.event_bus import EventBus
from core.harness import Harness
from core.scheduler import JobDef, Scheduler
from core.task import Task
from core.webhook import _ALL_EVENTS, WebhookDef, WebhookDispatcher

logger = logging.getLogger("bluedeer.api")

router = APIRouter(prefix="/api/v1", tags=["BlueDeer API"])

# ---- 限流配置 ----
_api_config = get_config().api
_RATE_LIMIT_REQUESTS = _api_config.rate_limit_requests
_RATE_LIMIT_WINDOW = _api_config.rate_limit_window
_MAX_TASK_TYPE_LEN = 50
_MAX_ASSIGNEE_LEN = 100
_MAX_DESCRIPTION_LEN = 2000
_MAX_JOB_ID_LEN = 100
_MAX_CRON_LEN = 100
_ALLOWED_TASK_TYPES = {
    "general",
    "code",
    "architecture",
    "batch",
    "voice",
    "image",
    "data",
}
_MAX_WEBHOOK_URL_LEN = 2048
_MAX_WEBHOOK_ID_LEN = 100
_MAX_SECRET_LEN = 256
_ALLOWED_URL_SCHEMES = {"http", "https"}


def _validate_webhook_url(url: str) -> None:
    if len(url) > _MAX_WEBHOOK_URL_LEN:
        raise HTTPException(400, f"URL 超过最大长度 {_MAX_WEBHOOK_URL_LEN}")
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_URL_SCHEMES:
        raise HTTPException(400, f"URL 协议必须是 {_ALLOWED_URL_SCHEMES}")
    hostname = parsed.hostname or ""
    if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        raise HTTPException(400, "Webhook URL 不能指向本地地址")
    if hostname.startswith(("10.", "192.168.", "172.")):
        raise HTTPException(400, "Webhook URL 不能指向内网地址")
    if hostname.endswith((".local", ".lan")):
        raise HTTPException(400, "Webhook URL 不能指向本地域名")


class RateLimiter:
    """滑动窗口限流器。"""

    def __init__(
        self,
        max_requests: int = _RATE_LIMIT_REQUESTS,
        window: float = _RATE_LIMIT_WINDOW,
    ) -> None:
        self._max = max_requests
        self._window = window
        self._buckets: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        now = time.time()
        cutoff = now - self._window
        with self._lock:
            if key not in self._buckets:
                self._buckets[key] = []
            self._buckets[key] = [ts for ts in self._buckets[key] if ts > cutoff]
            if len(self._buckets[key]) >= self._max:
                return False, len(self._buckets[key])
            self._buckets[key].append(now)
            return True, len(self._buckets[key])

    def cleanup(self) -> None:
        now = time.time()
        cutoff = now - self._window
        with self._lock:
            self._buckets = {
                k: [ts for ts in v if ts > cutoff] for k, v in self._buckets.items()
            }


_rate_limiter = RateLimiter()


# ---- 优雅关闭 ----

_shutdown_event = asyncio.Event()


def graceful_shutdown(drain_period: float = 30.0) -> None:
    """优雅关闭：设置关闭事件，等待 drain_period 秒让进行中请求完成。"""
    logger.warning("优雅关闭启动，drain 等待 %.1f 秒...", drain_period)
    _shutdown_event.set()
    import threading

    def _drain() -> None:
        deadline = time.time() + drain_period
        while time.time() < deadline:
            remaining = deadline - time.time()
            logger.info("drain 剩余 %.1f 秒", remaining)
            time.sleep(1)
        logger.warning("drain 完成，可安全退出")

    threading.Thread(target=_drain, daemon=True).start()


# 全局实例（由 init_api 注入）
_bus: EventBus | None = None
_harness: Harness | None = None
_scheduler: Scheduler | None = None
_webhook: WebhookDispatcher | None = None


def init_api(
    bus: EventBus,
    harness: Harness | None = None,
    scheduler: Scheduler | None = None,
    webhook: WebhookDispatcher | None = None,
) -> APIRouter:
    """初始化 API，注入依赖实例。"""
    global _bus, _harness, _scheduler, _webhook
    _bus = bus
    _harness = harness
    _scheduler = scheduler
    _webhook = webhook
    return router


# ===== 健康检查 =====


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    _allowed, _current = _rate_limiter.check(
        f"health:{request.client.host if request.client else 'unknown'}"
    )
    return {
        "status": "ok",
        "service": "BlueDeer API",
        "shutting_down": _shutdown_event.is_set(),
    }


# ===== 任务管理 =====


@router.post("/tasks")
async def create_task(
    task_type: str = Query(default="general"),
    assignee: str = Query(default=""),
    description: str = Query(default=""),
) -> dict[str, Any]:
    if _harness is None:
        raise HTTPException(503, "Harness 未初始化")
    if len(task_type) > _MAX_TASK_TYPE_LEN:
        raise HTTPException(400, f"task_type 超过最大长度 {_MAX_TASK_TYPE_LEN}")
    if len(assignee) > _MAX_ASSIGNEE_LEN:
        raise HTTPException(400, f"assignee 超过最大长度 {_MAX_ASSIGNEE_LEN}")
    if len(description) > _MAX_DESCRIPTION_LEN:
        raise HTTPException(400, f"description 超过最大长度 {_MAX_DESCRIPTION_LEN}")
    task = Task(type=task_type, payload={"description": description}, assignee=assignee)
    if _shutdown_event.is_set():
        raise HTTPException(503, "服务正在关闭，拒绝新任务")
    allowed, _ = _rate_limiter.check(f"create_task:{task_type}")
    if not allowed:
        raise HTTPException(429, "请求频率超限，请稍后重试")
    await _harness.submit_task(task)
    return {"task_id": task.id, "trace_id": task.trace_id, "status": "submitted"}


@router.get("/tasks")
async def list_tasks() -> dict[str, Any]:
    if _harness is None:
        raise HTTPException(503, "Harness 未初始化")
    stats = _harness.aggregate()
    return {
        "total": stats["total"],
        "success": stats["success"],
        "failed": stats["failed"],
        "pending": stats["pending"],
        "total_tokens": stats["total_tokens"],
        "tasks": stats["tasks"],
    }


@router.get("/tasks/{task_id}")
async def get_task(task_id: str) -> dict[str, Any]:
    if _harness is None:
        raise HTTPException(503, "Harness 未初始化")
    stats = _harness.aggregate()
    task = stats["tasks"].get(task_id)
    if task is None:
        raise HTTPException(404, f"任务 {task_id} 未找到")
    return {"task_id": task_id, **task}


# ===== 看板持久化 =====


@router.post("/board/save")
async def save_board(
    file: str = Query(default="data/task_state.json"),
) -> dict[str, Any]:
    if _harness is None:
        raise HTTPException(503, "Harness 未初始化")
    count = _harness.save_state(file)
    return {"saved": count, "path": file}


@router.post("/board/load")
async def load_board(
    file: str = Query(default="data/task_state.json"),
) -> dict[str, Any]:
    if _harness is None:
        raise HTTPException(503, "Harness 未初始化")
    count = _harness.load_state(file)
    return {"loaded": count, "path": file}


# ===== 定时调度 =====


@router.get("/schedules")
async def list_schedules() -> dict[str, Any]:
    if _scheduler is None:
        raise HTTPException(503, "Scheduler 未初始化")
    jobs = _scheduler.list_jobs()
    return {
        "total": len(jobs),
        "jobs": {
            jid: {
                "cron": j.cron,
                "task_type": j.task_type,
                "enabled": j.enabled,
                "description": j.description,
            }
            for jid, j in jobs.items()
        },
    }


@router.post("/schedules")
async def create_schedule(
    job_id: str = Query(...),
    cron: str = Query(...),
    task_type: str = Query(default="general"),
    assignee: str = Query(default=""),
    description: str = Query(default=""),
) -> dict[str, Any]:
    if len(job_id) > _MAX_JOB_ID_LEN:
        raise HTTPException(400, f"job_id 超过最大长度 {_MAX_JOB_ID_LEN}")
    if len(cron) > _MAX_CRON_LEN:
        raise HTTPException(400, f"cron 超过最大长度 {_MAX_CRON_LEN}")
    if _scheduler is None:
        raise HTTPException(503, "Scheduler 未初始化")
    job = JobDef(
        id=job_id,
        cron=cron,
        task_type=task_type,
        assignee=assignee,
        description=description,
    )
    _scheduler.add_job(job)
    return {"job_id": job_id, "status": "created"}


@router.delete("/schedules/{job_id}")
async def delete_schedule(job_id: str) -> dict[str, Any]:
    if _scheduler is None:
        raise HTTPException(503, "Scheduler 未初始化")
    ok = _scheduler.remove_job(job_id)
    if not ok:
        raise HTTPException(404, f"调度任务 {job_id} 未找到")
    return {"job_id": job_id, "status": "deleted"}


# ===== Webhook 管理 =====


@router.get("/webhooks")
async def list_webhooks() -> dict[str, Any]:
    if _webhook is None:
        raise HTTPException(503, "WebhookDispatcher 未初始化")
    hooks = _webhook.list_hooks()
    return {
        "total": len(hooks),
        "webhooks": {
            hid: {
                "url": h.url,
                "events": h.events,
                "enabled": h.enabled,
                "description": h.description,
            }
            for hid, h in hooks.items()
        },
    }


@router.post("/webhooks")
async def create_webhook(
    hook_id: str = Query(...),
    url: str = Query(...),
    events: str = Query(default=",".join(_ALL_EVENTS)),
    secret: str = Query(default=""),
    description: str = Query(default=""),
) -> dict[str, Any]:
    if _webhook is None:
        raise HTTPException(503, "WebhookDispatcher 未初始化")
    if len(hook_id) > _MAX_WEBHOOK_ID_LEN:
        raise HTTPException(400, f"hook_id 超过最大长度 {_MAX_WEBHOOK_ID_LEN}")
    if len(secret) > _MAX_SECRET_LEN:
        raise HTTPException(400, f"secret 超过最大长度 {_MAX_SECRET_LEN}")
    _validate_webhook_url(url)
    event_list = [e.strip() for e in events.split(",") if e.strip()]
    hook = WebhookDef(
        id=hook_id, url=url, events=event_list, secret=secret, description=description
    )
    _webhook.add_hook(hook)
    return {"hook_id": hook_id, "status": "created"}


@router.delete("/webhooks/{hook_id}")
async def delete_webhook(hook_id: str) -> dict[str, Any]:
    if _webhook is None:
        raise HTTPException(503, "WebhookDispatcher 未初始化")
    ok = _webhook.remove_hook(hook_id)
    if not ok:
        raise HTTPException(404, f"Webhook {hook_id} 未找到")
    return {"hook_id": hook_id, "status": "deleted"}


# ===== 报告 =====


@router.get("/report")
async def generate_report(fmt: str = Query(default="markdown")) -> dict[str, Any]:
    if _harness is None:
        raise HTTPException(503, "Harness 未初始化")
    from core.reporter import ReportGenerator

    stats = _harness.aggregate()
    task_board = stats.get("tasks", {})

    trace_lines: list[str] = []
    trace_file = "logs/trace.log"
    if os.path.exists(trace_file):
        with open(trace_file, "r", encoding="utf-8") as f:
            trace_lines = f.readlines()

    gen = ReportGenerator()
    path = gen.generate(
        task_board=task_board,
        aggregate_stats=stats,
        trace_lines=trace_lines,
        fmt=fmt,
    )
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return {
        "path": path,
        "format": fmt,
        "size": len(content),
        "content": content[:10000],
    }


# ===== DAG =====


@router.get("/dag")
async def list_dag() -> dict[str, Any]:
    from core.task_dag import TaskDAG

    dag = TaskDAG()
    nodes = dag.list_nodes()
    try:
        plan = dag.execution_plan()
    except ValueError:
        plan = []
    cycle = dag.detect_cycle()
    return {
        "nodes": [
            {"id": n.id, "depends_on": n.depends_on, "description": n.description}
            for n in nodes
        ],
        "topological_order": dag.topological_sort() if nodes else [],
        "execution_plan": plan,
        "has_cycle": cycle is not None,
        "total": len(nodes),
    }


@router.post("/dag/nodes")
async def add_dag_node(body: dict[str, Any]) -> dict[str, Any]:
    from core.task_dag import TaskDAG

    dag = TaskDAG()
    node_id = body.get("id", "")
    if not node_id:
        raise HTTPException(400, "请提供节点 id")
    dag.add_node(
        node_id,
        depends_on=body.get("depends_on", []),
        description=body.get("description", ""),
    )
    dag.save()
    return {"node_id": node_id, "status": "created"}


@router.delete("/dag/nodes/{node_id}")
async def delete_dag_node(node_id: str) -> dict[str, Any]:
    from core.task_dag import TaskDAG

    dag = TaskDAG()
    ok = dag.remove_node(node_id)
    if not ok:
        raise HTTPException(404, f"DAG 节点 {node_id} 未找到")
    dag.save()
    return {"node_id": node_id, "status": "deleted"}


@router.get("/dag/plan")
async def dag_execution_plan(
    completed: str = Query(default="", description="逗号分隔的已完成 task_id"),
) -> dict[str, Any]:
    from core.task_dag import TaskDAG

    dag = TaskDAG()
    completed_set = set(filter(None, completed.split(","))) if completed else set()
    try:
        plan = dag.execution_plan(completed_set)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"execution_plan": plan, "layers": len(plan)}


@router.get("/dag/subgraph/{root_id}")
async def dag_subgraph(root_id: str) -> dict[str, Any]:
    from core.task_dag import TaskDAG

    dag = TaskDAG()
    nodes = dag.subgraph(root_id)
    return {
        "root": root_id,
        "nodes": [{"id": n.id, "depends_on": n.depends_on} for n in nodes],
        "total": len(nodes),
    }
