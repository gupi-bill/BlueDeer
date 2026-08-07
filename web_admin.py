"""BlueDeer Web 管理面板：FastAPI + Jinja2 + HTMX。

依赖注入方式同 core/api_server.py。
"""

from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import jinja2
from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse

from core.event_bus import EventBus
from core.harness import Harness
from core.scheduler import JobDef, Scheduler
from core.task import Task
from core.task_templates import TaskTemplates
from core.webhook import _ALL_EVENTS, WebhookDef, WebhookDispatcher
# ruff: noqa: S110, S112

logger = logging.getLogger("bluedeer.admin")


# ====== Widget 系统 ======


class Widget(ABC):
    name: str
    title: str
    width: int = 1
    height: int = 1

    def __init__(self, name: str, title: str = "") -> None:
        self.name = name
        self.title = title or name

    @abstractmethod
    def render(self) -> str: ...

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "width": self.width,
            "height": self.height,
        }


@dataclass
class WidgetRegistry:
    _widgets: dict[str, Widget] = field(default_factory=dict)

    def add(self, name: str, component: Widget) -> None:
        self._widgets[name] = component

    def remove(self, name: str) -> bool:
        return self._widgets.pop(name, None) is not None

    def get(self, name: str) -> Widget | None:
        return self._widgets.get(name)

    def list_all(self) -> list[Widget]:
        return list(self._widgets.values())

    def render_all(self) -> str:
        parts = []
        for w in self._widgets.values():
            rendered = w.render()
            parts.append(
                f'<div class="widget widget-{w.width}" data-widget="{w.name}">'
            )
            parts.append(f'<div class="widget-title">{w.title}</div>')
            parts.append(f'<div class="widget-body">{rendered}</div>')
            parts.append("</div>")
        return "\n".join(parts)


_widget_registry = WidgetRegistry()


def add_widget(name: str, component: Widget) -> None:
    _widget_registry.add(name, component)


def get_stats(metric: str, period: str = "24h") -> dict[str, Any]:
    now = time.time()
    period_sec = {"1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800}.get(
        period, 86400
    )
    cutoff = now - period_sec
    base: dict[str, Any] = {
        "metric": metric,
        "period": period,
        "period_sec": period_sec,
        "cutoff": cutoff,
        "value": 0,
    }
    if _harness is None:
        return base
    try:
        agg = _harness.aggregate()
        tasks = agg.get("tasks", {})
        if metric == "total":
            base["value"] = tasks.get("total", 0)
        elif metric == "success":
            base["value"] = tasks.get("success", 0)
        elif metric == "failed":
            base["value"] = tasks.get("failed", 0)
        elif metric == "pending":
            base["value"] = tasks.get("pending", 0)
        elif metric == "success_rate":
            t = tasks.get("total", 1) or 1
            base["value"] = round(tasks.get("success", 0) / t * 100, 1)
        elif metric == "schedule_count":
            base["value"] = len(_scheduler.list_jobs()) if _scheduler else 0
        elif metric == "webhook_count":
            base["value"] = len(_webhook.list_hooks()) if _webhook else 0
    except Exception:
        pass
    return base


class TextWidget(Widget):
    def __init__(self, name: str, text: str = "", title: str = "") -> None:
        super().__init__(name, title)
        self._text = text

    def render(self) -> str:
        return f"<p>{self._text}</p>"


class StatsWidget(Widget):
    def __init__(
        self, name: str, metric: str, title: str = "", period: str = "24h"
    ) -> None:
        super().__init__(name, title)
        self.metric = metric
        self.period = period

    def render(self) -> str:
        stats = get_stats(self.metric, self.period)
        val = stats.get("value", 0)
        return f'<div class="stat-value">{val}</div><div class="stat-label">{self.metric}</div>'


class ChartWidget(Widget):
    def __init__(
        self, name: str, metrics: list[str], title: str = "", period: str = "24h"
    ) -> None:
        super().__init__(name, title)
        self.metrics = metrics
        self.period = period
        self.width = 2

    def render(self) -> str:
        data = {m: get_stats(m, self.period) for m in self.metrics}
        return f'<pre class="chart-data">{data}</pre>'


