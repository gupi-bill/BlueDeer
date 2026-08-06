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


# ===== 路由注册（自动拆分） =====
from .routes_admin import router as _admin_router
from .routes_users import router as _users_router
from .routes_system import router as _system_router
from .routes_traces import router as _traces_router
from .routes_plugins import router as _plugins_router
from .routes_agents import router as _agents_router
from .routes_dag import router as _dag_router
from .routes_alerts import router as _alerts_router
from .routes_vector import router as _vector_router
from .routes_pages import router as _pages_router
from .routes_misc import router as _misc_router

app.include_router(_admin_router)
app.include_router(_users_router)
app.include_router(_system_router)
app.include_router(_traces_router)
app.include_router(_plugins_router)
app.include_router(_agents_router)
app.include_router(_dag_router)
app.include_router(_alerts_router)
app.include_router(_vector_router)
app.include_router(_pages_router)
app.include_router(_misc_router)
