"""BlueDeer 森林生物圈 — 集成到 FastAPI 的 Game Router。

把 game_server.py 的所有路由搬到这里，作为 FastAPI APIRouter
挂载到 /game/，和 web_server 同进程同端口 8080。
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

# ── 负载均衡状态 ──
_server_loads: dict[str, float] = {}           # server_id -> 当前负载因子
_server_capacity: dict[str, int] = {}          # server_id -> 最大玩家数
_backup_servers: list[str] = []                # 备用 server id 列表

logger = logging.getLogger("bluedeer.game")

router = APIRouter(prefix="/game", tags=["生物圈游戏"])

# ── Biosphere 全局实例（由 web_server 的 startup 事件初始化） ──
_biosphere: Any = None
_biosphere_lock = threading.Lock()
_biosphere_ready = threading.Event()


def init_biosphere(biosphere: Any) -> None:
    global _biosphere
    _biosphere = biosphere
    _biosphere_ready.set()
    logger.info("生物圈已连接到 Web 服务器")


def get_biosphere() -> Any:
    if _biosphere is None:
        raise HTTPException(status_code=503, detail="生物圈尚未初始化")
    return _biosphere


# ── HTML 页面 ──

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def game_index():
    """主游戏页面（2D 俯视角）。"""
    from game_frontend import render_index
    return HTMLResponse(content=render_index())


@router.get("/map", response_class=HTMLResponse)
async def game_map():
    """2.5D 地图页面。"""
    from game_frontend import render_index
    return HTMLResponse(content=render_index())


@router.get("/console", response_class=HTMLResponse)
async def game_console():
    """极简控制台页面。"""
    from console_frontend import render_index
    return HTMLResponse(content=render_index())


@router.get("/report", response_class=HTMLResponse)
async def game_report():
    """进化报告页面。"""
    bio = get_biosphere()
    report_text = bio.evolution_report()
    safe_text = _escape_html(report_text)
    return HTMLResponse(content=_make_text_page("进化报告", "Evolution Report", safe_text))


@router.get("/story", response_class=HTMLResponse)
async def game_story():
    """故事章节页面。"""
    bio = get_biosphere()
    story_text = bio.story_text(n=50)
    safe_text = _escape_html(story_text)
    return HTMLResponse(content=_make_text_page("故事章节", "Chronicles", safe_text))


@router.get("/snap", response_class=HTMLResponse)
async def game_snap():
    """快照页面。"""
    bio = get_biosphere()
    snap = bio.evolution.take_snapshot()
    save_result = bio.save()
    snap_html = f"<pre>{_escape_html(json.dumps(snap, ensure_ascii=False, indent=2))}</pre>"
    save_html = f"<p>存档: {'✅' if save_result.get('ok') else '❌'} {save_result.get('path','')}</p>"
    return HTMLResponse(content=_make_text_page("生态快照", "Snapshot", snap_html + save_html))


# ── API ──

@router.get("/api/status")
async def api_status():
    """实时生物圈状态。"""
    bio = get_biosphere()
    with _biosphere_lock:
        return bio.status()


@router.get("/api/story")
async def api_story(since: float = Query(0.0, description="只返回此时间戳之后的故事")):
    bio = get_biosphere()
    stories = bio.story_text(n=50)
    return {"stories": stories, "count": 1, "since": since}


@router.get("/api/report")
async def api_report():
    bio = get_biosphere()
    text = bio.evolution_report()
    return {"report": text, "generated_at": time.time()}


@router.get("/api/snap")
async def api_snap():
    bio = get_biosphere()
    snap = bio.evolution.take_snapshot()
    bio.save()
    return {"snap": snap, "ok": True}


@router.post("/api/inject")
async def api_inject(request: Request):
    bio = get_biosphere()
    body = await request.json()
    task_type = body.get("type", "general")
    payload = body.get("payload", {})
    try:
        result = bio.tasks.inject_task(task_type, payload)
        return {"ok": True, "task_id": result.get("id", "")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/interact")
async def api_interact(request: Request):
    bio = get_biosphere()
    body = await request.json()
    name = body.get("name", "")
    action = body.get("action", "pat")
    try:
        result = bio.env.interact(name, action)
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/api/zones")
async def api_zones():
    from game_frontend import ZONES
    return {"zones": ZONES, "count": len(ZONES)}


@router.get("/api/eco")
async def api_eco():
    bio = get_biosphere()
    return bio.env.ecology_summary() if hasattr(bio.env, "ecology_summary") else {}


@router.get("/api/emotions")
async def api_emotions():
    bio = get_biosphere()
    data = {}
    for eid, emp in bio.env.employees.items():
        data[emp.name] = {
            "emotion": getattr(emp, "emotion", "平静"),
            "energy": getattr(emp, "energy", 100),
            "mood": getattr(emp, "mood", 0.5),
        }
    return {"emotions": data}


@router.get("/api/relationships")
async def api_relationships():
    bio = get_biosphere()
    rels = getattr(bio.env, "relationships", {})
    return {"relationships": rels}


@router.get("/api/events")
async def api_events():
    bio = get_biosphere()
    events = getattr(bio.env, "event_log", [])
    return {"events": events[-50:]}


@router.get("/api/messages")
async def api_messages():
    bio = get_biosphere()
    msgs = getattr(bio.env, "messages", [])
    return {"messages": msgs[-30:]}


@router.get("/api/memoir")
async def api_memoir():
    bio = get_biosphere()
    from core.digital_life import MemoryArchive
    archive = MemoryArchive()
    entries = archive.recent(20)
    return {"memoir": entries}


@router.get("/api/tasks")
async def api_tasks():
    bio = get_biosphere()
    tasks = getattr(bio.tasks, "pending", []) + getattr(bio.tasks, "completed", [])
    return {"tasks": tasks[-30:]}


@router.get("/api/recruit-status")
async def api_recruit_status():
    bio = get_biosphere()
    rs = getattr(bio, "recruit_system", None)
    if rs is None:
        return {"recruiting": False, "message": "招募系统未启用"}
    return rs.status() if hasattr(rs, "status") else {"recruiting": False}


@router.post("/api/recruit")
async def api_recruit():
    bio = get_biosphere()
    rs = getattr(bio, "recruit_system", None)
    if rs is None:
        return {"ok": False, "error": "招募系统未启用"}
    try:
        result = rs.start_recruiting()
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/api/evolution")
async def api_evolution():
    bio = get_biosphere()
    evo = getattr(bio, "evolution", None)
    if evo is None:
        return {"evolution": []}
    return {"evolution": evo.get_history() if hasattr(evo, "get_history") else []}


@router.get("/api/diary")
async def api_diary():
    bio = get_biosphere()
    diaries = []
    for eid, emp in bio.env.employees.items():
        d = getattr(emp, "diary", None)
        if d:
            diaries.append({"name": emp.name, "diary": d[-5:]})
    return {"diaries": diaries}


@router.get("/api/health")
async def api_health():
    """生物圈健康检查。"""
    bio = get_biosphere()
    emp_count = len(getattr(bio.env, "employees", {}))
    uptime = time.time() - getattr(bio, "_start_time", time.time())
    return {
        "status": "ok",
        "employees": emp_count,
        "uptime_seconds": round(uptime),
        "saving": getattr(bio, "_save_path", ""),
    }


# ── 辅助函数 ──

# ── 负载均衡接口 ──

def register_server(server_id: str, capacity: int = 100, load: float = 0.0) -> None:
    """注册游戏服务器。"""
    _server_capacity[server_id] = capacity
    _server_loads[server_id] = load

def update_load(server_id: str, load: float) -> None:
    """更新服务器负载因子（0.0 ~ 1.0）。"""
    _server_loads[server_id] = load

def set_backups(backups: list[str]) -> None:
    """设置备用服务器列表。"""
    _backup_servers.clear()
    _backup_servers.extend(backups)

def route_to_best(game_id: str, players: int) -> str | None:
    """选负载最低的可用服务器。
    Args:
        game_id: 游戏标识（预留）。
        players: 玩家人数（容量检查用）。
    Returns:
        server_id 或 None（无可用服务器）。
    """
    _ = game_id
    best: str | None = None
    best_load: float = 1.0
    for sid, load in _server_loads.items():
        cap = _server_capacity.get(sid, 100)
        if players > cap:
            continue
        if load < best_load:
            best_load = load
            best = sid
    return best

def fallback_handler(game_id: str) -> str | None:
    """主服务器不可用时的故障转移。
    Args:
        game_id: 游戏标识（预留）。
    Returns:
        备用服务器 id 或 None。
    """
    _ = game_id
    if _backup_servers:
        return _backup_servers[0]
    return None

def _escape_html(text: str) -> str:
    import html as _html
    return _html.escape(str(text))


def _make_text_page(title: str, subtitle: str, body: str) -> str:
    return f"""<!DOCTYPE html><html lang='zh-CN'><head>
<meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>BlueDeer · {title}</title>
<link rel='preconnect' href='https://fonts.googleapis.com'>
<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>
<link href='https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500&family=Manrope:wght@400;500&family=JetBrains+Mono&display=swap' rel='stylesheet'>
<style>
:root{{--bg:#0d1410;--card:rgba(22,31,26,.78);--border:rgba(212,165,116,.18);--text:#E8E4D8;--muted:#A8A095;--accent:#D4A574;}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Manrope',sans-serif;background:var(--bg);background-image:radial-gradient(ellipse 70% 50% at 50% 0%,rgba(107,143,113,.06),transparent),linear-gradient(180deg,#0d1410 0%,#0a0f0c 100%);color:var(--text);min-height:100vh;padding:48px 24px}}
.wrap{{max-width:880px;margin:0 auto}}
.head{{display:flex;align-items:baseline;gap:14px;margin-bottom:32px;padding-bottom:16px;border-bottom:1px solid var(--border)}}
.back{{color:var(--muted);text-decoration:none;font-size:12px;letter-spacing:.04em;transition:color .2s}}
.back:hover{{color:var(--accent)}}
h1{{font-family:'Fraunces',serif;font-weight:500;font-size:28px;letter-spacing:.01em;color:var(--text)}}
.sub{{color:var(--muted);font-size:11px;letter-spacing:.16em;text-transform:uppercase;margin-left:auto}}
pre{{font-family:'JetBrains Mono',monospace;font-size:13px;line-height:1.7;background:var(--card);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border:1px solid var(--border);border-radius:12px;padding:28px 32px;white-space:pre-wrap;color:var(--text);box-shadow:0 8px 32px rgba(0,0,0,.3)}}
@media(max-width:720px){{body{{padding:24px 14px}}pre{{padding:18px 16px;font-size:12px}}.sub{{display:none}}}}
</style></head><body>
<div class='wrap'><div class='head'><a class='back' href='/game'>← 返回</a><h1>{title}</h1><span class='sub'>{subtitle}</span></div><pre>{body}</pre></div></body></html>"""
