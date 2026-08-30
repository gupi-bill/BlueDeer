"""BlueDeer 森林公司仪表盘服务器。

启动方式: python -m uvicorn web_server:app --reload --port 8080
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import os
import socket
import threading
import time
import urllib.request
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from core.breakroom import BreakRoom
from core.canvas import Canvas
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


# ===== 生命周期管理 =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭生命周期：加载插件、启动服务、清理资源。"""
    # --- startup ---
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

    global _biosphere_instance
    try:
        bio = Biosphere(
            save_path="data/biosphere_save.json",
            pid_path="data/biosphere.pid",
        )
        bio.bootstrap(load=True)
        bio.start()
        _biosphere_instance = bio
        init_biosphere(bio)
        logger.info("🌿 森林生物圈已启动")
    except Exception as e:
        logger.warning("生物圈启动失败（可忽略）: %s", e)

    yield

    # --- shutdown ---
    await scheduler.stop()
    await webhook.stop()
    await plugin_manager.shutdown()

    if _biosphere_instance is not None:
        try:
            _biosphere_instance.stop()
            logger.info("🌿 森林生物圈已停止")
        except Exception as e:
            logger.warning("生物圈停止异常: %s", e)


# ===== 请求验证中间件 =====

app = FastAPI(title="BlueDeer 森林公司仪表盘", lifespan=lifespan)


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
                await request.json()
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


# ---- API 网关限流中间件 ----
from fastapi.responses import JSONResponse as _JSONResponse


@app.middleware("http")
async def api_rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)
    from core.api_rate_limit import get_rate_limiter

    limiter = get_rate_limiter()
    user = getattr(request.state, "user", "anonymous")
    ip = request.client.host if request.client else "unknown"
    ok, info = limiter.allow(user, ip, path)
    if not ok:
        return _JSONResponse(
            {"code": 429, "msg": "请求过于频繁，请稍后再试", "data": info},
            status_code=429,
        )
    return await call_next(request)



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

# ===== 实时状态 API（概览页真实数据源） =====
OPENCLAW_CONFIG_PATH = Path(r"C:\Users\a\Desktop\vibe coding\OpenClaw\data\openclaw.json")


