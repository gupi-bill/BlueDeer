"""BlueDeer 森林公司仪表盘服务器。

启动方式: python -m uvicorn web_server:app --reload --port 8080
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import logging
import os
import time
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from core.breakroom import BreakRoom
from core.canvas import Canvas
from core.config import get_config
from core.debugger import Debugger
from core.github_knowledge import GitHubKnowledge
from core.jarvis import JARVIS
from core.library import Library
from core.office import OfficeManager
from core.plugin_manager import PluginManager
from core.restarea import RestArea
from core.scene import CEOOffice
from core.vector_browser import VectorBrowser

logger = logging.getLogger("bluedeer.web")

# ===== 响应缓存 =====
_RESPONSE_CACHE: dict[str, tuple[float, Any]] = {}  # cache_key -> (expires_at, data)


def cache_response(ttl: int = 60) -> Callable:
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{hash(frozenset(kwargs.items()))}"
            now = time.time()
            cached = _RESPONSE_CACHE.get(cache_key)
            if cached and cached[0] > now:
                return cached[1]
            result = await func(*args, **kwargs)
            _RESPONSE_CACHE[cache_key] = (now + ttl, result)
            return result

        return wrapper

    return decorator


def invalidate_cache(pattern: str | None = None) -> None:
    if pattern is None:
        _RESPONSE_CACHE.clear()
    else:
        _RESPONSE_CACHE.clear()


# ===== 请求验证中间件 =====

app = FastAPI(title="BlueDeer 森林公司仪表盘")


class ValidationMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        await self.app(scope, receive, send)


@app.middleware("http")
async def request_validation_middleware(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH"):
        content_type = request.headers.get("content-type", "")
        if "json" in content_type:
            try:
                body = await request.json()
            except Exception:
                return Response(
                    content='{"error": "无效的 JSON"}',
                    status_code=400,
                    media_type="application/json",
                )
    response = await call_next(request)
    return response


# ---- Gzip 压缩中间件 ----
from fastapi.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)


# ---- 静态文件缓存 ----
_STATIC_CACHE: dict[str, tuple[str, str, float]] = (
    {}
)  # path -> (etag, content_type, mtime)


def _build_etag(filepath: str) -> str:
    h = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            h.update(f.read(8192))
    except OSError:
        pass
    return h.hexdigest()[:16]


@app.middleware("http")
async def static_cache_middleware(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/static/") and not path.startswith("/sprites/"):
        return await call_next(request)

    filepath = path.lstrip("/")
    if not os.path.exists(filepath):
        return await call_next(request)

    mtime = os.path.getmtime(filepath)
    cached = _STATIC_CACHE.get(filepath)
    if cached and cached[2] == mtime:
        etag, content_type, _ = cached
    else:
        etag = _build_etag(filepath)
        import mimetypes

        content_type, _ = mimetypes.guess_type(filepath)
        _STATIC_CACHE[filepath] = (
            etag,
            content_type or "application/octet-stream",
            mtime,
        )

    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match.strip('"') == etag:
        return Response(status_code=304)

    response = await call_next(request)
    response.headers["Cache-Control"] = "public, max-age=86400, immutable"
    response.headers["ETag"] = f'"{etag}"'
    return response


# 初始化场景
library = Library()
breakroom = BreakRoom()
office_manager = OfficeManager()
rest_area = RestArea()
scene = CEOOffice(
    library=library,
    breakroom=breakroom,
    office_manager=office_manager,
    rest_area=rest_area,
)
github = GitHubKnowledge(library=library)
jarvis = JARVIS(scene=scene)

# ===== 插件系统 =====
plugin_manager = PluginManager(plugin_dir="plugins")

# ===== 向量浏览器 =====
vector_browser = VectorBrowser(db_root="data")

# ===== API Server =====
from core.api_server import init_api
from core.event_bus import EventBus
from core.harness import Harness
from core.scheduler import Scheduler
from core.task_dag import TaskDAG
from core.task_templates import TaskTemplates
from core.webhook import WebhookDispatcher
from run_biosphere import Biosphere
from web_admin import init_admin

event_bus = EventBus()
harness = Harness(event_bus=event_bus)
scheduler = Scheduler(event_bus, harness)
webhook = WebhookDispatcher(event_bus)
templates_engine = TaskTemplates()

# 共享 DAG 实例，自动绑入 harness + scheduler + webhook
dag = TaskDAG()
harness.set_dag(dag)
harness.set_webhook(webhook)
scheduler.set_dag(dag)

api_router = init_api(
    bus=event_bus, harness=harness, scheduler=scheduler, webhook=webhook
)
admin_router = init_admin(
    bus=event_bus,
    harness=harness,
    scheduler=scheduler,
    webhook=webhook,
    templates_engine=templates_engine,
)
app.include_router(api_router)
app.include_router(admin_router)

# ── 生物圈游戏路由器 ──
from core.game_router import init_biosphere
from core.game_router import router as game_router

app.include_router(game_router)

# 生物圈全局实例（延迟初始化）
_biosphere_instance: Biosphere | None = None

# 注册员工办公室
for agent_id, name, role in [
    ("squirrel", "较真松鼠", "代码工程师"),
    ("hedgehog", "戒备猬", "安全工程师"),
    ("owl", "夜枭猫头鹰", "算法工程师"),
    ("beaver", "勤恳海狸", "运维工程师"),
    ("fox", "狡黠狐狸", "测试工程师"),
]:
    office = office_manager.get_or_create(agent_id, name, role)
    for skill in ["代码审查", "Bug 修复", "性能优化"]:
        office.register_skill(skill, f"{role}技能")

# ===== 调试面板 =====
debugger = Debugger(enabled=True)
debugger.enable()
canvas = Canvas(debugger)


# ===== 启动/关闭事件 =====
@app.on_event("startup")
async def startup() -> None:
    """应用启动时加载插件、启动后台服务、初始化生物圈。"""
    loaded = await plugin_manager.load_all()
    if loaded:
        logger.info("已加载 %d 个插件: %s", len(loaded), loaded)
        await plugin_manager.ready_all()
    else:
        logger.info("未发现插件，跳过")

    await scheduler.start()
    await webhook.start()
    logger.info("调度器和 Webhook 分发器已启动")
    asyncio.create_task(_periodic_ws_health())
    logger.info("WebSocket 健康推送已启动")

    # ── 启动生物圈 ──
    global _biosphere_instance
    try:
        bio = Biosphere(save_path="data/biosphere_save.json")
        bio.bootstrap(load=True)
        bio.start()
        _biosphere_instance = bio
        init_biosphere(bio)
        logger.info("🌿 森林生物圈已启动")
    except Exception as e:
        logger.warning("生物圈启动失败（可忽略）: %s", e)


async def _periodic_ws_health() -> None:
    """每 10s 通过 WS 推送系统健康状态 + 告警评估。"""
    while True:
        await asyncio.sleep(10)
        try:
            agg = harness.aggregate()
            data = {
                "total": agg.get("total", 0),
                "success": agg.get("success", 0),
                "failed": agg.get("failed", 0),
                "pending": agg.get("pending", 0),
                "in_flight": len(agg.get("in_flight", {})),
            }
            await ws_manager.broadcast(
                {
                    "event": "health",
                    "ts": time.time(),
                    "data": data,
                }
            )

            from core.alert import get_alert_engine

            ae = get_alert_engine()
            total = data["total"] or 1
            event = ae.evaluate("failed_rate", data["failed"] / total)
            if event:
                await ws_manager.broadcast(
                    {
                        "event": "alert",
                        "ts": time.time(),
                        "data": {
                            "rule_id": event.rule_id,
                            "severity": event.severity,
                            "message": event.message,
                        },
                    }
                )
            ae.evaluate("pending_count", data["pending"])
        except Exception:
            pass


@app.on_event("shutdown")
async def shutdown() -> None:
    """应用关闭时清理资源。"""
    await scheduler.stop()
    await webhook.stop()
    await plugin_manager.shutdown()

    # ── 停止生物圈 ──
    global _biosphere_instance
    if _biosphere_instance is not None:
        try:
            _biosphere_instance.stop()
            logger.info("🌿 森林生物圈已停止")
        except Exception as e:
            logger.warning("生物圈停止异常: %s", e)


# 挂载静态文件
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
# 精灵（game_frontend JS 请求 /sprites/<name>_sprite.png）
os.makedirs("static/sprites", exist_ok=True)
app.mount("/sprites", StaticFiles(directory="static/sprites"), name="sprites")

# ===== WebSocket 实时推送 =====


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._subs: dict[WebSocket, set[str]] = {}

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        self._subs[ws] = set()

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        self._subs.pop(ws, None)

    def subscribe(self, ws: WebSocket, event: str) -> None:
        if ws in self._subs:
            self._subs[ws].add(event)

    def unsubscribe(self, ws: WebSocket, event: str) -> None:
        if ws in self._subs:
            self._subs[ws].discard(event)

    async def broadcast(self, data: dict[str, Any]) -> None:
        event = data.get("event", "")
        for ws in list(self._connections):
            subs = self._subs.get(ws, set())
            if event and subs and event not in subs:
                continue
            try:
                await ws.send_json(data)
            except Exception:
                self._connections.discard(ws)
                self._subs.pop(ws, None)


ws_manager = ConnectionManager()
harness.set_task_event_cb(ws_manager.broadcast)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws_manager.connect(ws)
    try:
        while True:
            msg = await ws.receive_text()
            if msg.startswith("sub:"):
                ev = msg[4:]
                if ev == "*":
                    ws_manager._subs[ws] = set()
                else:
                    ws_manager.subscribe(ws, ev)
            elif msg.startswith("unsub:"):
                ws_manager.unsubscribe(ws, msg[6:])
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


@app.websocket("/ws/admin")
async def admin_ws(ws: WebSocket) -> None:
    """Admin 专用 WS：自动订阅所有事件 + 定期心跳。"""
    await ws_manager.connect(ws)
    ws_manager.subscribe(ws, "task_result")
    ws_manager.subscribe(ws, "health")
    ws_manager.subscribe(ws, "system")
    try:
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                try:
                    await ws.send_json({"event": "pong", "ts": time.time()})
                except Exception:
                    break
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ===== Admin 认证 =====

ADMIN_USER = "admin"
ADMIN_PASS = "bluedeer888"
ADMIN_AUTH_ENABLED = os.environ.get("BLUEDEER_AUTH", "true").lower() in (
    "1",
    "true",
    "yes",
)


LOGIN_HTML = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><title>BlueDeer 登录</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box;}
  body{font-family:system-ui,sans-serif;background:#1a2a1a;display:flex;align-items:center;justify-content:center;min-height:100vh;}
  .card{background:#2a3a2a;padding:32px;border-radius:12px;width:360px;box-shadow:0 8px 32px rgba(0,0,0,0.3);}
  h2{color:#a5d6a7;margin-bottom:20px;text-align:center;}
  .sub{color:#6a8a6a;text-align:center;font-size:12px;margin-bottom:16px;}
  input{width:100%;padding:10px;margin-bottom:12px;border:1px solid #3a5a3a;border-radius:6px;background:#1a2a1a;color:#e0e0e0;outline:none;}
  input:focus{border-color:#4caf50;}
  button{width:100%;padding:10px;background:#388e3c;border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:14px;}
  button:hover{background:#43a047;}
  .error{color:#ef5350;margin-top:8px;text-align:center;font-size:13px;}
</style></head><body>
<div class="card">
  <h2>🦌 BlueDeer 登录</h2>
  <div class="sub">森林公司管理系统</div>
  <form method="post" action="/admin/login">
    <input type="text" name="username" placeholder="用户名" required autofocus>
    <input type="password" name="password" placeholder="密码" required>
    <button type="submit">登 录</button>
  </form>
  <div id="error" class="error"></div>
</div></body></html>"""