router = APIRouter(prefix="/admin", tags=["管理面板"])

# 全局实例（由 init_admin 注入）
_bus: EventBus | None = None
_harness: Harness | None = None
_scheduler: Scheduler | None = None
_webhook: WebhookDispatcher | None = None
_templates_engine: TaskTemplates | None = None

_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader("templates"),
    autoescape=True,
)


def _render(name: str, **kwargs: Any) -> str:
    tmpl = _jinja_env.get_template(name)
    return tmpl.render(**kwargs)


def _timestamp_to_str(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


_jinja_env.filters["timestamp_to_str"] = _timestamp_to_str


def init_admin(
    bus: EventBus,
    harness: Harness | None = None,
    scheduler: Scheduler | None = None,
    webhook: WebhookDispatcher | None = None,
    templates_engine: TaskTemplates | None = None,
) -> APIRouter:
    global _bus, _harness, _scheduler, _webhook, _templates_engine
    _bus = bus
    _harness = harness
    _scheduler = scheduler
    _webhook = webhook
    _templates_engine = templates_engine
    return router


# ====== 仪表盘 ======


@router.get("", response_class=HTMLResponse)
async def dashboard(request: Request) -> str:
    stats = {"total": 0, "success": 0, "failed": 0, "pending": 0}
    schedule_count = 0
    webhook_count = 0
    resources: dict[str, Any] = {}
    health: list[dict[str, Any]] = []

    if _harness:
        s = _harness.aggregate()
        stats = {
            "total": s["total"],
            "success": s["success"],
            "failed": s["failed"],
            "pending": s["pending"],
        }

    dag_nodes = 0
    dag_layers = 0
    dag_cycle = False
    try:
        from core.task_dag import TaskDAG

        d = TaskDAG()
        dag_nodes = len(d.list_nodes())
        dag_cycle = d.detect_cycle() is not None
        try:
            dag_layers = len(d.execution_plan())
        except ValueError:
            dag_layers = 0
    except Exception:
        pass

    if _scheduler:
        schedule_count = len(_scheduler.list_jobs())

    if _webhook:
        webhook_count = len(_webhook.list_hooks())

    try:
        from core.monitor import SystemMonitor

        mon = SystemMonitor()
        resources = mon.resource_usage()
        health = [
            {
                "service": h.service,
                "status": h.status,
                "latency_ms": round(h.latency_ms, 1),
            }
            for h in mon.check_services()
        ]
    except Exception:
        pass

    return HTMLResponse(
        content=_render(
            "admin/dashboard.html",
            active="dashboard",
            stats=stats,
            schedule_count=schedule_count,
            webhook_count=webhook_count,
            resources=resources,
            health=health,
            dag_nodes=dag_nodes,
            dag_layers=dag_layers,
            dag_cycle=dag_cycle,
        )
    )


@router.get("/widgets", response_class=HTMLResponse)
async def widgets_page(request: Request) -> str:
    widgets = _widget_registry.list_all()
    rendered = _widget_registry.render_all()
    return HTMLResponse(
        content=_render(
            "admin/widgets.html", active="widgets", widgets=widgets, rendered=rendered
        )
    )


@router.post("/widgets/add")
async def widgets_add(
    name: str = Form(...),
    widget_type: str = Form("text"),
    title: str = Form(""),
    metric: str = Form(""),
    text: str = Form(""),
) -> str:
    if widget_type == "stats":
        w = StatsWidget(name=name, metric=metric or "total", title=title or name)
    elif widget_type == "text":
        w = TextWidget(name=name, text=text, title=title or name)
    else:
        return '<div class="toast toast-error">未知 widget 类型</div>'
    add_widget(name, w)
    return '<div class="toast toast-success">✅ Widget 已添加</div>'


@router.delete("/widgets/{name}")
async def widgets_delete(name: str) -> str:
    _widget_registry.remove(name)
    return ""


@router.get("/api/stats/{metric}")
async def stats_api(metric: str, period: str = Query("24h")) -> dict[str, Any]:
    return get_stats(metric, period)


# ====== 任务看板 ======


@router.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request) -> str:
    tasks: dict[str, Any] = {}
    if _harness:
        tasks = _harness.aggregate().get("tasks", {})
    return HTMLResponse(
        content=_render(
            "admin/tasks.html",
            active="tasks",
            tasks=tasks,
        )
    )


