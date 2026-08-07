# 自动拆分自 web_server.py（路由域: system）
import logging

logger = logging.getLogger(__name__)
from fastapi import APIRouter

from web_server.app import (
    harness,
    jarvis,
    scene,
)

router = APIRouter()


@router.get("/api/system/health")
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
        logger.exception("Exception in block")
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


@router.get("/api/rag/stats")
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


@router.get("/api/rewards/leaderboard")
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


@router.get("/api/cleanup/stats")
async def cleanup_stats() -> dict[str, Any]:
    from core.cleanup import get_storage_stats

    return get_storage_stats()


@router.post("/api/cleanup/run")
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


@router.get("/api/backups")
async def list_backups_api() -> dict[str, Any]:
    from core.backup import list_backups

    return {"backups": list_backups()}


@router.post("/api/backups")
async def create_backup_api(request: Request) -> dict[str, Any]:
    from core.backup import create_backup

    body = (
        await request.json()
        if request.headers.get("content-type", "").startswith("application/json")
        else {}
    )
    path = create_backup(name=body.get("name", ""), db_only=body.get("db_only", False))
    return {"ok": True, "path": path}


@router.post("/api/backups/restore")
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


@router.delete("/api/backups/{filename}")
async def delete_backup_api(filename: str) -> dict[str, Any]:
    from core.backup import delete_backup

    ok = delete_backup(filename)
    return {"ok": ok}


@router.get("/api/status")
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


@router.get("/api/scene")
async def get_scene() -> dict[str, Any]:
    """获取全场景数据。"""
    return scene.to_dict()


@router.get("/api/jarvis")
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


@router.get("/api/github")
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