@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request) -> str:
    return LOGIN_HTML


@app.post("/admin/login")
async def admin_login(request: Request) -> HTMLResponse:
    form = await request.form()
    u, p = form.get("username", ""), form.get("password", "")
    from core.auth import get_auth

    session = get_auth().authenticate(u, p)
    if session:
        resp = RedirectResponse(url="/admin", status_code=302)
        resp.set_cookie(
            key="bluedeer_token", value=session.token, max_age=86400, httponly=True
        )
        return resp
    return HTMLResponse(
        content=LOGIN_HTML.replace(
            '<div id="error" class="error"></div>',
            '<div class="error">用户名或密码错误</div>',
        )
    )


@app.get("/admin/logout")
async def admin_logout(request: Request) -> RedirectResponse:
    token = request.cookies.get("bluedeer_token", "")
    if token:
        from core.auth import get_auth

        get_auth().logout(token)
    resp = RedirectResponse(url="/admin/login", status_code=302)
    resp.delete_cookie("bluedeer_token")
    return resp


if ADMIN_AUTH_ENABLED:

    @app.middleware("http")
    async def admin_auth_middleware(request: Request, call_next):
        path = request.url.path
        if path.startswith("/admin") and path not in ("/admin/login", "/admin/logout"):
            token = request.cookies.get("bluedeer_token", "")
            from core.auth import get_auth

            session = get_auth().get_session(token)
            if not session:
                return RedirectResponse(url="/admin/login", status_code=302)
            request.state.user = session.username
            request.state.role = session.role
        return await call_next(request)


# ── 用户管理 API ──


def _require_role(role: str, request: Request) -> bool:
    from core.auth import ROLE_HIERARCHY

    user_role = getattr(request.state, "role", "viewer")
    return ROLE_HIERARCHY.get(user_role, 0) >= ROLE_HIERARCHY.get(role, 0)


@app.get("/api/users")
async def list_users(request: Request) -> dict[str, Any]:
    from core.auth import get_auth

    return {"users": get_auth().list_users()}


@app.post("/api/users")
async def create_user(request: Request) -> dict[str, Any]:
    if not _require_role("admin", request):
        return {"ok": False, "error": "权限不足"}
    from core.auth import get_auth

    body = await request.json()
    try:
        get_auth().create_user(
            username=body["username"],
            password=body["password"],
            role=body.get("role", "viewer"),
            display_name=body.get("display_name", ""),
            email=body.get("email", ""),
        )
        return {"ok": True}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


@app.put("/api/users/{username}")
async def update_user(username: str, request: Request) -> dict[str, Any]:
    if not _require_role("admin", request):
        return {"ok": False, "error": "权限不足"}
    from core.auth import get_auth

    body = await request.json()
    ok = get_auth().update_user(
        username, **{k: v for k, v in body.items() if v is not None}
    )
    return {"ok": ok}


@app.delete("/api/users/{username}")
async def delete_user(username: str, request: Request) -> dict[str, Any]:
    if not _require_role("admin", request):
        return {"ok": False, "error": "权限不足"}
    from core.auth import get_auth

    ok = get_auth().delete_user(username)
    return {"ok": ok}


@app.get("/api/users/tokens")
async def list_tokens(request: Request) -> dict[str, Any]:
    from core.auth import get_auth

    username = request.state.user if hasattr(request.state, "user") else ""
    return {"tokens": get_auth().list_api_tokens(username)}


@app.post("/api/users/tokens")
async def create_token(request: Request) -> dict[str, Any]:
    from core.auth import get_auth

    body = await request.json()
    username = request.state.user if hasattr(request.state, "user") else "admin"
    token = get_auth().create_api_token(username, body.get("name", "default"))
    return {"ok": True, "token": token.token}


@app.delete("/api/users/tokens/{token_str}")
async def revoke_token(token_str: str, request: Request) -> dict[str, Any]:
    from core.auth import get_auth

    ok = get_auth().revoke_api_token(token_str)
    return {"ok": ok}


# ── 系统健康 API ──


@app.get("/api/system/health")
async def system_health() -> dict[str, Any]:
    import time

    stats = harness.aggregate() or {}
    tasks = stats.get("tasks", {})
    success = tasks.get("success", 0)
    failed = tasks.get("failed", 0)
    total = tasks.get("total", 1) or 1
    rate = round(success / total * 100, 1)
    mem_mb = 0
    threads = 0
    try:
        import psutil

        proc = psutil.Process()
        mem_mb = round(proc.memory_info().rss / 1024 / 1024, 1)
        threads = proc.num_threads()
    except Exception:
        pass
    return {
        "status": "ok" if rate > 80 else "degraded" if rate > 50 else "critical",
        "uptime": f"{time.time() - stats.get('started_at', time.time()):.0f}s",
        "threads": threads,
        "memory": f"{mem_mb} MB",
        "success_rate": rate,
        "total_tasks": total,
        "failed_tasks": failed,
    }


# ── RAG 统计 API ──


@app.get("/api/rag/stats")
async def rag_stats() -> dict[str, Any]:
    try:
        from core.rag_engine import get_rag_engine

        engine = get_rag_engine()
        info = (
            engine.info()
            if hasattr(engine, "info")
            else engine.get_stats() if hasattr(engine, "get_stats") else {}
        )
        return {
            "total_docs": info.get("total_docs", info.get("document_count", 0)),
            "total_tags": info.get("total_tags", info.get("tag_count", 0)),
            "graph_edges": info.get("graph_edges", info.get("edge_count", 0)),
            "last_indexed": info.get("last_indexed", info.get("last_update", "--")),
        }
    except ImportError:
        return {
            "total_docs": 0,
            "total_tags": 0,
            "graph_edges": 0,
            "last_indexed": "--",
        }
    except Exception:
        return {
            "total_docs": 0,
            "total_tags": 0,
            "graph_edges": 0,
            "last_indexed": "--",
        }


# ── 奖励排行榜 API ──


@app.get("/api/rewards/leaderboard")
async def rewards_leaderboard() -> dict[str, Any]:
    try:
        from core.reward import RewardSystem

        rs = RewardSystem.load("data/rewards.json")
        lb = rs.leaderboard()
        if isinstance(lb, list):
            return {"leaderboard": lb}
        return {"leaderboard": []}
    except Exception:
        return {"leaderboard": []}


# ── 清理 API ──


@app.get("/api/cleanup/stats")
async def cleanup_stats() -> dict[str, Any]:
    from core.cleanup import get_storage_stats

    return get_storage_stats()


@app.post("/api/cleanup/run")
async def cleanup_run(request: Request) -> dict[str, Any]:
    from core.cleanup import run_cleanup

    body = (
        await request.json()
        if request.headers.get("content-type", "").startswith("application/json")
        else {}
    )
    dry_run = body.get("dry_run", False)
    max_days = body.get("max_days", 14)
    result = run_cleanup(dry_run=dry_run, max_days=max_days)
    return {
        "ok": True,
        "removed": result.removed,
        "freed_bytes": result.freed_bytes,
        "db_vacuumed": result.db_vacuumed,
        "errors": result.errors,
    }


# ── 备份 API ──


@app.get("/api/backups")
async def list_backups_api() -> dict[str, Any]:
    from core.backup import list_backups

    return {"backups": list_backups()}


@app.post("/api/backups")
async def create_backup_api(request: Request) -> dict[str, Any]:
    from core.backup import create_backup

    body = (
        await request.json()
        if request.headers.get("content-type", "").startswith("application/json")
        else {}
    )
    path = create_backup(name=body.get("name", ""), db_only=body.get("db_only", False))
    return {"ok": True, "path": path}


@app.post("/api/backups/restore")
async def restore_backup_api(request: Request) -> dict[str, Any]:
    from core.backup import restore_backup

    body = await request.json()
    dry_run = body.get("dry_run", False)
    file_path = body.get("file", "")
    if not file_path:
        return {"ok": False, "error": "缺少 file 参数"}
    try:
        files = restore_backup(file_path, dry_run=dry_run)
        return {"ok": True, "files": files, "dry_run": dry_run}
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}


@app.delete("/api/backups/{filename}")
async def delete_backup_api(filename: str) -> dict[str, Any]:
    from core.backup import delete_backup

    ok = delete_backup(filename)
    return {"ok": ok}


@app.get("/api/traces")
async def list_traces() -> dict[str, Any]:
    """列出所有 trace 摘要。"""
    summaries = debugger.summary()
    return {
        "traces": [
            {
                "trace_id": s.trace_id,
                "span_count": s.span_count,
                "total_duration_ms": s.total_duration_ms,
                "component_count": len(s.agent_spans),
                "error_count": len(s.errors),
                "token_usage": s.token_usage,
            }
            for s in summaries
        ],
        "total": len(summaries),
    }


@app.get("/api/traces/{trace_id}")
async def get_trace(trace_id: str) -> dict[str, Any]:
    """获取指定 trace 的 Chrome Trace Event Format 数据。"""
    # 从 debugger 导出为事件列表
    spans = debugger._spans.get(trace_id, [])
    events = []
    pid = 1
    for span in spans:
        ts_us = int(span.timestamp * 1_000_000)
        dur_us = int(span.duration_ms * 1_000) if span.duration_ms > 0 else 0
        args = dict(span.fields)
        if span.error:
            args["error"] = span.error
        events.append(
            {
                "ph": "X" if dur_us > 0 else "i",
                "name": f"{span.component}.{span.action}",
                "cat": span.component,
                "ts": ts_us,
                "dur": max(0, dur_us),
                "pid": pid,
                "tid": hash(span.component) % 1000,
                "args": args,
            }
        )
    return {"trace_id": trace_id, "events": events, "count": len(events)}


@app.get("/api/traces/{trace_id}/summary")
async def get_trace_summary(trace_id: str) -> dict[str, Any]:
    """获取指定 trace 的摘要。"""
    summaries = debugger.summary(trace_id)
    if not summaries:
        return {"summary": None}
    s = summaries[0]
    return {
        "summary": {
            "trace_id": s.trace_id,
            "total_duration_ms": s.total_duration_ms,
            "span_count": s.span_count,
            "agent_spans": {
                comp: [
                    {
                        "action": sp.action,
                        "duration_ms": sp.duration_ms,
                        "error": sp.error,
                    }
                    for sp in spans
                ]
                for comp, spans in s.agent_spans.items()
            },
            "errors": [
                {
                    "component": e.component,
                    "action": e.action,
                    "error": e.error,
                }
                for e in s.errors
            ],
            "token_usage": s.token_usage,
        }
    }