@router.get("/tasks/create-form", response_class=HTMLResponse)
async def tasks_create_form(request: Request) -> str:
    return """<div class="card" style="border-color:var(--accent);">
  <h3 style="margin-bottom:12px;">新建任务</h3>
  <form hx-post="/admin/tasks" hx-target="#create-form" hx-swap="innerHTML" hx-on::after-request="if(event.detail.successful) setTimeout(()=>htmx.trigger('#create-form','htmx:load'),500)">
    <div class="form-row">
      <div class="form-group">
        <label>任务类型</label>
        <input type="text" name="task_type" value="general" placeholder="如 code-review">
      </div>
      <div class="form-group">
        <label>执行人</label>
        <input type="text" name="assignee" placeholder="如 squirrel">
      </div>
    </div>
    <div class="form-group">
      <label>描述</label>
      <textarea name="description" rows="2" placeholder="任务描述"></textarea>
    </div>
    <div class="flex gap">
      <button type="submit" class="btn btn-primary">创建</button>
      <button type="button" class="btn" onclick="this.closest('.card').remove()">取消</button>
    </div>
  </form>
</div>"""


@router.post("/tasks", response_class=HTMLResponse)
async def tasks_create(
    request: Request,
    task_type: str = Form("general"),
    assignee: str = Form(""),
    description: str = Form(""),
) -> str:
    if _harness is None:
        return '<div class="toast toast-error">Harness 未初始化</div>'
    task = Task(type=task_type, payload={"description": description}, assignee=assignee)
    await _harness.submit_task(task)
    return f'<div class="toast toast-success">✅ 任务已创建: {task.id[:16]}…</div>'


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
async def tasks_detail(request: Request, task_id: str) -> str:
    if _harness is None:
        return '<p class="text-muted">不可用</p>'
    stats = _harness.aggregate()
    task = stats["tasks"].get(task_id)
    if task is None:
        return '<p class="text-muted">任务未找到</p>'

    dag_info = ""
    try:
        from core.task_dag import TaskDAG

        d = TaskDAG()
        if d.has_node(task_id):
            deps = d.depends_on(task_id)
            deps_str = ", ".join(deps) if deps else "无"
            deps_down = d.dependents(task_id)
            down_str = ", ".join(deps_down) if deps_down else "无"
            dag_info = f"""<tr><td style="color:var(--text-secondary);">前置依赖</td><td>{deps_str}</td></tr>
    <tr><td style="color:var(--text-secondary);">下游任务</td><td>{down_str}</td></tr>"""
    except Exception:
        pass

    return f"""<div class="card">
  <div class="flex-between">
    <h3>任务详情</h3>
    <button class="btn btn-sm" onclick="this.closest('.card').remove()">✕ 关闭</button>
  </div>
  <table>
    <tr><td style="width:100px;color:var(--text-secondary);">ID</td><td style="font-family:monospace;">{task_id}</td></tr>
    <tr><td style="color:var(--text-secondary);">类型</td><td>{task.get("type","—")}</td></tr>
    <tr><td style="color:var(--text-secondary);">执行人</td><td>{task.get("assignee","—")}</td></tr>
    <tr><td style="color:var(--text-secondary);">状态</td><td>{task.get("status","—")}</td></tr>
    <tr><td style="color:var(--text-secondary);">Token</td><td>{task.get("tokens",0)}</td></tr>
    <tr><td style="color:var(--text-secondary);">错误</td><td style="color:var(--error);">{task.get("error","") or "—"}</td></tr>
    {dag_info}
  </table>
</div>"""


