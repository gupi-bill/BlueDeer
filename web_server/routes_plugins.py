# 自动拆分自 web_server.py（路由域: plugins）
import logging

logger = logging.getLogger(__name__)
from typing import Any

from fastapi import APIRouter

from web_server.app import (
    app,
    plugin_manager,
)

router = APIRouter()


@router.get("/api/plugins")
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


@router.get("/api/plugins/{name}/enable")
async def enable_plugin(name: str) -> dict[str, Any]:
    ok = plugin_manager.enable(name)
    return {"success": ok, "name": name}


@router.get("/api/plugins/{name}/disable")
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
        logger.exception("Exception in block")
    _agent_registry_loaded = True


@router.get("/api/plugins/search")
async def plugin_search(query: str = "", max_results: int = 20) -> dict[str, Any]:
    from web_server.routes_misc import _get_plugin_repo
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


@router.post("/api/plugins/install-git")
async def plugin_install_git(body: dict[str, Any]) -> dict[str, Any]:
    from web_server.routes_misc import _get_plugin_repo
    repo = _get_plugin_repo()
    ok, msg = repo.install_from_git(
        url=body.get("url", ""),
        branch=body.get("branch", "main"),
        target_name=body.get("name", ""),
    )
    return {"success": ok, "message": msg}


@router.post("/api/plugins/uninstall")
async def plugin_uninstall(body: dict[str, Any]) -> dict[str, Any]:
    from web_server.routes_misc import _get_plugin_repo
    repo = _get_plugin_repo()
    ok, msg = repo.uninstall(body.get("name", ""))
    return {"success": ok, "message": msg}


# ── DAG API ──