@app.post("/api/test_traces")
async def generate_test_traces() -> dict[str, Any]:
    """生成测试 trace 数据用于演示。"""
    import random

    trace_id = f"test_{int(time.time())}_{random.randint(1000, 9999)}"
    agents = [
        "Squirrel",
        "Fox",
        "Beaver",
        "Owl",
        "Hedgehog",
        "EventBus",
        "ToolRegistry",
    ]
    actions = [
        "handle_start",
        "handle_success",
        "tool_call",
        "tool_result",
        "model_query",
        "model_response",
        "rag_retrieve",
        "rag_result",
        "event_publish",
        "event_receive",
    ]

    # 生成 agent 级 span
    debugger.record_span(trace_id, "Workflow", "orchestrate_start")
    await asyncio.sleep(0.01)

    for agent in agents[: random.randint(3, 6)]:
        debugger.record_span(
            trace_id, agent, "handle_start", tokens_in=random.randint(50, 500)
        )
        await asyncio.sleep(random.uniform(0.005, 0.03))

        # sub-actions
        for _ in range(random.randint(1, 3)):
            action = random.choice(actions)
            debugger.record_span(
                trace_id,
                agent,
                action,
                tokens_in=random.randint(10, 200),
                tokens_out=random.randint(5, 100),
            )
            await asyncio.sleep(random.uniform(0.002, 0.015))

        # 随机错误
        if random.random() < 0.15:
            debugger.record_span(
                trace_id,
                agent,
                "handle_failed",
                error=f"模拟超时 ({random.randint(1, 5)}s)",
            )
        else:
            debugger.record_span(
                trace_id, agent, "handle_success", tokens_out=random.randint(20, 300)
            )

    debugger.record_span(trace_id, "Workflow", "orchestrate_success")
    await asyncio.sleep(0.01)

    return {
        "trace_id": trace_id,
        "message": f"已生成测试 trace: {trace_id[:12]}…",
    }


@app.get("/api/canvas/{trace_id}")
async def get_canvas(trace_id: str) -> dict[str, Any]:
    """获取指定 trace 的 Mermaid 流程图。"""
    code = canvas.render(trace_id)
    return {"trace_id": trace_id, "mermaid": code}


@app.get("/api/canvas/flow")
async def get_canvas_flow() -> dict[str, Any]:
    """获取简化流程图。"""
    code = canvas.render_flow()
    return {"mermaid": code}


@app.get("/api/plugins")
async def list_plugins() -> dict[str, Any]:
    """列出所有插件及其状态。"""
    names = plugin_manager.plugin_names
    return {
        "plugins": [
            {
                "name": name,
                **plugin_manager.get_status(name),
            }
            for name in names
        ],
        "total": len(names),
    }


@app.get("/api/plugins/{name}/enable")
async def enable_plugin(name: str) -> dict[str, Any]:
    ok = plugin_manager.enable(name)
    return {"success": ok, "name": name}


@app.get("/api/plugins/{name}/disable")
async def disable_plugin(name: str) -> dict[str, Any]:
    ok = plugin_manager.disable(name)
    return {"success": ok, "name": name}


# ── Agent Market ──

_agent_registry_loaded = False


def _ensure_agent_registry() -> None:
    global _agent_registry_loaded
    if _agent_registry_loaded:
        return
    from core.agent_registry import AgentRegistry

    registry = getattr(app.state, "agent_registry", None)
    if registry is None:
        registry = AgentRegistry()
        app.state.agent_registry = registry
    # 自动发现 modules/*/agent.py 下的 Agent 类
    import importlib
    from pathlib import Path

    modules_dir = Path("modules")
    if modules_dir.is_dir():
        for child in modules_dir.iterdir():
            agent_file = child / "agent.py"
            if agent_file.is_file():
                try:
                    mod = importlib.import_module(f"modules.{child.name}.agent")
                    for attr in dir(mod):
                        cls = getattr(mod, attr)
                        if isinstance(cls, type) and "BaseAgent" in [
                            b.__name__ for b in cls.__mro__
                        ]:
                            registry.register(cls)
                except Exception as e:
                    logger.debug("跳过模块 %s: %s", child.name, e)
    # 同步到市场
    try:
        from core.agent_market import get_market

        get_market().refresh_from_registry()
    except Exception:
        pass
    _agent_registry_loaded = True


@app.get("/api/agents")
async def list_agents() -> dict[str, Any]:
    _ensure_agent_registry()
    registry = app.state.agent_registry
    agents = registry.list_agents()
    return {
        "agents": [
            {
                "name": a.name,
                "role": a.role,
                "description": a.description[:120],
                "capabilities": a.capabilities,
                "base_class": a.base_class,
                "source": a.source,
                "enabled": a.enabled,
                "tags": a.tags,
            }
            for a in agents
        ],
        "total": len(agents),
    }


@app.get("/api/agents/search")
async def search_agents(q: str = "") -> dict[str, Any]:
    _ensure_agent_registry()
    if not q:
        return await list_agents()
    hits = app.state.agent_registry.search(q)
    return {
        "query": q,
        "agents": [
            {
                "name": a.name,
                "role": a.role,
                "description": a.description[:120],
                "capabilities": a.capabilities,
            }
            for a in hits
        ],
        "total": len(hits),
    }


@app.get("/api/agents/{name}")
async def get_agent(name: str) -> dict[str, Any]:
    _ensure_agent_registry()
    info = app.state.agent_registry.get_agent(name)
    if info is None:
        return {"success": False, "error": f"Agent {name} 未找到"}
    return {
        "success": True,
        "agent": {
            "name": info.name,
            "role": info.role,
            "module": info.module,
            "version": info.version,
            "description": info.description,
            "capabilities": info.capabilities,
            "base_class": info.base_class,
            "source": info.source,
            "source_url": info.source_url,
            "enabled": info.enabled,
            "tags": info.tags,
        },
    }


@app.get("/api/agents/{name}/enable")
async def enable_agent(name: str) -> dict[str, Any]:
    _ensure_agent_registry()
    ok = app.state.agent_registry.set_enabled(name, True)
    return {"success": ok, "name": name}


@app.get("/api/agents/{name}/disable")
async def disable_agent(name: str) -> dict[str, Any]:
    _ensure_agent_registry()
    ok = app.state.agent_registry.set_enabled(name, False)
    return {"success": ok, "name": name}


# ── Agent Health ──

_agent_monitor = None


def _get_agent_monitor():
    global _agent_monitor
    if _agent_monitor is None:
        from core.agent_monitor import AgentMonitor

        _agent_monitor = AgentMonitor()
    return _agent_monitor


@app.get("/api/agents/health")
async def agent_health_summary() -> dict[str, Any]:
    mon = _get_agent_monitor()
    summary = mon.summary()
    return {
        "total_agents": summary.total_agents,
        "total_runs": summary.total_runs,
        "total_failures": summary.total_failures,
        "global_success_rate": summary.global_success_rate,
        "agents": [
            {
                "agent_id": a.agent_id,
                "role": a.role,
                "total_runs": a.total_runs,
                "success_count": a.success_count,
                "failure_count": a.failure_count,
                "avg_duration_ms": a.avg_duration_ms,
                "last_run_at": a.last_run_at,
                "last_error": a.last_error,
                "success_rate": (
                    round(a.success_count / a.total_runs * 100, 1)
                    if a.total_runs
                    else 0
                ),
            }
            for a in summary.agents
        ],
    }


@app.get("/api/agents/{name}/health")
async def agent_health_detail(
    name: str, max_errors: int = 10, max_recent: int = 10
) -> dict[str, Any]:
    mon = _get_agent_monitor()
    health = mon.get_health(agent_id=name, max_errors=max_errors, max_recent=max_recent)
    if isinstance(health, list):
        return {"found": False, "error": f"Agent {name} 未找到"}
    return {
        "found": True,
        "health": {
            "agent_id": health.agent_id,
            "role": health.role,
            "total_runs": health.total_runs,
            "success_count": health.success_count,
            "failure_count": health.failure_count,
            "avg_duration_ms": health.avg_duration_ms,
            "min_duration_ms": health.min_duration_ms,
            "max_duration_ms": health.max_duration_ms,
            "last_run_at": health.last_run_at,
            "last_error": health.last_error,
            "success_rate": (
                round(health.success_count / health.total_runs * 100, 1)
                if health.total_runs
                else 0
            ),
            "errors": health.errors,
            "recent_runs": health.recent_runs,
        },
    }


# ── Communication Log ──

_comm_log = None


def _get_comm_log():
    global _comm_log
    if _comm_log is None:
        from core.comm_log import CommLog

        _comm_log = CommLog()
    return _comm_log


@app.get("/api/comm-log")
async def comm_log_query(
    trace_id: str = "",
    agent: str = "",
    action: str = "",
    max_chains: int = 50,
) -> dict[str, Any]:
    log = _get_comm_log()
    result = log.query(
        trace_id=trace_id or None,
        agent=agent or None,
        action=action or None,
        max_chains=max_chains,
    )
    return {
        "chains": [
            {
                "trace_id": c.trace_id,
                "agents": c.agents,
                "agent_count": c.agent_count,
                "entry_count": c.entry_count,
                "error_count": c.error_count,
                "start_ts": c.start_ts,
                "end_ts": c.end_ts,
                "duration_sec": c.duration_sec,
                "entries": [
                    {
                        "ts": e.ts,
                        "ts_str": e.ts_str,
                        "component": e.component,
                        "action": e.action,
                        "level": e.level,
                        "message": e.message,
                        "duration_ms": e.duration_ms,
                        "error": e.error,
                    }
                    for e in c.entries
                ],
            }
            for c in result.chains
        ],
        "total_chains": result.total_chains,
        "total_entries": result.total_entries,
        "agent_list": result.agent_list,
    }


@app.get("/api/comm-log/summary")
async def comm_log_summary() -> dict[str, Any]:
    from core.comm_log import CommLogViewer

    log = _get_comm_log()
    return CommLogViewer.summary(log)


# ── Plugin Repository ──

_plugin_repo = None


def _get_plugin_repo():
    global _plugin_repo
    if _plugin_repo is None:
        from core.plugin_repo import PluginRepo

        _plugin_repo = PluginRepo()
    return _plugin_repo


@app.get("/api/plugins/search")
async def plugin_search(query: str = "", max_results: int = 20) -> dict[str, Any]:
    repo = _get_plugin_repo()
    result = repo.search_github(query=query, max_results=max_results)
    return {
        "plugins": [
            {
                "name": p.name,
                "version": p.version,
                "description": p.description,
                "author": p.author,
                "source_url": p.source_url,
                "installed": p.installed,
            }
            for p in result.plugins
        ],
        "total": result.total,
        "error": result.error,
    }


@app.post("/api/plugins/install-git")
async def plugin_install_git(body: dict[str, Any]) -> dict[str, Any]:
    repo = _get_plugin_repo()
    ok, msg = repo.install_from_git(
        url=body.get("url", ""),
        branch=body.get("branch", "main"),
        target_name=body.get("name", ""),
    )
    return {"success": ok, "message": msg}