# ====== 定时调度 ======


@router.get("/schedules", response_class=HTMLResponse)
async def schedules_page(request: Request) -> str:
    jobs: dict[str, Any] = {}
    if _scheduler:
        jobs = {
            jid: {
                "cron": j.cron,
                "task_type": j.task_type,
                "enabled": j.enabled,
                "description": j.description,
            }
            for jid, j in _scheduler.list_jobs().items()
        }
    return HTMLResponse(
        content=_render(
            "admin/schedules.html",
            active="schedules",
            jobs=jobs,
        )
    )


@router.get("/schedules/create-form", response_class=HTMLResponse)
async def schedules_create_form(request: Request) -> str:
    return """<div class="card" style="border-color:var(--accent);">
  <h3 style="margin-bottom:12px;">新建定时任务</h3>
  <form hx-post="/admin/schedules" hx-target="#create-form" hx-swap="innerHTML">
    <div class="form-row">
      <div class="form-group">
        <label>任务 ID</label>
        <input type="text" name="job_id" required placeholder="如 hourly-cleanup">
      </div>
      <div class="form-group">
        <label>Cron 表达式</label>
        <input type="text" name="cron" required placeholder="0 * * * *">
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>任务类型</label>
        <input type="text" name="task_type" value="general">
      </div>
      <div class="form-group">
        <label>执行人</label>
        <input type="text" name="assignee" placeholder="如 squirrel">
      </div>
    </div>
    <div class="form-group">
      <label>描述</label>
      <input type="text" name="description" placeholder="定时任务描述">
    </div>
    <div class="flex gap">
      <button type="submit" class="btn btn-primary">创建</button>
      <button type="button" class="btn" onclick="this.closest('.card').remove()">取消</button>
    </div>
  </form>
</div>"""


@router.post("/schedules", response_class=HTMLResponse)
async def schedules_create(
    request: Request,
    job_id: str = Form(...),
    cron: str = Form(...),
    task_type: str = Form("general"),
    assignee: str = Form(""),
    description: str = Form(""),
) -> str:
    if _scheduler is None:
        return '<div class="toast toast-error">Scheduler 未初始化</div>'
    job = JobDef(
        id=job_id,
        cron=cron,
        task_type=task_type,
        assignee=assignee,
        description=description,
    )
    _scheduler.add_job(job)
    return '<div class="toast toast-success">✅ 定时任务已创建</div>'


@router.post("/schedules/{job_id}/enable", response_class=HTMLResponse)
async def schedules_enable(request: Request, job_id: str) -> str:
    if _scheduler is None:
        return '<tr><td colspan="6" class="text-muted">不可用</td></tr>'
    _scheduler.enable_job(job_id)
    j = _scheduler.get_job(job_id)
    if j is None:
        return '<tr><td colspan="6" class="text-muted">已删除</td></tr>'
    return _schedule_row(job_id, j)


@router.post("/schedules/{job_id}/disable", response_class=HTMLResponse)
async def schedules_disable(request: Request, job_id: str) -> str:
    if _scheduler is None:
        return '<tr><td colspan="6" class="text-muted">不可用</td></tr>'
    _scheduler.disable_job(job_id)
    j = _scheduler.get_job(job_id)
    if j is None:
        return '<tr><td colspan="6" class="text-muted">已删除</td></tr>'
    return _schedule_row(job_id, j)


@router.delete("/schedules/{job_id}", response_class=HTMLResponse)
async def schedules_delete(request: Request, job_id: str) -> str:
    if _scheduler:
        _scheduler.remove_job(job_id)
    return ""


