# 自动拆分自 web_server.py（路由域: agents）
import logging

# ruff: noqa: F821

logger = logging.getLogger(__name__)
from fastapi import APIRouter

from web_server.app import (
    app,
)

router = APIRouter()


@router.get("/api/agents")
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


@router.get("/api/agents/search")
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


@router.get("/api/agents/{name}")
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


@router.get("/api/agents/{name}/enable")
async def enable_agent(name: str) -> dict[str, Any]:
    _ensure_agent_registry()
    ok = app.state.agent_registry.set_enabled(name, True)
    return {"success": ok, "name": name}


@router.get("/api/agents/{name}/disable")
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


@router.get("/api/agents/health")
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


@router.get("/api/agents/{name}/health")
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


@router.post("/api/agents/refresh")
async def agent_refresh() -> dict[str, Any]:
    from core.agent_market import get_market

    get_market().refresh_from_registry()
    return {"ok": True}


@router.get("/api/agents/stats/all")
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