@app.post("/api/plugins/uninstall")
async def plugin_uninstall(body: dict[str, Any]) -> dict[str, Any]:
    repo = _get_plugin_repo()
    ok, msg = repo.uninstall(body.get("name", ""))
    return {"success": ok, "message": msg}


# ── DAG API ──


@app.get("/api/dag/nodes")
async def dag_list_nodes() -> dict[str, Any]:
    from core.task_dag import TaskDAG

    dag = TaskDAG()
    nodes = dag.list_nodes()
    return {
        "nodes": [
            {
                "id": n.id,
                "depends_on": n.depends_on,
                "description": n.description,
                "metadata": n.metadata,
            }
            for n in nodes
        ],
        "total": len(nodes),
        "has_cycle": dag.detect_cycle() is not None,
    }


@app.post("/api/dag/nodes")
async def dag_add_node(body: dict[str, Any]) -> dict[str, Any]:
    from core.task_dag import TaskDAG

    dag = TaskDAG()
    node = dag.add_node(
        body["id"],
        depends_on=body.get("depends_on", []),
        description=body.get("description", ""),
        metadata=body.get("metadata", {}),
    )
    dag.save()
    return {
        "success": True,
        "node": {
            "id": node.id,
            "depends_on": node.depends_on,
            "description": node.description,
        },
    }


@app.put("/api/dag/nodes/{node_id}")
async def dag_update_node(node_id: str, body: dict[str, Any]) -> dict[str, Any]:
    from core.task_dag import TaskDAG

    dag = TaskDAG()
    existing = dag.get_node(node_id)
    if not existing:
        return {"success": False, "error": f"节点 {node_id} 未找到"}
    node = dag.add_node(
        node_id,
        depends_on=body.get("depends_on", existing.depends_on),
        description=body.get("description", existing.description),
        metadata=body.get("metadata", existing.metadata),
    )
    dag.save()
    return {
        "success": True,
        "node": {
            "id": node.id,
            "depends_on": node.depends_on,
            "description": node.description,
        },
    }


@app.delete("/api/dag/nodes/{node_id}")
async def dag_delete_node(node_id: str) -> dict[str, Any]:
    from core.task_dag import TaskDAG

    dag = TaskDAG()
    ok = dag.remove_node(node_id)
    if ok:
        dag.save()
    return {"success": ok}


@app.post("/api/dag/auto-layout")
async def dag_auto_layout() -> dict[str, Any]:
    from core.task_dag import TaskDAG

    dag = TaskDAG()
    plan = dag.execution_plan()
    nodes = dag.list_nodes()
    layout = {}
    y_offset = 80
    for layer_idx, layer in enumerate(plan):
        x_offset = 60
        for node_id in layer:
            layout[node_id] = {"x": x_offset, "y": y_offset}
            x_offset += 220
        y_offset += 120
    return {"layout": layout, "layers": plan}


@app.get("/api/dag/plan")
async def dag_plan() -> dict[str, Any]:
    from core.task_dag import TaskDAG

    dag = TaskDAG()
    try:
        plan = dag.execution_plan()
    except ValueError as e:
        return {"error": str(e), "plan": []}
    return {"plan": plan, "total_layers": len(plan)}


# ── Gantt ──


@app.get("/api/gantt")
async def gantt_data(max_bars: int = 50) -> dict[str, Any]:
    from core.gantt import GanttFormatter, GanttGenerator

    gen = GanttGenerator()
    try:
        from core.scheduler import Scheduler

        sched = Scheduler()
        jobs = sched.list_jobs()
        sched_data = {
            jid: {"cron": j.cron, "task_type": j.task_type, "enabled": j.enabled}
            for jid, j in jobs.items()
        }
    except Exception:
        sched_data = {}
    try:
        from core.harness import Harness

        h = Harness()
        agg = h.aggregate()
    except Exception:
        agg = None
    gantt = gen.generate(
        harness_aggregate=agg, scheduler_jobs=sched_data, since=time.time() - 3600
    )
    chart = GanttFormatter.to_chart_data(gantt, max_bars=max_bars)
    return chart


@app.get("/api/tasks/retry")
async def retry_status() -> dict[str, Any]:
    cfg = get_config().task
    active = {}
    try:
        from core.harness import Harness

        h = Harness()
        mgr = getattr(h, "_retry_mgr", None)
        if mgr:
            active = mgr.retry_summary()
    except Exception:
        pass
    return {
        "config": {
            "retry_enabled": cfg.retry_enabled,
            "retry_max_attempts": cfg.retry_max_attempts,
            "retry_base_delay": cfg.retry_base_delay,
            "retry_max_delay": cfg.retry_max_delay,
            "retry_jitter": cfg.retry_jitter,
            "max_reallocate": cfg.max_reallocate,
        },
        "active_retries": active,
    }


# ── DAG 模板 ──


@app.get("/api/dag-templates")
async def dag_templates_list(category: str = "") -> dict[str, Any]:
    from core.dag_templates import list_categories, list_templates

    cat = category or None
    return {
        "categories": list_categories(),
        "templates": list_templates(cat),
    }


@app.get("/api/dag-templates/{template_id}")
async def dag_templates_get(template_id: str) -> dict[str, Any]:
    from core.dag_templates import get_template

    t = get_template(template_id)
    if t is None:
        return {"error": "模板不存在"}
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "category": t.category,
        "nodes": t.nodes,
    }


@app.post("/api/dag-templates/{template_id}/apply")
async def dag_templates_apply(template_id: str) -> dict[str, Any]:
    from core.dag_templates import apply_template

    try:
        dag = apply_template(template_id, clear_existing=True)
        return {
            "ok": True,
            "node_count": len(dag.list_nodes()),
            "topological_order": dag.topological_sort(),
        }
    except ValueError as e:
        return {"error": str(e)}


# ── 审计日志 ──