def _schedule_row(job_id: str, j: JobDef) -> str:
    enabled = j.enabled
    badge = (
        '<span class="badge badge-green">启用</span>'
        if enabled
        else '<span class="badge badge-gray">禁用</span>'
    )
    toggle_btn = (
        f'<button class="btn btn-sm btn-warn" hx-post="/admin/schedules/{job_id}/disable" hx-target="closest tr" hx-swap="outerHTML">禁用</button>'
        if enabled
        else f'<button class="btn btn-sm" hx-post="/admin/schedules/{job_id}/enable" hx-target="closest tr" hx-swap="outerHTML">启用</button>'
    )
    return f"""<tr>
  <td style="font-family:monospace;font-size:11px;">{job_id}</td>
  <td><code style="background:var(--bg-primary);padding:2px 6px;border-radius:3px;">{j.cron}</code></td>
  <td>{j.task_type}</td>
  <td class="text-muted">{j.description or '—'}</td>
  <td>{badge}</td>
  <td>{toggle_btn}<button class="btn btn-sm btn-danger" hx-delete="/admin/schedules/{job_id}" hx-target="closest tr" hx-swap="outerHTML" hx-confirm="确定删除？">删除</button></td>
</tr>"""


# ====== Webhook 管理 ======


@router.get("/webhooks", response_class=HTMLResponse)
async def webhooks_page(request: Request) -> str:
    hooks: dict[str, Any] = {}
    if _webhook:
        hooks = {
            hid: {
                "url": h.url,
                "events": h.events,
                "enabled": h.enabled,
                "description": h.description,
            }
            for hid, h in _webhook.list_hooks().items()
        }
    return HTMLResponse(
        content=_render(
            "admin/webhooks.html",
            active="webhooks",
            webhooks=hooks,
        )
    )


@router.get("/webhooks/create-form", response_class=HTMLResponse)
async def webhooks_create_form(request: Request) -> str:
    return """<div class="card" style="border-color:var(--accent);">
  <h3 style="margin-bottom:12px;">新建 Webhook</h3>
  <form hx-post="/admin/webhooks" hx-target="#create-form" hx-swap="innerHTML">
    <div class="form-row">
      <div class="form-group">
        <label>Hook ID</label>
        <input type="text" name="hook_id" required placeholder="如 github-ci">
      </div>
      <div class="form-group">
        <label>URL</label>
        <input type="url" name="url" required placeholder="https://hooks.example.com/event">
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>事件类型（逗号分隔）</label>
        <input type="text" name="events" value="task.completed,task.failed,task.started,task.allocated">
      </div>
      <div class="form-group">
        <label>密钥（可选）</label>
        <input type="text" name="secret" placeholder="HMAC 密钥">
      </div>
    </div>
    <div class="form-group">
      <label>描述</label>
      <input type="text" name="description" placeholder="Webhook 用途说明">
    </div>
    <div class="flex gap">
      <button type="submit" class="btn btn-primary">创建</button>
      <button type="button" class="btn" onclick="this.closest('.card').remove()">取消</button>
    </div>
  </form>
</div>"""


@router.post("/webhooks", response_class=HTMLResponse)
async def webhooks_create(
    request: Request,
    hook_id: str = Form(...),
    url: str = Form(...),
    events: str = Form(",".join(_ALL_EVENTS)),
    secret: str = Form(""),
    description: str = Form(""),
) -> str:
    if _webhook is None:
        return '<div class="toast toast-error">WebhookDispatcher 未初始化</div>'
    event_list = [e.strip() for e in events.split(",") if e.strip()]
    hook = WebhookDef(
        id=hook_id, url=url, events=event_list, secret=secret, description=description
    )
    _webhook.add_hook(hook)
    return '<div class="toast toast-success">✅ Webhook 已创建</div>'


@router.post("/webhooks/{hook_id}/enable", response_class=HTMLResponse)
async def webhooks_enable(request: Request, hook_id: str) -> str:
    if _webhook is None:
        return '<tr><td colspan="6" class="text-muted">不可用</td></tr>'
    _webhook.enable_hook(hook_id)
    h = _webhook.get_hook(hook_id)
    if h is None:
        return '<tr><td colspan="6" class="text-muted">已删除</td></tr>'
    return _webhook_row(hook_id, h)


