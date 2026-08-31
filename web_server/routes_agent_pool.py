# -*- coding: utf-8 -*-
"""Agent 池管理 API：多实例、健康检查、自动故障切换。"""

import json
import logging
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from web_server.app import app

logger = logging.getLogger("bluedeer.agent_pool")

router = APIRouter(prefix="/agent-pool")

# 池配置路径
_POOL_CONFIG_PATH = Path(__file__).parent.parent / "agent" / "agent_pool.json"


def _get_pool():
    """延迟导入，避免循环依赖。"""
    from .routes_agent_pool_core import get_pool
    return get_pool()


# ===== 实例列表 =====
@router.get("/instances", summary="获取所有 Agent 实例")
async def pool_list_instances():
    pool = _get_pool()
    instances = [a.to_dict() for a in pool.list_all()]
    current = pool.current_id
    return {"instances": instances, "current_id": current}


@router.get("/current", summary="获取当前活跃的 Agent")
async def pool_get_current():
    pool = _get_pool()
    agent = pool.current
    if agent:
        return {"instance": agent.to_dict()}
    return JSONResponse({"error": "没有可用的 Agent"}, status_code=404)


# ===== 切换 Agent =====
@router.post("/switch", summary="切换到指定 Agent")
async def pool_switch(request: Request):
    body = await request.json() if request.body else {}
    agent_id = body.get("id", "")
    pool = _get_pool()
    if agent_id and pool.switch(agent_id):
        # 持久化
        _save_config(pool)
        return {"ok": True, "current_id": agent_id}
    return JSONResponse({"error": "Agent 不存在"}, status_code=404)


@router.post("/switch/next", summary="自动切换到下一个健康 Agent")
async def pool_switch_next():
    pool = _get_pool()
    new_id = pool.switch_next_healthy()
    _save_config(pool)
    agent = pool.get(new_id) if new_id else None
    return {"ok": True, "current_id": new_id, "instance": agent.to_dict() if agent else None}


# ===== 执行任务 =====
@router.post("/run", summary="在当前 Agent 上执行任务")
async def pool_run(request: Request):
    body = await request.json() if request.body else {}
    task = body.get("task", "")
    agent_id = body.get("agent_id")  # 可选，不传则用当前
    max_steps = int(body.get("max_steps", 10))

    if not task:
        return JSONResponse({"error": "task 不能为空"}, status_code=400)

    pool = _get_pool()

    # 记录开始
    ts_start = time.time()

    try:
        result = pool.run_task(agent_id, task, max_steps)
        result["elapsed"] = round(time.time() - ts_start, 2)
        return result
    except Exception as e:
        pool.record_error()
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ===== 健康状态 =====
@router.get("/health", summary="获取 Agent 池健康状态")
async def pool_health():
    pool = _get_pool()
    instances = [a.to_dict() for a in pool.list_all()]
    stats = {
        "total": len(instances),
        "online": sum(1 for a in instances if a["status"] == "online"),
        "busy": sum(1 for a in instances if a["status"] == "busy"),
        "error": sum(1 for a in instances if a["status"] == "error"),
        "offline": sum(1 for a in instances if a["status"] == "offline"),
    }
    return {"pool_stats": stats, "instances": instances, "current_id": pool.current_id}


# ===== 配置管理 =====
@router.get("/config", summary="获取池配置")
async def pool_get_config():
    pool = _get_pool()
    return {
        "auto_failover": pool._auto_failover,
        "failover_timeout": pool._failover_timeout,
        "config_path": str(_POOL_CONFIG_PATH),
    }


@router.post("/config", summary="更新池配置")
async def pool_update_config(request: Request):
    body = await request.json() if request.body else {}
    pool = _get_pool()
    if "auto_failover" in body:
        pool._auto_failover = bool(body["auto_failover"])
    if "failover_timeout" in body:
        pool._failover_timeout = int(body["failover_timeout"])
    _save_config(pool)
    return {"ok": True}


@router.post("/config/save", summary="保存配置到文件")
async def pool_save_config():
    pool = _get_pool()
    _save_config(pool)
    return {"ok": True, "path": str(_POOL_CONFIG_PATH)}


# ===== 场景筛选 =====
@router.get("/scenes", summary="按场景筛选 Agent")
async def pool_by_scene(scene: str = ""):
    pool = _get_pool()
    if not scene:
        return {"instances": [a.to_dict() for a in pool.list_all()]}
    filtered = [a.to_dict() for a in pool.list_all() if a.scene == scene]
    return {"scene": scene, "instances": filtered}


# ===== 工具函数 =====
def _save_config(pool):
    """持久化 Agent 池配置到 JSON 文件。"""
    try:
        data = {
            "agents": [a.to_dict() for a in pool.list_all()],
            "current_id": pool.current_id,
            "auto_failover": pool._auto_failover,
            "failover_timeout": pool._failover_timeout,
        }
        _POOL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _POOL_CONFIG_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        logger.error("保存配置失败: %s", e)


# 路由注册
app.include_router(router)
logger.info("Agent 池路由已注册: /agent-pool/*")