@app.get("/api/audit")
async def audit_query(
    task_id: str = "",
    action: str = "",
    agent: str = "",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    from core.audit import get_audit_log

    log = get_audit_log()
    entries = log.query(
        task_id=task_id or None,
        action=action or None,
        agent=agent or None,
        limit=min(limit, 500),
        offset=offset,
    )
    summary = log.summary()
    return {"entries": entries, "summary": summary}


# ── 告警 ──


@app.get("/api/alerts/rules")
async def alert_rules() -> dict[str, Any]:
    from core.alert import get_alert_engine

    return {"rules": get_alert_engine().list_rules()}


@app.post("/api/alerts/rules")
async def alert_add_rule(request: Request) -> dict[str, Any]:
    from core.alert import AlertRule, get_alert_engine

    body = await request.json()
    rule = AlertRule(**body)
    get_alert_engine().add_rule(rule)
    return {"ok": True, "rule_id": rule.id}


@app.delete("/api/alerts/rules/{rule_id}")
async def alert_remove_rule(rule_id: str) -> dict[str, Any]:
    from core.alert import get_alert_engine

    ok = get_alert_engine().remove_rule(rule_id)
    return {"ok": ok}


@app.get("/api/alerts/events")
async def alert_events(limit: int = 50) -> dict[str, Any]:
    from core.alert import get_alert_engine

    return {"events": get_alert_engine().recent_alerts(limit=min(limit, 200))}


@app.post("/api/alerts/acknowledge/{rule_id}")
async def alert_acknowledge(rule_id: str) -> dict[str, Any]:
    from core.alert import get_alert_engine

    get_alert_engine().acknowledge(rule_id)
    return {"ok": True}


# ── Agent 市场 ──


@app.post("/api/agents/refresh")
async def agent_refresh() -> dict[str, Any]:
    from core.agent_market import get_market

    get_market().refresh_from_registry()
    return {"ok": True}


@app.get("/api/agents/stats/all")
async def agent_stats_all() -> dict[str, Any]:
    from core.agent_market import get_market
    from core.audit import get_audit_log

    m = get_market()
    log = get_audit_log()
    agents = m.list_agents()
    stats = {}
    for a in agents:
        try:
            entries = log.query(agent=a["name"], limit=500)
            total = len(entries)
            success = sum(
                1 for e in entries if e.get("action") in ("completed", "success")
            )
            failed = sum(1 for e in entries if e.get("action") in ("failed", "error"))
            durations = [
                e.get("duration_ms", 0) for e in entries if e.get("duration_ms")
            ]
            avg_dur = round(sum(durations) / len(durations), 1) if durations else 0
            last = max((e.get("ts", 0) for e in entries), default=0)
            stats[a["name"]] = {
                "total_tasks": total,
                "success": success,
                "failed": failed,
                "avg_duration_ms": avg_dur,
                "last_active": last,
            }
        except Exception:
            stats[a["name"]] = {
                "total_tasks": 0,
                "success": 0,
                "failed": 0,
                "avg_duration_ms": 0,
                "last_active": 0,
            }
    return {"stats": stats}


@app.get("/api/vector/stats")
async def vector_stats() -> dict[str, Any]:
    """向量库各层统计。"""
    return vector_browser.layer_stats()


@app.get("/api/vector/layers/{scope:str}")
async def vector_layer(
    scope: str, sub_id: str = "", offset: int = 0, limit: int = 50
) -> dict[str, Any]:
    """浏览指定层的文档。"""
    return vector_browser.list_documents(scope, sub_id, offset, limit)


@app.get("/api/vector/search")
async def vector_search(q: str = "", top_k: int = 3) -> dict[str, Any]:
    """跨层搜索。"""
    results = vector_browser.search_all(q, top_k_per_layer=top_k) if q else []
    return {"query": q, "results": results, "total": len(results)}


@app.get("/api/vector/doc/{scope}/{sub_id}/{doc_id}")
async def vector_doc(scope: str, sub_id: str, doc_id: str) -> dict[str, Any]:
    """文档详情 + 相似文档。"""
    doc = vector_browser.get_document(scope, sub_id, doc_id)
    if doc is None:
        return {"found": False}
    similar = vector_browser.similar_to(doc_id, scope, sub_id)
    return {"found": True, "doc": doc, "similar": similar}


@app.get("/api/status")
async def get_status() -> dict[str, Any]:
    """获取全场景状态。"""
    return {
        "scene": scene.status(),
        "github": github.stats(),
        "config": {
            "environment": get_config().environment.value,
            "use_real_api": get_config().use_real_api,
        },
    }


@app.get("/api/scene")
async def get_scene() -> dict[str, Any]:
    """获取全场景数据。"""
    return scene.to_dict()


@app.get("/api/jarvis")
async def jarvis_query(q: str = "") -> dict[str, Any]:
    """JARVIS 智能助手接口。"""
    if not q:
        return {"text": "请输入你的问题", "intent": "unknown", "success": True}
    response = jarvis.process(q)
    return {
        "text": response.text,
        "intent": response.intent.value,
        "success": response.success,
        "data": response.data,
        "processing_time": round(response.processing_time, 3),
    }


@app.get("/api/github")
async def get_github_projects(category: str = "") -> dict[str, Any]:
    """获取 GitHub 项目。"""
    if category:
        from core.github_knowledge import ProjectCategory

        try:
            cat = ProjectCategory(category)
            projects = github.get_by_category(cat)
        except ValueError:
            projects = []
    else:
        projects = list(github._projects.values())
    return {
        "projects": [
            {
                "name": p.name,
                "description": p.description,
                "category": p.category.value,
                "tags": p.tags,
                "key_insights": p.key_insights,
            }
            for p in projects
        ],
        "total": len(projects),
    }


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> str:
    """2.5D 平面图仪表盘页面。"""
    status = scene.status()
    offices_data = scene.office_manager.to_dict()
    github_data = github.stats()
    announcements = scene.breakroom.recent(count=5, msg_type=None)

    html = (
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BlueDeer 森林公司 · 平面图</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body {
    font-family: 'Segoe UI','Microsoft YaHei',system-ui,sans-serif;
    background: #0d1a12;
    color: #d8f0d8;
    min-height: 100vh;
    overflow-x: auto;
}

/* ===== 全局动画 ===== */
@keyframes floatSteam {
    0% { transform: translateY(0) scale(1); opacity: 0.7; }
    50% { transform: translateY(-16px) scale(1.3); opacity: 0.4; }
    100% { transform: translateY(-32px) scale(1.7); opacity: 0; }
}
@keyframes breathe {
    0%,100% { opacity: 0.35; }
    50% { opacity: 0.9; }
}
@keyframes screenGlow {
    0%,100% { filter: brightness(0.9); }
    50% { filter: brightness(1.3); }
}
@keyframes swim {
    0% { transform: translateX(0) translateY(0); }
    25% { transform: translateX(60px) translateY(-4px); }
    50% { transform: translateX(120px) translateY(0); }
    75% { transform: translateX(60px) translateY(4px); }
    100% { transform: translateX(0) translateY(0); }
}
@keyframes waterRipple {
    0%,100% { transform: scale(0.7); opacity: 0.25; }
    50% { transform: scale(1.3); opacity: 0.6; }
}
@keyframes sunbeam {
    0% { transform: translateX(-40px) rotate(25deg); opacity: 0.15; }
    50% { transform: translateX(0) rotate(25deg); opacity: 0.3; }
    100% { transform: translateX(40px) rotate(25deg); opacity: 0.15; }
}
@keyframes statusPulse {
    0%,100% { box-shadow: 0 0 4px #4caf50; }
    50% { box-shadow: 0 0 14px #76ff03; }
}
@keyframes flicker {
    0%,100% { opacity: 0.75; }
    50% { opacity: 0.95; }
}
@keyframes floatCloud {
    0%,100% { transform: translateX(0); }
    50% { transform: translateX(15px); }
}
@keyframes sway {
    0%,100% { transform: rotate(-2deg); }
    50% { transform: rotate(2deg); }
}
@keyframes leafFall {
    0% { transform: translateY(0) rotate(0); opacity: 0.8; }
    100% { transform: translateY(30px) rotate(45deg); opacity: 0; }
}

.header {
    background: linear-gradient(135deg,#1b3a1e,#2e5a35);
    padding: 18px 30px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 2px solid #4caf50;
    position: sticky;
    top: 0;
    z-index: 1000;
}
.header h1 { font-size: 24px; color: #e8f5e9; letter-spacing: 2px; }
.header .subtitle { font-size: 12px; color: #a5d6a7; margin-top: 4px; }
.header .stats-mini {
    display: flex;
    gap: 20px;
    font-size: 12px;
}
.header .stats-mini span { color: #c8e6c9; }
.header .stats-mini b { color: #81c784; margin-right: 4px; }

.floorplan-wrapper {
    padding: 30px;
    min-width: 1200px;
}
.floorplan {
    position: relative;
    width: 1140px;
    height: 800px;
    margin: 0 auto;
    background:
        repeating-linear-gradient(90deg, rgba(0,0,0,0.05) 0 1px, transparent 1px 40px),
        repeating-linear-gradient(0deg, rgba(0,0,0,0.05) 0 1px, transparent 1px 40px),
        linear-gradient(135deg, #d7ccc8 0%, #bcaaa4 100%);
    border: 8px solid #5d4037;
    border-radius: 8px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.6), inset 0 0 120px rgba(0,0,0,0.15);
    overflow: hidden;
}

/* 墙体 */
.wall {
    position: absolute;
    background: #4e342e;
    box-shadow: inset 0 0 10px rgba(0,0,0,0.3);
}
.wall-h { height: 8px; }
.wall-v { width: 8px; }

/* 窗户阳光 */
.window-light {
    position: absolute;
    width: 220px;
    height: 500px;
    background: linear-gradient(90deg, rgba(255,248,220,0) 0%, rgba(255,248,220,0.18) 50%, rgba(255,248,220,0) 100%);
    transform: rotate(25deg);
    filter: blur(10px);
    animation: sunbeam 10s ease-in-out infinite;
    pointer-events: none;
    z-index: 5;
}

/* 房间区域 */
.room {
    position: absolute;
    border: 2px dashed rgba(93,64,55,0.25);
    transition: all 0.25s ease;
    cursor: pointer;
}
.room:hover {
    background: rgba(76,175,80,0.06);
    border-color: rgba(76,175,80,0.5);
    box-shadow: inset 0 0 30px rgba(76,175,80,0.1);
}
.room-label {
    position: absolute;
    font-size: 13px;
    font-weight: 700;
    color: #3e2723;
    text-shadow: 0 1px 0 rgba(255,255,255,0.4);
    pointer-events: none;
    letter-spacing: 1px;
    z-index: 20;
}
.room-icon {
    font-size: 22px;
    margin-right: 6px;
}

/* ==================== 资料库 Library ==================== */
#library { left: 30px; top: 30px; width: 260px; height: 240px; background: #efebe9; }

/* 三面书墙 */
.book-wall {
    position: absolute;
    background: #5d4037;
    border-radius: 3px;
    box-shadow: 3px 3px 0 rgba(0,0,0,0.12);
}
.book-wall-left {
    left: 12px; top: 35px;
    width: 55px; height: 175px;
}
.book-wall-back {
    left: 72px; top: 35px;
    width: 130px; height: 45px;
}
.book-wall-right {
    right: 12px; top: 35px;
    width: 40px; height: 120px;
}

/* 彩色书脊 */
.books {
    position: absolute;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 4px;
}
.book-spine {
    width: 100%;
    height: 14px;
    border-radius: 1px;
    border-left: 3px solid rgba(255,255,255,0.3);
    position: relative;
}
.book-spine::after {
    content: "";
    position: absolute;
    left: 50%; top: 50%;
    transform: translate(-50%, -50%);
    width: 40%; height: 2px;
    background: rgba(255,255,255,0.25);
}

/* 阅读区大桌 */
.reading-table {
    position: absolute;
    right: 22px; bottom: 28px;
    width: 110px; height: 75px;
    background: #8d6e63;
    border-radius: 4px;
    box-shadow: 5px 5px 0 rgba(0,0,0,0.15);
}
.reading-table::before {
    content: "";
    position: absolute;
    left: 8px; top: -6px;
    width: 94px; height: 12px;
    background: #a1887f;
    border-radius: 2px;
}
.reading-table::after {
    content: "";
    position: absolute;
    left: 35px; top: -26px;
    width: 24px; height: 24px;
    background: #fff9c4;
    border-radius: 50%;
    box-shadow: 0 0 25px #fff59d;
    animation: flicker 3s ease-in-out infinite;
}

/* 桌上物品 */
.open-book {
    position: absolute;
    left: 12px; top: 18px;
    width: 34px; height: 24px;
    background: #fff;
    border-radius: 2px;
    box-shadow: 1px 1px 3px rgba(0,0,0,0.1);
}
.open-book::before {
    content: "";
    position: absolute;
    left: 50%; top: 2px; bottom: 2px;
    width: 1px;
    background: #d7ccc8;
}
.glasses {
    position: absolute;
    right: 14px; top: 22px;
    width: 22px; height: 8px;
    border: 2px solid #424242;
    border-radius: 8px;
}
.globe {
    position: absolute;
    left: 55px; top: 10px;
    width: 18px; height: 18px;
    background: radial-gradient(circle at 30% 30%, #4fc3f7, #0277bd);
    border-radius: 50%;
    border: 2px solid #6d4c41;
}
.globe::after {
    content: "";
    position: absolute;
    left: 50%; bottom: -8px;
    transform: translateX(-50%);
    width: 4px; height: 10px;
    background: #6d4c41;
}

/* 梯子和分类标签 */
.ladder {
    position: absolute;
    left: 75px; top: 90px;
    width: 8px; height: 120px;
    background: #6d4c41;
    transform: rotate(10deg);
}
.ladder::before {
    content: "";
    position: absolute;
    left: -12px; top: 0; bottom: 0;
    width: 32px;
    background: repeating-linear-gradient(0deg, transparent 0 22px, #6d4c41 22px 26px);
}
.shelf-label {
    position: absolute;
    font-size: 8px;
    color: #5d4037;
    background: #fff9c4;
    padding: 1px 4px;
    border-radius: 2px;
    font-weight: 700;
}

/* 知识树挂画 */
.knowledge-tree {
    position: absolute;
    right: 18px; top: 45px;
    width: 55px; height: 70px;
    background: #fff;
    border: 3px solid #6d4c41;
    border-radius: 3px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 28px;
    box-shadow: 2px 2px 0 rgba(0,0,0,0.1);
}
.knowledge-tree::before {
    content: "知识树";
    position: absolute;
    bottom: 3px;
    font-size: 8px;
    color: #5d4037;
}

/* 盆栽 */
.pot-plant {
    position: absolute;
    font-size: 22px;
    line-height: 1;
    animation: sway 4s ease-in-out infinite;
}

/* ==================== 总经理办公室 CEO ==================== */
#ceo { right: 30px; top: 30px; width: 380px; height: 240px; background: #efebe9; }
#ceo .ceo-desk {
    position: absolute;
    right: 45px; top: 65px;
    width: 170px; height: 95px;
    background: #6d4c41;
    border-radius: 4px;
    box-shadow: 6px 6px 0 rgba(0,0,0,0.15);
}
#ceo .ceo-desk::before {
    content: "";
    position: absolute;
    left: 25px; top: 18px;
    width: 90px; height: 55px;
    background: #263238;
    border-radius: 3px;
    animation: screenGlow 4s ease-in-out infinite;
}
#ceo .ceo-desk::after {
    content: "";
    position: absolute;
    right: 12px; top: 25px;
    width: 28px; height: 40px;
    background: #fff;
    border-radius: 2px;
    box-shadow: 1px 1px 3px rgba(0,0,0,0.15);
}
#ceo .ceo-chair {
    position: absolute;
    right: 110px; bottom: 28px;
    width: 55px; height: 55px;
    background: #3e2723;
    border-radius: 50% 50% 10px 10px;
    box-shadow: 3px 3px 0 rgba(0,0,0,0.15);
}
#ceo .deer-badge {
    position: absolute;
    left: 25px; top: 50px;
    width: 70px; height: 90px;
    background: #fff;
    border: 2px solid #5d4037;
    border-radius: 6px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    font-size: 28px;
    box-shadow: 3px 3px 0 rgba(0,0,0,0.1);
}
#ceo .deer-badge::after {
    content: "总经理";
    font-size: 11px;
    color: #5d4037;
    margin-top: 4px;
    font-weight: 700;
}
#ceo .window {
    position: absolute;
    right: 0; top: 25px;
    width: 16px; height: 150px;
    background: linear-gradient(180deg, #b3e5fc, #81d4fa);
    border-left: 3px solid #5d4037;
}
#ceo .window::before {
    content: "🌲";
    position: absolute;
    right: 4px; top: 25px;
    font-size: 16px;
    opacity: 0.7;
}
#ceo .window::after {
    content: "☁️";
    position: absolute;
    right: 2px; top: 60px;
    font-size: 12px;
    opacity: 0.6;
    animation: floatCloud 8s ease-in-out infinite;
}
#ceo .bookshelf-small {
    position: absolute;
    left: 115px; top: 60px;
    width: 55px; height: 90px;
    background: #5d4037;
    border-radius: 3px;
}
#ceo .bookshelf-small::before {
    content: "";
    position: absolute;
    left: 3px; top: 6px; right: 3px; bottom: 6px;
    background: repeating-linear-gradient(0deg, #8d6e63 0 5px, #5d4037 5px 8px, #a1887f 8px 13px, #4e342e 13px 18px);
}
#ceo .trophy {
    position: absolute;
    left: 130px; top: 42px;
    font-size: 20px;
}
#ceo .strategy-board {
    position: absolute;
    left: 190px; top: 12px;
    width: 90px; height: 55px;
    background: #fff;
    border: 3px solid #6d4c41;
    border-radius: 3px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    box-shadow: 2px 2px 0 rgba(0,0,0,0.1);
}
#ceo .strategy-board::after {
    content: "战略图";
    position: absolute;
    bottom: 2px;
    font-size: 8px;
    color: #5d4037;
}