@router.post("/webhooks/{hook_id}/disable", response_class=HTMLResponse)
async def webhooks_disable(request: Request, hook_id: str) -> str:
    if _webhook is None:
        return '<tr><td colspan="6" class="text-muted">不可用</td></tr>'
    _webhook.disable_hook(hook_id)
    h = _webhook.get_hook(hook_id)
    if h is None:
        return '<tr><td colspan="6" class="text-muted">已删除</td></tr>'
    return _webhook_row(hook_id, h)


@router.delete("/webhooks/{hook_id}", response_class=HTMLResponse)
async def webhooks_delete(request: Request, hook_id: str) -> str:
    if _webhook:
        _webhook.remove_hook(hook_id)
    return ""


def _webhook_row(hook_id: str, h: WebhookDef) -> str:
    enabled = h.enabled
    badge = (
        '<span class="badge badge-green">启用</span>'
        if enabled
        else '<span class="badge badge-gray">禁用</span>'
    )
    toggle_btn = (
        f'<button class="btn btn-sm btn-warn" hx-post="/admin/webhooks/{hook_id}/disable" hx-target="closest tr" hx-swap="outerHTML">禁用</button>'
        if enabled
        else f'<button class="btn btn-sm" hx-post="/admin/webhooks/{hook_id}/enable" hx-target="closest tr" hx-swap="outerHTML">启用</button>'
    )
    events_html = " ".join(
        f'<span class="badge badge-blue">{ev}</span>' for ev in h.events
    )
    return f"""<tr>
  <td style="font-family:monospace;font-size:11px;">{hook_id}</td>
  <td style="max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{h.url}</td>
  <td>{events_html}</td>
  <td class="text-muted">{h.description or '—'}</td>
  <td>{badge}</td>
  <td>{toggle_btn}<button class="btn btn-sm btn-danger" hx-delete="/admin/webhooks/{hook_id}" hx-target="closest tr" hx-swap="outerHTML" hx-confirm="确定删除？">删除</button></td>
</tr>"""


# ====== 任务模板 ======


@router.get("/templates", response_class=HTMLResponse)
async def templates_page(request: Request) -> str:
    tmpls: list[dict[str, Any]] = []
    if _templates_engine:
        tmpls = [
            {
                "id": t.id,
                "type": t.type,
                "assignee": t.assignee,
                "tags": t.tags,
                "description": t.description,
            }
            for t in _templates_engine.list_templates()
        ]
    return HTMLResponse(
        content=_render(
            "admin/templates_page.html",
            active="templates",
            templates=tmpls,
        )
    )


# ====== DAG 依赖图 ======


@router.get("/dag", response_class=HTMLResponse)
async def dag_page(request: Request) -> str:
    from core.task_dag import TaskDAG

    dag = TaskDAG()
    nodes = dag.list_nodes()
    try:
        plan = dag.execution_plan()
    except ValueError:
        plan = []
    cycle = dag.detect_cycle()
    mermaid_lines = ["graph TD"]
    for n in nodes:
        if not n.depends_on:
            mermaid_lines.append(f'  {n.id}["{n.id}"]')
        for dep in n.depends_on:
            mermaid_lines.append(f"  {dep} --> {n.id}")
    mermaid_code = "\n".join(mermaid_lines) if nodes else "graph TD\n  empty[暂无节点]"
    return HTMLResponse(
        content=_render(
            "admin/dag.html",
            active="dag",
            nodes=nodes,
            plan=plan,
            has_cycle=cycle is not None,
            mermaid_code=mermaid_code,
        )
    )