def _load_openclaw_config() -> dict:
    try:
        with open(OPENCLAW_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _check_tcp(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _ollama_installed_models() -> list[str]:
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


# ===== OpenClaw 网关 CLI 集成（真实数据通道） =====
# openclaw CLI 本身就是网关官方客户端（内部完成 WS 握手/签名），
# 通过它拉取真实 agent / session / channel / cron / model 数据。
OPENCLAW_STATE_DIR = r"C:\Users\a\Desktop\vibe coding\OpenClaw\data"
OPENCLAW_NODE = r"C:\Users\a\.workbuddy\binaries\node\versions\22.22.2\node.exe"
OPENCLAW_CLI = (
    r"C:\Users\a\.workbuddy\binaries\node\versions\22.22.2"
    r"\node_modules\openclaw\dist\index.js"
)

_oc_cache: dict = {}
_oc_cache_ts: float = 0.0


def _openclaw_cli(args: list, timeout: float = 22.0):
    """调用 openclaw CLI（官方网关客户端），解析 stdout 中的 JSON。"""
    import subprocess

    env = dict(os.environ)
    env["OPENCLAW_STATE_DIR"] = OPENCLAW_STATE_DIR
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        p = subprocess.run(
            [OPENCLAW_NODE, OPENCLAW_CLI] + args,
            capture_output=True, text=True, timeout=timeout, env=env,
            creationflags=flags,
        )
        out = p.stdout or ""
        # stdout 开头可能有 state-migrations 警告行，定位第一个 JSON 起始
        start = len(out)
        for ch in ("{", "["):
            i = out.find(ch)
            if 0 <= i < start:
                start = i
        if start < len(out):
            return json.loads(out[start:])
        return None
    except Exception:
        return None


def _openclaw_quick() -> dict:
    """毫秒级真实数据：网关 /health + openclaw.json + 磁盘会话文件（不调 CLI）。"""
    gw_up = _check_tcp("127.0.0.1", 18789, timeout=0.5)
    cfg = _load_openclaw_config()
    agents_cfg = cfg.get("agents", {}) or {}
    defaults = agents_cfg.get("defaults", {}) or {}
    primary_model = (defaults.get("model", {}) or {}).get("primary", "")
    channels_cfg = cfg.get("channels", {}) or {}

    sessions = []
    sessions_count = 0
    skills = []
    sess_path = os.path.join(
        OPENCLAW_STATE_DIR, "agents", "main", "sessions", "sessions.json"
    )
    try:
        with open(sess_path, "r", encoding="utf-8") as f:
            smap = json.load(f)
        sessions_count = len(smap)
        for key, s in list(smap.items())[:12]:
            sessions.append({
                "key": key,
                "channel": (s.get("route", {}) or {}).get("channel", s.get("lastChannel", "")),
                "updatedAt": s.get("updatedAt"),
                "tokens": s.get("totalTokens", 0),
                "sessionId": s.get("sessionId", ""),
            })
        seen = set()
        for s in smap.values():
            for sk in (s.get("skillsSnapshot", {}) or {}).get("skills", []) or []:
                n = sk.get("name") if isinstance(sk, dict) else str(sk)
                if n and n not in seen:
                    seen.add(n)
                    skills.append(n)
    except Exception:
        pass

    return {
        "connected": gw_up,
        "controlUrl": "http://127.0.0.1:18789/",
        "gatewayHealth": gw_up,
        "primaryModel": primary_model,
        "agentsConfig": agents_cfg,
        "channelsConfig": channels_cfg,
        "sessions": sessions,
        "sessionsCount": sessions_count,
        "skills": skills[:40],
    }


_oc_cache: dict = {}
_oc_cache_ts: float = 0.0
_oc_refreshing: bool = False


def _openclaw_snapshot() -> dict:
    """返回 OpenClaw 网关真实数据：快速路径立即返回，慢速 CLI 后台缓存刷新。"""
    global _oc_cache, _oc_cache_ts, _oc_refreshing
    now = time.time()
    if _oc_cache and (now - _oc_cache_ts) < 60:
        return _oc_cache
    if _oc_refreshing:
        # 正在后台刷新：先把快速路径数据兜底返回，不阻塞请求
        quick = _openclaw_quick()
        if _oc_cache:
            base = dict(_oc_cache)
            base.update(quick)
            return base
        return {"ok": bool(quick["connected"]), "refreshing": True, **quick}
    _oc_refreshing = True

    def _refresh():
        global _oc_cache, _oc_cache_ts, _oc_refreshing
        try:
            quick = _openclaw_quick()
            if not quick["connected"]:
                _oc_cache = {"ok": False, "refreshing": False, **quick}
                _oc_cache_ts = time.time()
                return
            from concurrent.futures import ThreadPoolExecutor

            def _run(cmd):
                return _openclaw_cli(cmd) or {}

            with ThreadPoolExecutor(max_workers=4) as ex:
                f_status = ex.submit(_run, ["status", "--json"])
                f_agents = ex.submit(_run, ["agents", "list", "--json"])
                f_channels = ex.submit(_run, ["channels", "list", "--json"])
                f_models = ex.submit(_run, ["models", "status", "--json"])
                snap = {
                    "ok": True,
                    "refreshing": False,
                    "status": f_status.result(),
                    "agents": f_agents.result(),
                    "channels": f_channels.result(),
                    "models": f_models.result(),
                    **quick,
                }
            _oc_cache, _oc_cache_ts = snap, time.time()
        except Exception:
            _oc_cache = {"ok": False, "refreshing": False, **_openclaw_quick()}
            _oc_cache_ts = time.time()
        finally:
            _oc_refreshing = False

    threading.Thread(target=_refresh, daemon=True).start()
    quick = _openclaw_quick()
    if _oc_cache:
        base = dict(_oc_cache)
        base.update(quick)
        return base
    return {"ok": bool(quick["connected"]), "refreshing": True, **quick}



@app.get("/api/realtime-status")
@cache_response(ttl=5)
async def realtime_status() -> dict:
    """返回 BlueDeer / OpenClaw 真实运行态，供概览页渲染。

    数据源：
    - OpenClaw 配置文件（gateway / agents / channels / mcp）
    - 网关端口 TCP 连通性
    - Ollama 11434 端口连通性 + /api/tags 已安装模型
    """
    cfg = await asyncio.to_thread(_load_openclaw_config)
    gateway = cfg.get("gateway", {})
    agents_cfg = cfg.get("agents", {})
    channels_cfg = cfg.get("channels", {})

    gw_port = gateway.get("port", 18789)
    bind = gateway.get("bind", "loopback")
    gw_host = "127.0.0.1" if bind in ("loopback", "localhost") else "0.0.0.0"

    gw_running, ollama_running = await asyncio.gather(
        asyncio.to_thread(_check_tcp, gw_host, int(gw_port)),
        asyncio.to_thread(_check_tcp, "127.0.0.1", 11434),
    )
    installed_models = (
        await asyncio.to_thread(_ollama_installed_models) if ollama_running else []
    )

    agent_entries = agents_cfg.get("entries", [])
    if not isinstance(agent_entries, list):
        agent_entries = []
    online_agents = len(agent_entries)

    enabled_channels = 0
    if isinstance(channels_cfg, dict):
        enabled_channels = sum(
            1
            for v in channels_cfg.values()
            if isinstance(v, dict) and v.get("enabled") is not False
        )

    defaults = agents_cfg.get("defaults", {})
    primary_model = defaults.get("model", {}).get("primary", "未配置")

    # 主模型是否可在本地 Ollama 列表中匹配（支持 alias / 完整名）
    model_reachable = False
    if installed_models and primary_model and primary_model != "未配置":
        model_reachable = any(
            primary_model == m
            or primary_model.endswith(f"/{m}")
            or m.endswith(primary_model)
            for m in installed_models
        )

    checks = {
        "gateway": gw_running,
        "ollama": ollama_running,
        "bluedeer_web": True,
        "primary_model_reachable": model_reachable,
    }
    score = int(sum(checks.values()) / len(checks) * 100)
    health = "healthy" if score == 100 else ("degraded" if score >= 60 else "unhealthy")

    # 最近会话：用真实 agent 条目 + 频道聚合
    recent: list[dict] = []
    for a in agent_entries[:5]:
        recent.append(
            {
                "mainKey": f"agent::{a.get('id', 'unknown')}",
                "state": "RUNNING",
                "time": "在线",
            }
        )
    if enabled_channels:
        recent.append({"mainKey": "channel::aggregate", "state": "RUNNING", "time": "在线"})
    if not recent:
        recent.append({"mainKey": "system", "state": "IDLE", "time": "刚刚"})

    events: list[dict] = []
    if gw_running:
        events.append(
            {"level": "INFO", "text": f"网关监听 {bind}:{gw_port}", "time": "实时"}
        )
    else:
        events.append(
            {"level": "WARN", "text": f"网关未响应 {bind}:{gw_port}", "time": "实时"}
        )
    if ollama_running:
        events.append(
            {
                "level": "INFO",
                "text": f"本地推理在线，模型 {len(installed_models)} 个",
                "time": "实时",
            }
        )
    else:
        events.append(
            {"level": "WARN", "text": "本地推理未响应 127.0.0.1:11434", "time": "实时"}
        )
    if not online_agents:
        events.append(
            {
                "level": "INFO",
                "text": "当前无 agent 条目（agents.entries 为空）",
                "time": "实时",
            }
        )

    mcp_servers = cfg.get("mcp", {}).get("servers", {})
    logs = [
        {
            "level": "INFO",
            "text": f"gateway.mode={gateway.get('mode', 'unknown')} port={gw_port} bind={bind}",
            "time": "实时",
        },
        {
            "level": "INFO",
            "text": f"agents.defaults.model.primary={primary_model}",
            "time": "实时",
        },
        {
            "level": "INFO",
            "text": f"channels.enabled={enabled_channels} mcp.servers={len(mcp_servers)}",
            "time": "实时",
        },
    ]
    if not model_reachable and primary_model != "未配置":
        logs.append(
            {
                "level": "WARN",
                "text": f"主模型 {primary_model} 不在本地已安装列表中",
                "time": "实时",
            }
        )

    return {
        "gateway": {
            "mode": gateway.get("mode", "unknown"),
            "port": str(gw_port),
            "authMode": gateway.get("auth", {}).get("mode", "unknown"),
            "bind": bind,
        },
        "stats": {
            "agentsOnline": online_agents,
            "channelsConnected": enabled_channels,
            "primaryModel": primary_model,
            "tokensToday": 0,
            "tokensNote": "未接入用量统计",
            "health": health,
            "healthScore": score,
        },
        "services": {
            "gatewayRunning": gw_running,
            "ollamaRunning": ollama_running,
            "installedModels": installed_models,
            "modelReachable": model_reachable,
        },
        "recent": recent,
        "events": events,
        "logs": logs,
    }


# ===== 全模块真实数据（仪表盘数据源，无假数据） =====
def _scan_agents(root: str) -> list[dict]:
    """静态扫描 modules/ 下每个 agent 模块的真实角色与技能（正则解析，不导入业务代码）。"""
    import re

    modules_dir = os.path.join(root, "modules")
    out: list[dict] = []
    if not os.path.isdir(modules_dir):
        return out

    def extract(path: str, pat: str) -> list[str]:
        try:
            s = open(path, encoding="utf-8", errors="ignore").read()
        except Exception:
            return []
        return re.findall(pat, s)

    for name in sorted(os.listdir(modules_dir)):
        d = os.path.join(modules_dir, name)
        if not os.path.isdir(d):
            continue
        ap = os.path.join(d, "agent.py")
        sp = os.path.join(d, "skills.py")
        rg = os.path.join(d, "role_glow.py")
        if not (os.path.exists(ap) or os.path.exists(sp) or os.path.exists(rg)):
            continue
        roles = extract(ap, r'role="([^"]+)"') + extract(rg, r'role="([^"]+)"')
        roles = [r for r in roles if r and r != "unknown"]
        classes = extract(ap, r"class\s+(\w*Agent)\b")
        skills: list[str] = []
        if os.path.exists(sp):
            skills = [s for s in extract(sp, r"async\s+def\s+(\w+)") if not s.startswith("_")]
        skills = list(dict.fromkeys(skills))
        out.append(
            {
                "id": name,
                "roles": roles or ["（未定义角色）"],
                "classes": classes,
                "skill_count": len(skills),
                "skills": skills,
            }
        )
    return out


def _load_json_file(path: str):
    import json

    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _load_model_settings(root: str) -> dict:
    """用户在前端配置的模型来源（本地 Ollama / 云端 API）。"""
    import json

    path = os.path.join(root, "data", "model_settings.json")
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    # 默认值：本地优先，用户可在前端切换为 API
    return {
        "source": d.get("source", "local"),  # local | api
        "api_base": d.get("api_base", ""),
        "api_model": d.get("api_model", ""),
        "api_key": d.get("api_key", ""),
    }


def _detect_api_provider(base: str) -> str:
    """根据 API base_url 识别供应商名称。"""
    b = (base or "").lower()
    if "siliconflow" in b or "硅基" in b:
        return "SiliconFlow"
    if "openai" in b and "azure" not in b:
        return "OpenAI"
    if "azure" in b or "inference.ai" in b:
        return "Azure/GitHub Models"
    if "deepseek" in b:
        return "DeepSeek"
    if "bigmodel" in b or "智谱" in b:
        return "智谱"
    if "dashscope" in b:
        return "DashScope"
    if "openrouter" in b:
        return "OpenRouter"
    if "localhost" in b or "127.0.0.1" in b:
        return "本地兼容端点"
    return "自定义 API"


def _probe_api_models(base: str, key: str, model: str) -> dict:
    """探测云端 API 是否可达，并尝试拉取模型列表。

    兼容 OpenAI / SiliconFlow / Azure 等 /v1/models 端点。
    """
    import ssl

    result = {"reachable": False, "models": [], "error": "", "provider": _detect_api_provider(base)}
    if not base:
        result["error"] = "未配置 API 地址"
        return result
    url = base.rstrip("/") + "/models"
    headers = {"User-Agent": "BlueDeer-Console/1.0"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=5.0, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = []
            for item in data.get("data", []):
                name = item.get("id") or item.get("model") or item.get("name")
                if name:
                    models.append(name)
            result["reachable"] = True
            result["models"] = models[:50]  # 最多 50 个
            if model and any(model == m or m.endswith(model) or model.endswith(m) for m in models):
                result["target_match"] = True
            else:
                result["target_match"] = bool(model) and bool(models)
    except Exception as e:
        result["error"] = str(e)
    return result



def _scan_config(path: str) -> dict:
    import re

    try:
        s = open(path, encoding="utf-8", errors="ignore").read()
    except Exception:
        return {}
    grp = lambda pat, d=None: (re.search(pat, s).group(1) if re.search(pat, s) else d)
    tm = re.search(r"task_model_map.*?default_factory=lambda:\s*\{([^}]*)\}", s, re.S)
    task_map = dict(re.findall(r'"(\w+)":\s*"([^"]+)"', tm.group(1))) if tm else {}
    return {
        "default_model": grp(r'default_model:\s*str\s*=\s*"([^"]+)"'),
        "task_model_map": task_map,
        "environments": ["local", "cloud", "test"],
        "response_styles": ["default", "formal", "casual", "technical", "creative"],
        "reward": {
            "coins_success": grp(r"coins_success:\s*int\s*=\s*(\d+)"),
            "coins_failed": grp(r"coins_failed:\s*int\s*=\s*(\d+)"),
            "exp_success": grp(r"exp_success:\s*int\s*=\s*(\d+)"),
            "favor_init": grp(r"favor_init:\s*int\s*=\s*(\d+)"),
        },
    }


def _scan_usage(db_path: str) -> dict:
    try:
        import sqlite3

        con = sqlite3.connect(db_path)
        cur = con.cursor()
        try:
            cur.execute(
                "SELECT COALESCE(SUM(tokens_in),0), COALESCE(SUM(tokens_out),0), COUNT(*) FROM task_results"
            )
            ti, to, n = cur.fetchone()
        except Exception:
            ti, to, n = 0, 0, 0
        try:
            cur.execute("SELECT COUNT(*) FROM task_pending")
            pending = cur.fetchone()[0]
        except Exception:
            pending = 0
        con.close()
        return {
            "tokens_in": ti,
            "tokens_out": to,
            "tasks_done": n,
            "tasks_pending": pending,
        }
    except Exception:
        return {"tokens_in": 0, "tokens_out": 0, "tasks_done": 0, "tasks_pending": 0}


def _scan_core_modules(root: str) -> dict:
    core = os.path.join(root, "core")

    def exists(*names: str) -> list[str]:
        return [n for n in names if os.path.exists(os.path.join(core, n + ".py"))]

    return {
        "nodes": exists(
            "task_dag", "dag_templates", "task_orchestrator", "task_dispatcher",
            "task_board", "stream", "task_templates", "gantt",
        ),
        "automation": exists(
            "scheduler", "healer_engine", "healer", "circuit_breaker",
            "retry", "retry_handler", "healer_retry", "healer_strategies",
        ),
        "sessions": exists("session_store", "state_store", "context", "cleanup"),
        "comm": exists("event_bus", "comm_log", "notifier", "webhook", "dead_letter_queue"),
        "infra": exists(
            "backup", "git_ops", "database", "config", "auth", "security",
            "mcp", "monitor", "metrics_collector", "observability",
        ),
    }


async def dashboard_data() -> dict:
    """BlueDeer 全模块真实数据。所有数据来自本地真实文件/库，无假数据。"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = await asyncio.to_thread(_load_openclaw_config)
    gateway = cfg.get("gateway", {})
    agents_cfg = cfg.get("agents", {})
    channels_cfg = cfg.get("channels", {})
    gw_port = gateway.get("port", 18789)
    bind = gateway.get("bind", "loopback")
    gw_host = "127.0.0.1" if bind in ("loopback", "localhost") else "0.0.0.0"

    # 模型来源配置（本地 / 云端 API），必须在健康检查前加载
    model_settings = await asyncio.to_thread(_load_model_settings, root)
    source = model_settings.get("source", "local")

    gw_running, ollama_running = await asyncio.gather(
        asyncio.to_thread(_check_tcp, gw_host, int(gw_port)),
        asyncio.to_thread(_check_tcp, "127.0.0.1", 11434),
    )
    installed_models = (
        await asyncio.to_thread(_ollama_installed_models) if ollama_running else []
    )

    # OpenClaw 网关真实数据（快速路径毫秒级 + CLI 深数据后台缓存）
    oc = await asyncio.to_thread(_openclaw_snapshot)
    oc_connected = bool(oc.get("connected"))
    oc_agents = oc.get("agents", []) or []
    oc_status = oc.get("status", {}) or {}
    oc_models = oc.get("models", {}) or {}
    oc_channels = oc.get("channels", {}) or {}
    oc_sessions = oc_status.get("sessions", {}) or {}
    oc_sessions_count = int(oc.get("sessionsCount", 0) or 0)

    if oc_connected:
        # 真实数据优先：OpenClaw 实际运行的 agent / 会话 / 模型
        online_agents = len(oc_agents) if oc_agents else (1 if oc.get("agentsConfig") else 0)
        oc_agent_objs = [a for a in oc_agents if isinstance(a, dict)]
        if oc_agent_objs:
            primary_model = oc_agent_objs[0].get("model") or "未配置"
        elif oc_models.get("resolvedDefault"):
            primary_model = oc_models.get("resolvedDefault")
        elif oc.get("primaryModel"):
            primary_model = oc.get("primaryModel")
        else:
            primary_model = "未配置"
        enabled_channels = len(oc_channels.get("chat", {})) if isinstance(oc_channels, dict) else 0
    else:
        agent_entries = agents_cfg.get("entries", [])
        if not isinstance(agent_entries, list):
            agent_entries = []
        online_agents = len(agent_entries)
        enabled_channels = 0
        if isinstance(channels_cfg, dict):
            enabled_channels = sum(
                1 for v in channels_cfg.values()
                if isinstance(v, dict) and v.get("enabled") is not False
            )
        defaults = agents_cfg.get("defaults", {})
        primary_model = defaults.get("model", {}).get("primary", "未配置")

    # 云端 API 探测（当用户选择 API 模式时，不再只看本地 Ollama）
    api_status: dict = {"reachable": False, "models": [], "error": "", "provider": ""}
    if source == "api":
        api_status = await asyncio.to_thread(
            _probe_api_models,
            model_settings.get("api_base", ""),
            model_settings.get("api_key", ""),
            model_settings.get("api_model", ""),
        )

    agent_entries = agents_cfg.get("entries", [])
    if not isinstance(agent_entries, list):
        agent_entries = []
    defaults = agents_cfg.get("defaults", {})

    # 主模型可达性：API 模式下以云端探测为准，本地模式以 Ollama 列表为准
    model_reachable = False
    if source == "api":
        model_reachable = api_status.get("reachable", False)
    elif installed_models and primary_model and primary_model != "未配置":
        model_reachable = any(
            primary_model == m or primary_model.endswith(f"/{m}") or m.endswith(primary_model)
            for m in installed_models
        )

    checks = {
        "gateway": gw_running,
        "ollama": ollama_running if source == "local" else True,
        "bluedeer_web": True,
        "primary_model_reachable": model_reachable,
    }
    score = int(sum(checks.values()) / len(checks) * 100)
    health = "healthy" if score == 100 else ("degraded" if score >= 60 else "unhealthy")

    agents = await asyncio.to_thread(_scan_agents, root)
    crons = await asyncio.to_thread(_load_json_file, os.path.join(root, "data", "scheduler_jobs.json"))
    config = await asyncio.to_thread(_scan_config, os.path.join(root, "core", "config.py"))
    usage = await asyncio.to_thread(_scan_usage, os.path.join(root, "data", "bluedeer.db"))
    core_mods = await asyncio.to_thread(_scan_core_modules, root)

    biosphere_pid_path = os.path.join(root, "data", "biosphere.pid")
    biosphere_running = os.path.exists(biosphere_pid_path)

    return {
        "overview": {
            "gateway": {
                "mode": gateway.get("mode", "unknown"),
                "port": str(gw_port),
                "bind": bind,
                "running": gw_running,
            },
            "stats": {
                "agentsOnline": online_agents,
                "channelsConnected": enabled_channels,
                "primaryModel": primary_model,
                "tokensToday": usage["tokens_in"] + usage["tokens_out"],
                "health": health,
                "healthScore": score,
                "ollamaRunning": ollama_running,
                "installedModels": installed_models,
                "modelSource": source,
                "apiProvider": api_status.get("provider", ""),
                "apiModelCount": len(api_status.get("models", [])),
                # OpenClaw 真实运行数据
                "ocConnected": oc_connected,
                "ocSessions": oc_sessions_count,
                "ocAgentName": (
                    (oc_agent_objs[0].get("identityName") or oc_agent_objs[0].get("id"))
                    if oc_connected and oc_agent_objs else ""
                ),
            },
            "services": {
                "gateway": gw_running,
                "ollama": ollama_running,
                "bluedeer_web": True,
                "biosphere": biosphere_running,
                "modelReachable": model_reachable,
                "apiReachable": api_status.get("reachable", False),
                "openclawCli": oc_connected,
            },
        },
        # OpenClaw 网关真实快照（快速路径 + CLI 深数据）
        "openclaw": {
            "connected": oc_connected,
            "stateDir": OPENCLAW_STATE_DIR,
            "controlUrl": oc.get("controlUrl", f"http://127.0.0.1:{int(gw_port)}/"),
            "refreshing": oc.get("refreshing", False),
            "status": oc_status,
            "agents": oc_agents,
            "channels": oc_channels,
            "models": oc_models,
            "sessions": oc.get("sessions", []),
            "skills": oc.get("skills", []),
        },
        "agents": agents,
        "skills": {
            "total": sum(a["skill_count"] for a in agents),
            "by_agent": {a["id"]: a["skill_count"] for a in agents},
        },
        "crons": crons if isinstance(crons, list) else [],
        "config": config,
        "modelSettings": model_settings,
        "apiStatus": api_status,
        "usage": usage,
        "nodes": core_mods["nodes"],
        "automation": core_mods["automation"],
        "sessions": {"modules": core_mods["sessions"], "active": usage["tasks_pending"]},
        "comm": {"webhooks": 0, "modules": core_mods["comm"]},
        "infra": {
            "modules": core_mods["infra"],
            "services": {
                "gateway": gw_running,
                "ollama": ollama_running,
                "biosphere": biosphere_running,
            },
        },
        "instances": {"biosphere_running": biosphere_running, "web_running": True},
        "appearance": {"logo": "/static/assets/bluedeer-logo.png", "name": "BlueDeer"},
        "channels": {
            "enabled": enabled_channels,
            "available": list(channels_cfg.keys()) if isinstance(channels_cfg, dict) else [],
        },
    }


@app.get("/api/dashboard")
async def dashboard_endpoint() -> dict:
    return await dashboard_data()


@app.post("/api/model-config")
async def save_model_config(request: Request):
    """保存用户的模型来源配置（本地 Ollama / 云端 API）。"""
    import json

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "data", "model_settings.json")
    try:
        body = await request.json()
    except Exception:
        return {"ok": False, "error": "无效的请求体"}
    source = body.get("source", "local")
    if source not in ("local", "api"):
        source = "local"
    data = {
        "source": source,
        "api_base": str(body.get("api_base", "") or ""),
        "api_model": str(body.get("api_model", "") or ""),
        "api_key": str(body.get("api_key", "") or ""),
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return {"ok": True, "settings": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ===== OpenClaw 可操作 API（真实生效：写配置 / 调 CLI） =====

def _write_openclaw_json(cfg: dict) -> bool:
    """写回 openclaw.json（先自动备份）。"""
    import shutil

    try:
        shutil.copy(OPENCLAW_CONFIG_PATH, str(OPENCLAW_CONFIG_PATH) + ".bak")
    except Exception:
        pass
    try:
        with open(OPENCLAW_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


@app.get("/api/openclaw/mcp")
async def oc_mcp_list():
    """OpenClaw 已配置的 MCP 服务器（真实，来自 openclaw.json）。"""
    cfg = _load_openclaw_config()
    servers = (cfg.get("mcp") or {}).get("servers", {}) or {}
    items = []
    for name, s in servers.items():
        if not isinstance(s, dict):
            continue
        items.append({
            "name": name,
            "enabled": s.get("enabled", True),
            "command": s.get("command", ""),
            "args": s.get("args", []) or [],
            "env_keys": list((s.get("env") or {}).keys()),
        })
    return {"ok": True, "servers": items}


@app.post("/api/openclaw/mcp")
async def oc_mcp_add(request: Request):
    """新增 MCP 服务器（写入 openclaw.json，网关支持热重载）。"""
    body = await request.json()
    name = str(body.get("name", "")).strip()
    command = str(body.get("command", "")).strip()
    if not name or not command:
        return {"ok": False, "error": "name 和 command 必填"}
    cfg = _load_openclaw_config()
    servers = cfg.setdefault("mcp", {}).setdefault("servers", {})
    if name in servers:
        return {"ok": False, "error": f"MCP「{name}」已存在"}
    servers[name] = {
        "command": command,
        "args": body.get("args") or [],
        "env": body.get("env") or {},
        "enabled": True,
    }
    if not _write_openclaw_json(cfg):
        return {"ok": False, "error": "写入 openclaw.json 失败"}
    return {"ok": True, "name": name, "enabled": True}


@app.post("/api/openclaw/mcp/{name}/toggle")
async def oc_mcp_toggle(name: str):
    """启停 MCP 服务器（改 enabled，热重载）。"""
    cfg = _load_openclaw_config()
    servers = (cfg.get("mcp") or {}).get("servers", {}) or {}
    if name not in servers or not isinstance(servers[name], dict):
        return {"ok": False, "error": "MCP 不存在"}
    cur = bool(servers[name].get("enabled", True))
    servers[name]["enabled"] = not cur
    if not _write_openclaw_json(cfg):
        return {"ok": False, "error": "写入失败"}
    return {"ok": True, "name": name, "enabled": not cur}


@app.delete("/api/openclaw/mcp/{name}")
async def oc_mcp_delete(name: str):
    """删除 MCP 服务器。"""
    cfg = _load_openclaw_config()
    servers = (cfg.get("mcp") or {}).get("servers", {}) or {}
    if name not in servers:
        return {"ok": False, "error": "MCP 不存在"}
    del servers[name]
    if not _write_openclaw_json(cfg):
        return {"ok": False, "error": "写入失败"}
    return {"ok": True, "name": name}


@app.post("/api/openclaw/agent/identity")
async def oc_agent_identity(request: Request):
    """修改 OpenClaw agent 身份（名字/emoji，真实生效）。"""
    body = await request.json()
    agent = str(body.get("agent", "main") or "main")
    args = ["agents", "set-identity", "--agent", agent, "--json"]
    if body.get("name"):
        args += ["--name", str(body["name"])]
    if body.get("emoji"):
        args += ["--emoji", str(body["emoji"])]
    out = await asyncio.to_thread(_openclaw_cli, args, 45)
    return {"ok": out is not None, "result": out}


@app.get("/api/openclaw/cron")
async def oc_cron_list():
    out = await asyncio.to_thread(_openclaw_cli, ["cron", "list", "--json"], 45)
    return {"ok": out is not None, "cron": out or {}}


@app.post("/api/openclaw/cron")
async def oc_cron_add(request: Request):
    body = await request.json()
    schedule = str(body.get("schedule", "")).strip()
    message = str(body.get("message", "")).strip()
    if not schedule or not message:
        return {"ok": False, "error": "schedule 和 message 必填"}
    args = ["cron", "add", schedule, message, "--json"]
    if body.get("name"):
        args += ["--name", str(body["name"])]
    out = await asyncio.to_thread(_openclaw_cli, args, 45)
    return {"ok": out is not None, "result": out}


@app.post("/api/openclaw/cron/{cid}/toggle")
async def oc_cron_toggle(cid: str, request: Request):
    body = await request.json()
    sub = "enable" if body.get("enable") else "disable"
    out = await asyncio.to_thread(_openclaw_cli, ["cron", sub, cid, "--json"], 45)
    return {"ok": out is not None, "result": out}


@app.delete("/api/openclaw/cron/{cid}")
async def oc_cron_delete(cid: str):
    out = await asyncio.to_thread(_openclaw_cli, ["cron", "rm", cid, "--json"], 45)
    return {"ok": out is not None, "result": out}


@app.get("/api/openclaw/skills")
async def oc_skills_list():
    """磁盘直读技能目录（毫秒级），不调慢速 CLI。"""
    import glob as _glob

    skills = []
    for pat in ("skills/*/*/SKILL.md", "workspace/skills/*/SKILL.md", "workspace/skills/*/*/SKILL.md"):
        for f in _glob.glob(os.path.join(OPENCLAW_STATE_DIR, pat)):
            rel = os.path.relpath(f, OPENCLAW_STATE_DIR)
            parts = rel.split(os.sep)
            if "SKILL.md" not in parts:
                continue
            author = parts[1] if parts[0] == "skills" and len(parts) >= 3 else ""
            name = parts[2] if parts[0] == "skills" and len(parts) >= 3 else (parts[2] if len(parts) >= 3 else parts[1])
            skills.append({
                "name": name,
                "author": author,
                "path": rel,
                "enabled": True,
            })
    # 去重
    seen = set()
    uniq = []
    for s in skills:
        k = (s["name"], s["author"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(s)
    # 合并 agent 会话快照中的技能（捆绑/内置技能也在内）
    try:
        with open(os.path.join(OPENCLAW_STATE_DIR, "agents", "main", "sessions", "sessions.json"), "r", encoding="utf-8") as f:
            smap = json.load(f)
        for s in smap.values():
            for sk in (s.get("skillsSnapshot", {}) or {}).get("skills", []) or []:
                n = sk.get("name") if isinstance(sk, dict) else str(sk)
                if n and n not in seen:
                    seen.add(n)
                    uniq.append({"name": n, "author": "", "path": "", "enabled": True, "bundled": True})
    except Exception:
        pass
    return {"ok": True, "skills": uniq}


@app.get("/api/openclaw/logs")
async def oc_logs(limit: int = 120):
    """磁盘直读最新网关日志文件（毫秒级）。"""
    import glob as _glob

    # 优先网关运行日志，其次 logs 目录
    ordered = [
        r"C:\Users\a\Desktop\vibe coding\OpenClaw\data\gateway-start.log",
        r"C:\Users\a\Desktop\vibe coding\OpenClaw\gw.log",
        r"C:\Users\a\Desktop\vibe coding\OpenClaw\openclaw-gw.log",
        r"C:\Users\a\Desktop\vibe coding\OpenClaw\openclaw.log",
    ]
    cands = [c for c in ordered if os.path.exists(c)]
    if not cands:
        for pat in ("*.log", "logs/*.log", "logs/*.jsonl"):
            cands += _glob.glob(os.path.join(OPENCLAW_STATE_DIR, pat))
    cands = [c for c in cands if os.path.exists(c)]
    if not cands:
        return {"ok": False, "logs": [], "error": "no log files"}
    # 有候选：优先取 mtime 最新的 .log；若无 .log 再取 jsonl
    log_cands = [c for c in cands if c.lower().endswith(".log")]
    newest = max(log_cands if log_cands else cands, key=os.path.getmtime)
    try:
        with open(newest, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        lines = [l.rstrip("\n") for l in lines if l.strip()]
        lines = lines[-int(limit):]
        return {"ok": True, "logs": lines, "file": os.path.basename(newest)}
    except Exception as e:
        return {"ok": False, "logs": [], "error": str(e)}


@app.get("/api/openclaw/config")
async def oc_config_get():
    cfg = _load_openclaw_config()
    return {"ok": True, "config": cfg}


@app.post("/api/openclaw/config")
async def oc_config_patch(request: Request):
    """深度合并 patch 到 openclaw.json（真实生效，先备份）。"""
    body = await request.json()
    patch = body.get("patch")
    if not isinstance(patch, dict):
        return {"ok": False, "error": "patch 需为对象"}
    cfg = _load_openclaw_config()

    def _merge(d, p):
        for k, v in p.items():
            if isinstance(v, dict) and isinstance(d.get(k), dict):
                _merge(d[k], v)
            else:
                d[k] = v

    _merge(cfg, patch)
    if not _write_openclaw_json(cfg):
        return {"ok": False, "error": "写入失败"}
    return {"ok": True}


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


async def _periodic_ws_health() -> None:
    """每 10s 通过 WS 推送系统健康状态 + 告警评估。"""
    _logger = logging.getLogger("bluedeer.web")
    from core.alert import get_alert_engine

    ae = get_alert_engine()
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
        except Exception as _e:
            _logger.warning("WS 健康推送异常: %s", _e, exc_info=True)


# 挂载静态文件
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
# 精灵（game_frontend JS 请求 /sprites/<name>_sprite.png）
os.makedirs("static/sprites", exist_ok=True)
app.mount("/sprites", StaticFiles(directory="static/sprites"), name="sprites")
# new_ui：Agent-Rotary-Station 调度台（纯静态，仅调底座 API）
if os.path.isdir("new_ui"):
    app.mount("/new_ui", StaticFiles(directory="new_ui", html=True), name="new_ui")


# ===== 项目文件路由（仿 OpenClaw：本地文件经自身 web 路由提供，而非 file://）=====
# 控制台「文档 / 配置」里的文件链接统一指向 /repo/...，由本路由安全读取磁盘文件。
# 屏蔽敏感目录与文件，仅本地 127.0.0.1 暴露，避免源码/密钥外泄。
import mimetypes as _mimetypes
from fastapi.responses import FileResponse, Response

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_REPO_BLOCKED_DIRS = {
    ".venv", "data", ".git", "backups", ".workbuddy", "__pycache__",
    "node_modules", ".idea", ".vscode", "odysseus", "memory_archive",
}
_REPO_BLOCKED_NAMES = {".env", "secrets.json", "credentials.json", ".gitignore"}
_REPO_BLOCKED_EXT = {".db", ".sqlite", ".sqlite3", ".pyc", ".pem", ".key", ".pkl"}


@app.get("/repo/{file_path:path}")
async def serve_repo_file(file_path: str):
    """安全读取 BlueDeer 项目内文件（文档 / 配置 / 源码），屏蔽敏感路径。"""
    norm = os.path.normpath(file_path).replace("\\", "/")
    if norm.startswith("..") or os.path.isabs(norm) or norm.startswith("/"):
        return Response("forbidden", status_code=403)
    parts = norm.split("/")
    if any(p in _REPO_BLOCKED_DIRS for p in parts):
        return Response("forbidden", status_code=403)
    if parts[-1] in _REPO_BLOCKED_NAMES:
        return Response("forbidden", status_code=403)
    _, ext = os.path.splitext(parts[-1])
    if ext.lower() in _REPO_BLOCKED_EXT:
        return Response("forbidden", status_code=403)
    full = os.path.join(_REPO_ROOT, norm)
    if not os.path.isfile(full):
        return Response("not found", status_code=404)
    return FileResponse(
        full,
        media_type=_mimetypes.guess_type(full)[0] or "application/octet-stream",
        filename=parts[-1],
    )


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
# 管理员初始密码不再硬编码：优先环境变量，其次 vault（首次登录强制改密）
ADMIN_PASS = os.environ.get("BLUEDEER_ADMIN_INIT_PASS", "") or ""
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
from .routes_agents import router as _agents_router
from .routes_alerts import router as _alerts_router
from .routes_dag import router as _dag_router
from .routes_misc import router as _misc_router
from .routes_pages import router as _pages_router
from .routes_plugins import router as _plugins_router
from .routes_system import router as _system_router
from .routes_traces import router as _traces_router
from .routes_users import router as _users_router
from .routes_vector import router as _vector_router
from .routes_ui import router as _ui_router

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
app.include_router(_ui_router)



# ---- 安全加固中间件：安全响应头 + 请求体大小限制 ----
_APP_MAX_BODY_BYTES = int(os.environ.get("BLUEDEER_MAX_BODY_MB", "10")) * 1024 * 1024


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    # 请求体大小限制：超过阈值直接拒绝（避免超大 JSON 拖垮服务）
    content_length = request.headers.get("content-length", "")
    if content_length.isdigit() and int(content_length) > _APP_MAX_BODY_BYTES:
        return Response(
            content='{"error": "请求体过大"}',
            status_code=413,
            media_type="application/json",
        )
    response = await call_next(request)
    # 基础安全响应头
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("X-XSS-Protection", "1; mode=block")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    # 内容安全策略：仅允许本域 + 内联样式/脚本（项目为纯原生前端，无外部框架）
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self' data:; "
        "connect-src 'self'",
    )
    return response