/* ==================== 开放办公区 ==================== */
#office-area { left: 30px; top: 300px; width: 700px; height: 320px; background: #d7ccc8; }
.desk {
    position: absolute;
    width: 120px; height: 85px;
    background: #a1887f;
    border-radius: 4px;
    box-shadow: 4px 4px 0 rgba(0,0,0,0.12);
    cursor: pointer;
    transition: transform 0.2s;
}
.desk:hover { transform: translateY(-3px); z-index: 50; }
.desk-top {
    position: absolute;
    left: 8px; top: -10px;
    width: 104px; height: 55px;
    background: #8d6e63;
    border-radius: 3px;
}
.monitor {
    position: absolute;
    left: 22px; top: -40px;
    width: 55px; height: 35px;
    background: #263238;
    border-radius: 3px;
    border: 2px solid #455a64;
    overflow: hidden;
    animation: screenGlow 3s ease-in-out infinite;
}
.monitor::after {
    content: "</>";
    position: absolute;
    left: 10px; top: 9px;
    font-size: 11px;
    color: #69f0ae;
    font-family: monospace;
}
.keyboard {
    position: absolute;
    left: 20px; top: 12px;
    width: 60px; height: 15px;
    background: #5d4037;
    border-radius: 2px;
}
.mouse {
    position: absolute;
    right: 14px; top: 14px;
    width: 11px; height: 15px;
    background: #5d4037;
    border-radius: 50%;
}
.cup {
    position: absolute;
    right: 12px; bottom: 12px;
    width: 13px; height: 15px;
    background: #fff;
    border-radius: 0 0 6px 6px;
    border: 1px solid #d7ccc8;
}
.cup::before {
    content: "";
    position: absolute;
    right: -5px; top: 2px;
    width: 6px; height: 8px;
    border: 2px solid #fff;
    border-radius: 0 6px 6px 0;
    border-left: none;
}
.steam {
    position: absolute;
    right: 14px; bottom: 26px;
    width: 6px; height: 10px;
    background: rgba(255,255,255,0.6);
    border-radius: 50%;
    animation: floatSteam 2.5s ease-out infinite;
}
.steam:nth-child(2) { animation-delay: 0.6s; }
.steam:nth-child(3) { animation-delay: 1.2s; }
.plant {
    position: absolute;
    left: 10px; bottom: 8px;
    width: 18px; height: 26px;
    font-size: 20px;
    line-height: 1;
}
.chair {
    position: absolute;
    width: 38px; height: 38px;
    background: #5d4037;
    border-radius: 50%;
    box-shadow: 2px 2px 0 rgba(0,0,0,0.12);
}
.employee-name {
    position: absolute;
    left: 50%;
    bottom: -22px;
    transform: translateX(-50%);
    font-size: 11px;
    color: #3e2723;
    font-weight: 700;
    white-space: nowrap;
    text-shadow: 0 1px 0 rgba(255,255,255,0.5);
}
.status-dot {
    position: absolute;
    right: 6px; top: -55px;
    width: 8px; height: 8px;
    background: #4caf50;
    border-radius: 50%;
    animation: statusPulse 2s ease-in-out infinite;
}
.status-dot.busy { background: #ff9100; }
.status-dot.idle { background: #9e9e9e; }
.headphones {
    position: absolute;
    left: 8px; top: -6px;
    font-size: 16px;
}
.phone {
    position: absolute;
    right: 32px; top: 18px;
    width: 10px; height: 16px;
    background: #37474f;
    border-radius: 2px;
}
.sticky-note {
    position: absolute;
    right: 2px; top: -32px;
    width: 14px; height: 14px;
    background: #fff59d;
    border-radius: 1px;
    transform: rotate(8deg);
    box-shadow: 1px 1px 2px rgba(0,0,0,0.1);
}
.photo-frame {
    position: absolute;
    left: 4px; top: -34px;
    width: 14px; height: 16px;
    background: #6d4c41;
    border-radius: 1px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 9px;
}

/* ==================== 茶水间 ==================== */
#breakroom { left: 30px; top: 650px; width: 360px; height: 120px; background: #efebe9; }
#breakroom .counter {
    position: absolute;
    left: 15px; top: 15px;
    width: 170px; height: 58px;
    background: #8d6e63;
    border-radius: 4px;
    box-shadow: 4px 4px 0 rgba(0,0,0,0.12);
}
.coffee-machine {
    position: absolute;
    left: 20px; top: -22px;
    width: 34px; height: 34px;
    background: #424242;
    border-radius: 4px;
}
.coffee-machine::after {
    content: "☕";
    position: absolute;
    left: 5px; top: 5px;
    font-size: 18px;
}
.microwave {
    position: absolute;
    left: 62px; top: -16px;
    width: 36px; height: 24px;
    background: #bdbdbd;
    border-radius: 3px;
    border: 2px solid #757575;
}
.microwave::after {
    content: "";
    position: absolute;
    right: 4px; top: 4px;
    width: 20px; height: 12px;
    background: #424242;
    border-radius: 1px;
}
.water-dispenser {
    position: absolute;
    left: 110px; top: -28px;
    width: 22px; height: 42px;
    background: #4fc3f7;
    border-radius: 3px;
    border: 2px solid #0277bd;
}
.water-dispenser::after {
    content: "";
    position: absolute;
    left: 50%; top: 8px;
    transform: translateX(-50%);
    width: 10px; height: 10px;
    background: #fff;
    border-radius: 50%;
}
.stool {
    position: absolute;
    width: 22px; height: 22px;
    background: #5d4037;
    border-radius: 50%;
    box-shadow: 2px 2px 0 rgba(0,0,0,0.1);
}
.notice-board {
    position: absolute;
    right: 18px; top: 12px;
    width: 130px; height: 75px;
    background: #d7ccc8;
    border: 3px solid #6d4c41;
    border-radius: 4px;
    box-shadow: 3px 3px 0 rgba(0,0,0,0.1);
    display: flex;
    flex-wrap: wrap;
    padding: 5px;
    gap: 5px;
}
.notice-board::before {
    content: "公告";
    position: absolute;
    top: -12px; left: 8px;
    background: #5d4037;
    color: #fff;
    font-size: 9px;
    padding: 1px 6px;
    border-radius: 2px;
}
.notice-paper {
    width: 22px; height: 26px;
    background: #fff;
    border: 1px solid #bcaaa4;
}
.notice-paper:nth-child(2) { background: #fff9c4; transform: rotate(-3deg); }
.notice-paper:nth-child(3) { background: #ffccbc; transform: rotate(2deg); }
.notice-paper:nth-child(4) { background: #c8e6c9; transform: rotate(-1deg); }
.fruit-bowl {
    position: absolute;
    right: 160px; top: 36px;
    width: 24px; height: 16px;
    background: #ff7043;
    border-radius: 0 0 12px 12px;
}
.fruit-bowl::before {
    content: "🍎";
    position: absolute;
    left: 3px; top: -10px;
    font-size: 12px;
}
.fruit-bowl::after {
    content: "🍌";
    position: absolute;
    right: 2px; top: -8px;
    font-size: 10px;
}
.clock {
    position: absolute;
    right: 160px; top: 10px;
    width: 20px; height: 20px;
    background: #fff;
    border: 2px solid #5d4037;
    border-radius: 50%;
}
.clock::after {
    content: "";
    position: absolute;
    left: 50%; top: 4px;
    width: 1px; height: 6px;
    background: #5d4037;
    transform-origin: bottom;
}

/* ==================== 休息区 ==================== */
#restarea { right: 30px; top: 650px; width: 360px; height: 120px; background: #efebe9; }
.sofa {
    position: absolute;
    left: 20px; top: 30px;
    width: 120px; height: 55px;
    background: #5d4037;
    border-radius: 14px;
    box-shadow: 4px 4px 0 rgba(0,0,0,0.12);
}
.sofa::before {
    content: "";
    position: absolute;
    left: -10px; top: 10px;
    width: 16px; height: 38px;
    background: #4e342e;
    border-radius: 10px;
}
.sofa::after {
    content: "";
    position: absolute;
    right: -10px; top: 10px;
    width: 16px; height: 38px;
    background: #4e342e;
    border-radius: 10px;
}
.pillow {
    position: absolute;
    left: 22px; top: 12px;
    width: 26px; height: 26px;
    background: #ffab91;
    border-radius: 5px;
}
.coffee-table {
    position: absolute;
    left: 155px; top: 55px;
    width: 55px; height: 35px;
    background: #8d6e63;
    border-radius: 4px;
    box-shadow: 3px 3px 0 rgba(0,0,0,0.1);
}
.coffee-table::before {
    content: "";
    position: absolute;
    left: 8px; top: 6px;
    width: 18px; height: 12px;
    background: #fff;
    border-radius: 0 0 8px 8px;
}
.coffee-table::after {
    content: "📓";
    position: absolute;
    right: 6px; top: 4px;
    font-size: 12px;
}
.fish-tank {
    position: absolute;
    right: 22px; top: 22px;
    width: 95px; height: 58px;
    background: linear-gradient(180deg, #b3e5fc 0%, #4fc3f7 100%);
    border: 3px solid #6d4c41;
    border-radius: 4px;
    overflow: hidden;
    box-shadow: 3px 3px 0 rgba(0,0,0,0.1);
}
.fish {
    position: absolute;
    top: 24px; left: 10px;
    width: 20px; height: 11px;
    background: #ff7043;
    border-radius: 50% 50% 40% 40%;
    animation: swim 7s ease-in-out infinite alternate;
}
.fish::after {
    content: "";
    position: absolute;
    right: -5px; top: 2px;
    width: 0; height: 0;
    border-top: 3px solid transparent;
    border-bottom: 3px solid transparent;
    border-left: 7px solid #ff7043;
}
.ripple {
    position: absolute;
    width: 34px; height: 8px;
    border: 1px solid rgba(255,255,255,0.5);
    border-radius: 50%;
    animation: waterRipple 2.2s ease-in-out infinite;
}
.ripple:nth-child(2) { top: 10px; left: 30px; animation-delay: 0.5s; }
.ripple:nth-child(3) { top: 36px; left: 55px; animation-delay: 1s; }
.floor-lamp {
    position: absolute;
    right: 135px; top: 14px;
    width: 8px; height: 75px;
    background: #5d4037;
}
.floor-lamp::before {
    content: "";
    position: absolute;
    left: -14px; top: -10px;
    width: 36px; height: 22px;
    background: #fff9c4;
    border-radius: 10px 10px 0 0;
    box-shadow: 0 0 28px #fff59d;
    animation: flicker 4s ease-in-out infinite;
}
.dream-wall {
    position: absolute;
    left: 220px; top: 12px;
    width: 55px; height: 40px;
    background: #d7ccc8;
    border: 2px solid #6d4c41;
    border-radius: 2px;
    display: flex;
    flex-wrap: wrap;
    align-content: flex-start;
    padding: 3px;
    gap: 3px;
}
.dream-photo {
    width: 12px; height: 14px;
    background: #fff;
    border: 1px solid #8d6e63;
}
.dream-photo:nth-child(1) { background: #c8e6c9; }
.dream-photo:nth-child(2) { background: #fff9c4; }
.dream-photo:nth-child(3) { background: #ffccbc; }
.dream-photo:nth-child(4) { background: #b3e5fc; }

/* 信息面板 */
.info-panel {
    position: fixed;
    right: 30px;
    top: 110px;
    width: 320px;
    background: rgba(13,26,18,0.95);
    border: 1px solid #4caf50;
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 10px 40px rgba(0,0,0,0.5);
    backdrop-filter: blur(10px);
    z-index: 2000;
    max-height: calc(100vh - 140px);
    overflow-y: auto;
}
.info-panel h3 {
    color: #81c784;
    font-size: 16px;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid #2e7d32;
}
.info-panel p, .info-panel li {
    font-size: 13px;
    color: #c8e6c9;
    line-height: 1.7;
}
.info-panel ul { padding-left: 18px; margin: 8px 0; }
.info-panel .close-btn {
    position: absolute;
    right: 12px; top: 12px;
    width: 24px; height: 24px;
    background: #2e7d32;
    border: none;
    border-radius: 50%;
    color: #fff;
    cursor: pointer;
    font-size: 14px;
}
.info-panel .close-btn:hover { background: #4caf50; }

.footer-tip {
    text-align: center;
    padding: 16px;
    color: #6a8a6b;
    font-size: 12px;
}

.rug {
    position: absolute;
    left: 50%; top: 50%;
    transform: translate(-50%, -50%);
    width: 85%; height: 85%;
    background: repeating-linear-gradient(
        45deg,
        rgba(93,64,55,0.06) 0 10px,
        transparent 10px 20px
    );
    border-radius: 8px;
    pointer-events: none;
}

.door {
    position: absolute;
    width: 32px; height: 6px;
    background: #6d4c41;
    border-radius: 3px;
}
.door::after {
    content: "";
    position: absolute;
    right: 4px; top: -2px;
    width: 4px; height: 4px;
    background: #ffd54f;
    border-radius: 50%;
}

.cabinet {
    position: absolute;
    width: 45px; height: 55px;
    background: #8d6e63;
    border-radius: 3px;
    box-shadow: 3px 3px 0 rgba(0,0,0,0.1);
}
.cabinet::before {
    content: "";
    position: absolute;
    left: 5px; top: 5px; right: 5px; bottom: 5px;
    border: 1px solid rgba(0,0,0,0.1);
}
.cabinet::after {
    content: "";
    position: absolute;
    left: 50%; top: 8px; bottom: 8px;
    width: 1px;
    background: rgba(0,0,0,0.15);
}
</style>
</head>
<body>
<div class="header">
    <div>
        <h1>🦌 BlueDeer 森林公司</h1>
        <div class="subtitle">2.5D 平面户型图 · 点击房间查看详情</div>
    </div>
    <div class="stats-mini">
        <span><b>"""
        + str(status["library"]["total_entries"])
        + """</b>资料库</span>
        <span><b>"""
        + str(status["breakroom"]["total_messages"])
        + """</b>茶水间</span>
        <span><b>"""
        + str(status["offices"]["total_offices"])
        + """</b>办公室</span>
        <span><b>"""
        + str(github_data["total_projects"])
        + """</b>GitHub项目</span>
    </div>
</div>

<div class="floorplan-wrapper">
    <div class="floorplan">
        <!-- 阳光 -->
        <div class="window-light" style="top:-80px;right:80px;"></div>
        <div class="window-light" style="top:-80px;left:60px;animation-delay:3s;"></div>

        <!-- 资料库 -->
        <div class="room" id="library" onclick="showRoom('library')">
            <div class="room-label" style="left:15px;top:12px;"><span class="room-icon">📚</span>资料库</div>
            
            <!-- 三面书墙 -->
            <div class="book-wall book-wall-left">
                <div class="books" style="top:8px;left:4px;right:4px;">
                    <div class="book-spine" style="background:#8d6e63;"></div>
                    <div class="book-spine" style="background:#5d4037;"></div>
                    <div class="book-spine" style="background:#a1887f;"></div>
                    <div class="book-spine" style="background:#4e342e;"></div>
                    <div class="book-spine" style="background:#bcaaa4;"></div>
                    <div class="book-spine" style="background:#6d4c41;"></div>
                    <div class="book-spine" style="background:#795548;"></div>
                    <div class="book-spine" style="background:#8d6e63;"></div>
                    <div class="book-spine" style="background:#5d4037;"></div>
                </div>
            </div>
            <div class="book-wall book-wall-back">
                <div class="books" style="top:6px;left:4px;right:4px;flex-direction:row;gap:3px;">
                    <div class="book-spine" style="width:10px;height:100%;background:#ef5350;"></div>
                    <div class="book-spine" style="width:8px;height:100%;background:#ec407a;"></div>
                    <div class="book-spine" style="width:12px;height:100%;background:#ab47bc;"></div>
                    <div class="book-spine" style="width:9px;height:100%;background:#7e57c2;"></div>
                    <div class="book-spine" style="width:11px;height:100%;background:#5c6bc0;"></div>
                    <div class="book-spine" style="width:8px;height:100%;background:#42a5f5;"></div>
                    <div class="book-spine" style="width:10px;height:100%;background:#26c6da;"></div>
                    <div class="book-spine" style="width:9px;height:100%;background:#66bb6a;"></div>
                </div>
            </div>
            <div class="book-wall book-wall-right">
                <div class="books" style="top:8px;left:4px;right:4px;">
                    <div class="book-spine" style="background:#6d4c41;"></div>
                    <div class="book-spine" style="background:#8d6e63;"></div>
                    <div class="book-spine" style="background:#5d4037;"></div>
                    <div class="book-spine" style="background:#a1887f;"></div>
                    <div class="book-spine" style="background:#4e342e;"></div>
                    <div class="book-spine" style="background:#bcaaa4;"></div>
                </div>
            </div>
            
            <!-- 分类标签 -->
            <div class="shelf-label" style="left:20px;top:42px;">架构</div>
            <div class="shelf-label" style="left:20px;top:80px;">算法</div>
            <div class="shelf-label" style="left:20px;top:118px;">GitHub</div>
            <div class="shelf-label" style="left:80px;top:42px;">最佳实践</div>
            
            <!-- 阅读桌 -->
            <div class="reading-table">
                <div class="open-book"></div>
                <div class="glasses"></div>
                <div class="globe"></div>
                <div class="cup" style="right:8px;bottom:10px;">
                    <div class="steam"></div>
                    <div class="steam"></div>
                    <div class="steam"></div>
                </div>
            </div>
            
            <!-- 梯子 -->
            <div class="ladder"></div>
            
            <!-- 知识树挂画 -->
            <div class="knowledge-tree">🌳</div>
            
            <!-- 盆栽 -->
            <div class="pot-plant" style="left:80px;bottom:8px;">🪴</div>
            <div class="pot-plant" style="right:8px;bottom:8px;animation-delay:1s;">🌿</div>
            
            <div class="door" style="right:20px;bottom:2px;"></div>
        </div>

        <!-- 总经理办公室 -->
        <div class="room" id="ceo" onclick="showRoom('ceo')">
            <div class="room-label" style="left:15px;top:12px;"><span class="room-icon">🫎</span>总经理办公室</div>
            <div class="deer-badge">🦌</div>
            <div class="window"></div>
            <div class="bookshelf-small">
                <div class="trophy">🏆</div>
            </div>
            <div class="strategy-board">📈</div>
            <div class="ceo-desk"></div>
            <div class="ceo-chair"></div>
            <div class="pot-plant" style="left:180px;bottom:12px;">🌵</div>
            <div class="door" style="left:20px;bottom:2px;"></div>
        </div>

        <!-- 开放办公区 -->
        <div class="room" id="office-area" onclick="showRoom('office')">
            <div class="room-label" style="left:15px;top:12px;"><span class="room-icon">🏢</span>开放办公区</div>
            <div class="rug"></div>
"""
    )

    # 工位布局
    positions = [
        (60, 60, "squirrel", "较真松鼠", "online"),
        (210, 60, "hedgehog", "戒备猬", "busy"),
        (360, 60, "owl", "夜枭猫头鹰", "online"),
        (510, 60, "beaver", "勤恳海狸", "idle"),
        (130, 200, "fox", "狡黠狐狸", "online"),
        (340, 200, "desk6", "待招岗位", "idle"),
    ]
    personal_items = [
        ["🎧", "🖼️", "📝"],
        ["🔒", "🖼️", ""],
        ["🧠", "🖼️", "📝"],
        ["🔧", "🖼️", ""],
        ["🧪", "🖼️", "📝"],
        ["", "", ""],
    ]
    for idx, (x, y, aid, name, st) in enumerate(positions):
        office_info = offices_data.get("offices", {}).get(aid, {})
        badge = office_info.get("badge", {})
        level = badge.get("level", 1)
        role = badge.get("role", "")
        status_class = f"status-dot {st}"
        items = personal_items[idx]
        headphone = f'<div class="headphones">{items[0]}</div>' if items[0] else ""
        photo = f'<div class="photo-frame">{items[1]}</div>' if items[1] else ""
        sticky = '<div class="sticky-note"></div>' if items[2] else ""
        click_attr = (
            f"onclick=\"event.stopPropagation();showDesk('{aid}','{name}','{role}',{level})\""
            if aid != "desk6"
            else ""
        )
        html += f"""
            <div class="desk" style="left:{x}px;top:{y}px;" {click_attr}>
                <div class="desk-top"></div>
                <div class="monitor"></div>
                {photo}
                {sticky}
                <div class="keyboard"></div>
                <div class="mouse"></div>
                <div class="phone"></div>
                <div class="cup"><div class="steam"></div><div class="steam"></div><div class="steam"></div></div>
                {headphone}
                <div class="plant">🪴</div>
                <div class="chair" style="bottom:-32px;left:38px;"></div>
                <div class="{status_class}"></div>
                <div class="employee-name">{name}</div>
            </div>
"""

    html += (
        """
        </div>

        <!-- 茶水间 -->
        <div class="room" id="breakroom" onclick="showRoom('breakroom')">
            <div class="room-label" style="left:15px;top:12px;"><span class="room-icon">☕</span>茶水间</div>
            <div class="counter">
                <div class="coffee-machine"></div>
                <div class="microwave"></div>
                <div class="water-dispenser"></div>
                <div class="cup" style="right:12px;bottom:14px;">
                    <div class="steam"></div>
                    <div class="steam"></div>
                </div>
            </div>
            <div class="stool" style="left:42px;top:82px;"></div>
            <div class="stool" style="left:92px;top:82px;"></div>
            <div class="stool" style="left:142px;top:82px;"></div>
            <div class="fruit-bowl"></div>
            <div class="clock"></div>
            <div class="cabinet" style="left:200px;top:15px;"></div>
            <div class="notice-board">
                <div class="notice-paper"></div>
                <div class="notice-paper"></div>
                <div class="notice-paper"></div>
                <div class="notice-paper"></div>
            </div>
        </div>

        <!-- 休息区 -->
        <div class="room" id="restarea" onclick="showRoom('restarea')">
            <div class="room-label" style="left:15px;top:12px;"><span class="room-icon">🧘</span>休息区</div>
            <div class="sofa">
                <div class="pillow"></div>
                <div class="pillow" style="left:55px;background:#c5e1a5;"></div>
                <div class="pillow" style="left:88px;background:#b3e5fc;"></div>
            </div>
            <div class="coffee-table"></div>
            <div class="floor-lamp"></div>
            <div class="dream-wall">
                <div class="dream-photo"></div>
                <div class="dream-photo"></div>
                <div class="dream-photo"></div>
                <div class="dream-photo"></div>
                <div class="dream-photo" style="width:100%;height:10px;background:#e1bee7;"></div>
            </div>
            <div class="fish-tank">
                <div class="ripple"></div>
                <div class="ripple"></div>
                <div class="ripple"></div>
                <div class="fish"></div>
            </div>
            <div class="pot-plant" style="left:12px;bottom:8px;">🌿</div>
        </div>

        <!-- 墙体分隔 -->
        <div class="wall wall-h" style="left:30px;top:290px;width:700px;"></div>
        <div class="wall wall-h" style="left:30px;top:640px;width:360px;"></div>
        <div class="wall wall-h" style="right:30px;top:640px;width:360px;"></div>
        <div class="wall wall-v" style="left:300px;top:30px;height:260px;"></div>
        <div class="wall wall-v" style="right:420px;top:30px;height:260px;"></div>
    </div>
</div>

<!-- 信息面板 -->
<div class="info-panel" id="infoPanel">
    <button class="close-btn" onclick="closePanel()">×</button>
    <h3>🏢 欢迎来到 BlueDeer 森林公司</h3>
    <p>点击任意房间或员工工位查看详情。</p>
    <ul>
        <li>📚 资料库：三面书墙、彩色书脊、阅读桌、地球仪、知识树挂画</li>
        <li>🫎 总经理办公室：忧郁鹿全局调度中心</li>
        <li>🏢 开放办公区：6 个独立工位，每个都有独特个人物品</li>
        <li>☕ 茶水间：咖啡机、微波炉、饮水机、水果、公告板</li>
        <li>🧘 休息区：沙发、落地灯、鱼缸、梦境照片墙</li>
    </ul>
</div>

<div class="footer-tip">
    BlueDeer 森林公司 · 多智能体协同办公系统 · 认知架构 v2.5D+
</div>

<script>
const roomData = {
    library: {
        title: "📚 资料库",
        content: "公司拥有三面书墙，收录 <b>"""
        + str(status["library"]["total_entries"])
        + """</b> 条知识条目，整合 <b>"""
        + str(github_data["total_projects"])
        + """</b> 个 GitHub 精选项目。阅读桌上摊开的书、地球仪、眼镜和热茶，知识的香气扑面而来。"
    },
    ceo: {
        title: "🫎 总经理办公室",
        content: "忧郁鹿的调度中心。负责任务分发、负载均衡、熔断重分配、Token 审计与奖惩结算。窗外就是森林，墙上挂着战略图。"
    },
    office: {
        title: "🏢 开放办公区",
        content: "6 个独立工位，员工状态实时显示。绿点在线、橙点忙碌、灰点空闲。每个工位都有显示器、键盘、热茶杯、绿植和独特的个人物品。"
    },
    breakroom: {
        title: "☕ 茶水间",
        content: "员工自由交流区。当前有 <b>"""
        + str(status["breakroom"]["total_messages"])
        + """</b> 条消息。咖啡机、微波炉、饮水机一应俱全，公告板贴着最新通知。"
    },
    restarea: {
        title: "🧘 休息区",
        content: "放松与梦境回放空间。舒适的沙发、落地灯、游着金鱼的鱼缸，还有记录成功与失败记忆的梦境照片墙。"
    }
};

function showRoom(room) {
    const panel = document.getElementById('infoPanel');
    const data = roomData[room];
    panel.innerHTML = '<button class="close-btn" onclick="closePanel()">×</button><h3>' + data.title + '</h3><p>' + data.content + '</p>';
    panel.style.display = 'block';
}

function showDesk(aid, name, role, level) {
    const panel = document.getElementById('infoPanel');
    panel.innerHTML = '<button class="close-btn" onclick="closePanel()">×</button>' +
        '<h3>🧑‍💻 ' + name + '</h3>' +
        '<p><b>岗位：</b>' + (role || '工程师') + '</p>' +
        '<p><b>等级：</b>Lv' + level + '</p>' +
        '<p><b>工号：</b>' + aid + '</p>' +
        '<p>正在使用高性能工作站，显示器上运行着代码。桌上一杯热茶正冒着袅袅热气。</p>';
    panel.style.display = 'block';
}

function closePanel() {
    document.getElementById('infoPanel').style.display = 'none';
}
</script>
</body>
</html>"""
    )
    return html


@app.get("/vector", response_class=HTMLResponse)
async def vector_page(request: Request) -> str:
    with open("static/vector.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/debug", response_class=HTMLResponse)
async def debug_page(request: Request) -> str:
    """调试面板：火焰图 + 推理链路可视化。"""
    traces = debugger.summary()
    trace_options = ""
    for s in traces:
        tid = s.trace_id
        dur = f"{s.total_duration_ms:.1f}" if s.total_duration_ms else "?"
        label = f"{tid[:12]}… ({s.span_count} spans, {dur}ms)"
        trace_options += f'<option value="{tid}">{label}</option>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BlueDeer · 调试面板</title>
<link rel="stylesheet" href="/static/debug.css">
</head>
<body>
<div class="debug-header">
    <div>
        <h1>🔬 BlueDeer 调试面板</h1>
        <div class="subtitle">火焰图 · 推理链路 · Trace 分析</div>
    </div>
    <div class="nav-links">
        <a href="/">🏠 仪表盘</a>
        <a href="/debug" style="border-color:var(--accent-dim);background:rgba(76,175,80,0.1);">🔬 调试面板</a>
    </div>
</div>

<div class="container">
    {f'''<!-- Trace 选择器 -->
    <div class="card trace-selector">
        <label for="traceSelect">选择 Trace:</label>
        <select id="traceSelect">{trace_options}</select>
        <button class="btn btn-sm" id="refreshBtn" style="margin-left:12px;">⟳ 刷新</button>
        <button class="btn btn-sm btn-primary" id="genSampleBtn" style="margin-left:8px;">🎲 生成测试 Trace</button>
    </div>''' if trace_options else '''<div class="card" style="text-align:center;padding:40px;">
        <p style="color:var(--text-secondary);font-size:14px;margin-bottom:16px;">暂无 trace 数据</p>
        <button class="btn btn-primary" id="genSampleBtn">🎲 生成测试 Trace</button>
    </div>'''}

    <!-- Tab 栏 -->
    <div class="tab-bar">
        <button class="tab-btn active" data-tab="flame">
            🔥 火焰图 <span class="badge">Flame Graph</span>
        </button>
        <button class="tab-btn" data-tab="chain">
            🔗 推理链路 <span class="badge">Chain</span>
        </button>
        <button class="tab-btn" data-tab="summary">
            📊 摘要统计 <span class="badge">Summary</span>
        </button>
    </div>

    <!-- 火焰图面板 -->
    <div class="tab-panel active" id="tabFlame">
        <div class="card">
            <h2>🔥 火焰图</h2>
            <p style="font-size:12px;color:var(--text-secondary);margin-bottom:12px;">
                色块宽度 = 耗时 · 悬停查看详情 · 点击色块放大 · 点击空白恢复
            </p>
            <div class="legend" id="flameLegend">
                <div class="legend-item"><span class="legend-color" style="background:hsla(140,55%,40%,0.8)"></span>Agent</div>
                <div class="legend-item"><span class="legend-color" style="background:hsla(210,60%,40%,0.8)"></span>Tool</div>
                <div class="legend-item"><span class="legend-color" style="background:hsla(30,70%,42%,0.8)"></span>Model</div>
                <div class="legend-item"><span class="legend-color" style="background:hsla(280,45%,40%,0.8)"></span>Event</div>
                <div class="legend-item"><span class="legend-color" style="background:hsla(0,70%,45%,0.8)"></span>Error</div>
            </div>
            <div class="flame-container">
                <canvas id="flameCanvas"></canvas>
                <div class="flame-tooltip" id="flameTooltip"></div>
            </div>
        </div>
    </div>

    <!-- 推理链路面板 -->
    <div class="tab-panel" id="tabChain">
        <div class="card">
            <h2>🔗 Agent 调用链</h2>
            <p style="font-size:12px;color:var(--text-secondary);margin-bottom:12px;">
                树形结构，显示 Agent 调用顺序和耗时
            </p>
            <div id="chainTreeContainer"></div>
        </div>
        <div class="card">
            <h2>📐 Mermaid 流程图</h2>
            <p style="font-size:12px;color:var(--text-secondary);margin-bottom:12px;">
                从 Canvas 模块生成的调用流程图
            </p>
            <div class="mermaid-container" id="mermaidContainer">
                <pre id="mermaidCode" style="font-size:12px;color:var(--text-secondary);overflow-x:auto;"></pre>
            </div>
        </div>
    </div>

    <!-- 摘要统计面板 -->
    <div class="tab-panel" id="tabSummary">
        <div id="summaryContent">
            <div class="card" style="text-align:center;padding:40px;">
                <p style="color:var(--text-secondary);font-size:13px;">选择 trace 查看统计</p>
            </div>
        </div>
    </div>
</div>

<script src="/static/debug.js"></script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