@router.post("/dag/nodes", response_class=HTMLResponse)
async def dag_add_node(request: Request) -> str:
    from core.task_dag import TaskDAG

    form = await request.form()
    dag = TaskDAG()
    dag.add_node(
        form.get("id", ""),
        depends_on=[
            x.strip() for x in form.get("depends_on", "").split(",") if x.strip()
        ],
        description=form.get("description", ""),
    )
    dag.save()
    # 返回行（HTMX oob 刷新）
    idx = form.get("id", "")
    return f"""<tr id="dag-row-{idx}">
  <td>{idx}</td>
  <td>{form.get("depends_on", "")}</td>
  <td>{form.get("description", "")}</td>
</tr>"""


@router.delete("/dag/nodes/{node_id}", response_class=HTMLResponse)
async def dag_delete_node(node_id: str) -> str:
    from core.task_dag import TaskDAG

    dag = TaskDAG()
    dag.remove_node(node_id)
    dag.save()
    return ""


# ====== 系统监控 ======


@router.get("/monitor", response_class=HTMLResponse)
async def monitor_page(request: Request) -> str:
    resources: dict[str, Any] = {
        "cpu_percent": 0,
        "memory_percent": 0,
        "disk": {"total_gb": 0, "used_gb": 0, "free_gb": 0, "percent": 0},
        "timestamp": time.time(),
    }
    health: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    try:
        from core.monitor import SystemMonitor

        mon = SystemMonitor()
        resources = mon.resource_usage()
        health = [
            {
                "service": h.service,
                "status": h.status,
                "latency_ms": round(h.latency_ms, 1),
            }
            for h in mon.check_services()
        ]
        alerts = mon.evaluate_alerts(resources)
    except Exception:
        pass
    return HTMLResponse(
        content=_render(
            "admin/monitor.html",
            active="monitor",
            resources=resources,
            health=health,
            alerts=alerts,
        )
    )


# ====== 森林平面图 ======


@router.get("/floorplan", response_class=HTMLResponse)
async def floorplan_page(request: Request) -> str:
    aggr: dict[str, Any] = {
        "success": 0,
        "failed": 0,
        "pending": 0,
        "total": 0,
        "health": "良好",
    }
    try:
        if _harness:
            aggr = _harness.aggregate()
    except Exception:
        pass
    return HTMLResponse(
        content=_render(
            "admin/floorplan.html",
            active="floorplan",
            aggr=aggr,
        )
    )


# ====== Agent 市场 ======


@router.get("/agents", response_class=HTMLResponse)
async def agents_page(request: Request) -> str:
    categories: list[str] = []
    try:
        from core.agent_market import get_market

        m = get_market()
        m.refresh_from_registry()
        categories = m.get_categories()
    except Exception:
        pass
    return HTMLResponse(
        content=_render(
            "admin/agents.html",
            active="agents",
            categories=categories,
        )
    )


# ====== Agent 健康 ======


@router.get("/agent-health", response_class=HTMLResponse)
async def agent_health_page(request: Request) -> str:
    return HTMLResponse(
        content=_render(
            "admin/agent_health.html",
            active="agent-health",
        )
    )


# ====== 告警引擎 ======


@router.get("/alerts", response_class=HTMLResponse)
async def alerts_page(request: Request) -> str:
    return HTMLResponse(
        content=_render(
            "admin/alerts.html",
            active="alerts",
        )
    )


# ====== 日志查看 ======


@router.get("/logs", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    level: str = Query(default=""),
    component: str = Query(default=""),
    keyword: str = Query(default=""),
    action: str = Query(default=""),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
) -> str:
    from core.log_viewer import LogViewer

    viewer = LogViewer()
    viewer.reload()
    result = viewer.query(
        level=level or None,
        component=component or None,
        keyword=keyword or None,
        action=action or None,
        offset=offset,
        limit=limit,
    )
    stats = viewer.stats()
    entries_data = result.get("entries", [])
    return HTMLResponse(
        content=_render(
            "admin/logs.html",
            active="logs",
            log_stats=stats,
            entries=entries_data,
            total_entries=result.get("filtered", 0),
            offset=offset,
            limit=limit,
        )
    )


# ====== 报告 ======


@router.get("/report", response_class=HTMLResponse)
async def report_page(request: Request) -> str:
    return HTMLResponse(content=_render("admin/report.html", active="report"))


@router.post("/report/generate", response_class=HTMLResponse)
async def report_generate(
    request: Request,
    title: str = Form("BlueDeer 任务报告"),
    fmt: str = Form("markdown"),
) -> str:
    if _harness is None:
        return '<div class="toast toast-error">Harness 未初始化</div>'
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
        title=title,
    )
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    preview = content[:2000]
    return f"""<div class="card">
  <div class="flex-between">
    <h3>📄 报告已生成</h3>
    <a href="/{path}" target="_blank" class="btn btn-sm btn-primary">打开</a>
  </div>
  <p class="text-muted" style="margin:8px 0;">{path} ({len(content)} 字符)</p>
  <pre style="background:var(--bg-primary);padding:12px;border-radius:4px;font-size:11px;max-height:400px;overflow-y:auto;white-space:pre-wrap;word-break:break-all;">{preview}</pre>
</div>"""


# ====== Agent 市场 ======


@router.get("/agents", response_class=HTMLResponse)
async def agents_page(request: Request) -> str:
    return HTMLResponse(content=_render("admin/agents.html", active="agents"))


# ====== Agent 健康 ======


@router.get("/agent-health", response_class=HTMLResponse)
async def agent_health_page(request: Request) -> str:
    return HTMLResponse(
        content=_render("admin/agent_health.html", active="agent-health")
    )


# ====== 通信日志 ======


@router.get("/comm-log", response_class=HTMLResponse)
async def comm_log_page(request: Request) -> str:
    return HTMLResponse(content=_render("admin/comm_log.html", active="comm-log"))


# ====== Plugin 仓库 ======


@router.get("/plugin-repo", response_class=HTMLResponse)
async def plugin_repo_page(request: Request) -> str:
    return HTMLResponse(content=_render("admin/plugin_repo.html", active="plugin-repo"))


# ====== Gantt 图 ======


@router.get("/gantt", response_class=HTMLResponse)
async def gantt_page(request: Request) -> str:
    return HTMLResponse(content=_render("admin/gantt.html", active="gantt"))


# ====== 重试策略 ======


@router.get("/retry", response_class=HTMLResponse)
async def retry_page(request: Request) -> str:
    return HTMLResponse(content=_render("admin/retry.html", active="retry"))


# ====== 用户管理 ======


@router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request) -> str:
    return HTMLResponse(content=_render("admin/users.html", active="users"))


# ====== DAG 模板库 ======


@router.get("/dag-templates", response_class=HTMLResponse)
async def dag_templates_page(request: Request) -> str:
    return HTMLResponse(
        content=_render("admin/dag_templates.html", active="dag-templates")
    )


# ====== 森林生物圈游戏 ======


@router.get("/game", response_class=HTMLResponse)
async def game_page(request: Request) -> str:
    return HTMLResponse(content=_render("admin/game.html", active="game"))


# ====== 森林公司房间详情页 ======


@router.get("/floorplan/library", response_class=HTMLResponse)
async def room_library(request: Request) -> str:
    return HTMLResponse(content=_render("admin/room_library.html", active="floorplan"))


@router.get("/floorplan/breakroom", response_class=HTMLResponse)
async def room_breakroom(request: Request) -> str:
    return HTMLResponse(
        content=_render("admin/room_breakroom.html", active="floorplan")
    )


@router.get("/floorplan/rest", response_class=HTMLResponse)
async def room_rest(request: Request) -> str:
    return HTMLResponse(content=_render("admin/room_rest.html", active="floorplan"))


@router.get("/floorplan/office", response_class=HTMLResponse)
async def room_office(request: Request) -> str:
    return HTMLResponse(content=_render("admin/room_office.html", active="floorplan"))


# ====== 审计日志 ======


@router.get("/audit", response_class=HTMLResponse)
async def audit_page(request: Request) -> str:
    return HTMLResponse(content=_render("admin/audit.html", active="audit"))
