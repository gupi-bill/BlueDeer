# -*- coding: utf-8 -*-
"""BlueDeer Agent 底座 — FastAPI 路由集成。

将 agent 子项目的 REST API 集成到主控制台（同一端口）。
前端 console/ 通过相对路径 /agent/ 调用。
"""

import asyncio
import logging
import os
import sys
import threading

from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse

# 导入 agent 核心模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))
from bluedeer.server import (
    STORE,
    Api,
    build_stats,
    dispatch,
    load_config,
    probe_models,
    seed_agents_from_roles,
    usage_report,
)
from bluedeer.config import ROOT_DIR

logger = logging.getLogger("bluedeer.agent_routes")

router = APIRouter(prefix="/agent")

# 全局 API 实例（由 app.py 的 startup 事件初始化）
_api_instance: Api | None = None


def get_api() -> Api:
    global _api_instance
    if _api_instance is None:
        cfg = load_config()
        _api_instance = Api(cfg)
        seed_agents_from_roles(cfg)
    return _api_instance


def init_agent_scheduler():
    """在 app 启动时调用，初始化 agent 底座并启动调度线程。"""
    cfg = load_config()
    global _api_instance
    _api_instance = Api(cfg)
    seed_agents_from_roles(cfg)
    logger.info("Agent 底座已初始化，角色已种子")


# ==================== system 路由 ====================

@router.get("/", summary="底座根信息")
async def agent_root():
    return {"version": "1.0.0", "name": "BlueDeer 底座"}


@router.get("/system/stats", summary="系统统计")
async def agent_stats():
    api = get_api()
    stats = build_stats(api.cfg)
    return {"stats": stats}


@router.get("/system/usage", summary="使用报告")
async def agent_usage():
    api = get_api()
    return usage_report(api.cfg)


@router.get("/system/settings", summary="获取设置")
async def agent_settings_get():
    api = get_api()
    from bluedeer.config import DEFAULT_CONFIG, get_env
    keys = ["provider", "ollama_model", "ollama_base_url", "trace", "role",
            "roles_dir", "system_prompt", "server_host", "server_port",
            "api_base", "api_model"]
    s = {k: api.cfg.get(k, DEFAULT_CONFIG.get(k)) for k in keys}
    s["api_key_set"] = bool(api.cfg.get("api_key") or get_env("BLUEDEER_API_KEY"))
    return {"settings": s}


@router.post("/system/settings", summary="更新设置")
async def agent_settings_post(request: Request):
    api = get_api()
    from bluedeer.config import load_config, save_config
    body = await request.json() if request.body else {}
    allowed = {"provider", "ollama_model", "ollama_base_url", "trace", "role",
               "roles_dir", "system_prompt", "default_auto_reply_template",
               "api_base", "api_key", "api_model"}
    changed = []
    fresh = load_config()
    for k, v in (body or {}).items():
        if k in allowed and v is not None:
            api.cfg[k] = v
            fresh[k] = v
            changed.append(k)
    STORE.audit("human", "settings.update", {"keys": changed})
    STORE.save()
    if set(changed) & {"provider", "ollama_model", "ollama_base_url",
                       "api_base", "api_key", "api_model"}:
        api.agent = type(api.agent)(api.cfg)
    save_config(fresh)
    return {"ok": True, "changed": changed}


@router.get("/system/audit-logs", summary="审计日志")
async def agent_audit_logs(limit: int = Query(50), actor: str = Query("")):
    logs = STORE.data["audit_logs"]
    if actor:
        logs = [l for l in logs if l.get("actor") == actor]
    return {"logs": logs[-limit:][::-1]}


@router.post("/system/emergency-block/toggle", summary="紧急刹车开关")
async def agent_emergency_toggle(active: str = Query("")):
    want = active.lower()
    cur = bool(STORE.data["emergency_block"])
    nxt = (want == "true") if want else (not cur)
    STORE.data["emergency_block"] = nxt
    STORE.audit("human", "emergency_block.toggle", {"active": nxt})
    STORE.save()
    return {"ok": True, "emergency_block": nxt}


@router.get("/system/probe-models", summary="探测可用模型")
async def agent_probe_models(api_base: str = Query(""), api_key: str = Query("")):
    return probe_models(api_base, api_key)


# ==================== agents 路由 ====================

@router.get("/agents", summary="Agent 列表")
async def agent_list():
    api = get_api()
    import time
    ags = list(STORE.data["agents"].values())
    now = int(time.time())
    for a in ags:
        a["last_seen"] = a.get("last_seen") or 0
        a["status"] = "online" if a["last_seen"] and now - int(a["last_seen"]) <= 600 else "offline"
    return {"agents": ags}


@router.post("/agents/register", summary="注册 Agent")
async def agent_register(request: Request):
    api = get_api()
    body = await request.json() if request.body else {}
    aid = (body or {}).get("agent_id", "").strip()
    if not aid:
        return JSONResponse({"detail": "agent_id 不能为空"}, status_code=400)
    from bluedeer.roles import list_roles, load_role
    existed = aid in STORE.data["agents"]
    rec = STORE.data["agents"].get(aid, {})
    rec.update({
        "agent_id": aid,
        "name": body.get("name") or aid,
        "role": body.get("role") or "worker",
        "capabilities": body.get("capabilities") or [],
        "system_prompt": body.get("system_prompt") or rec.get("system_prompt") or "",
        "auto_reply": body.get("auto_reply") or rec.get("auto_reply") or {"enabled": False},
        "status": "online", "last_seen": int(time.time()),
        "created_at": rec.get("created_at", int(time.time())),
    })
    STORE.data["agents"][aid] = rec
    STORE.audit("human", "agents.register", {"agent_id": aid})
    STORE.save()
    return {"ok": True, "registered_before": existed, "agent": rec}


@router.get("/agents/{agent_id}", summary="Agent 详情")
async def agent_detail(agent_id: str):
    api = get_api()
    import time
    rec = STORE.data["agents"].get(agent_id)
    if rec is None:
        from bluedeer.roles import list_roles, load_role
        roles = list_roles(api.cfg.get("roles_dir") or "")
        if agent_id in roles:
            r = load_role(api.cfg.get("roles_dir") or "", agent_id)
            rec = {"agent_id": agent_id, "name": agent_id, "role": "worker",
                   "capabilities": ["内置角色"], "system_prompt": r.system_prompt,
                   "auto_reply": {"enabled": False}, "status": "online", "last_seen": int(time.time())}
        else:
            return JSONResponse({"detail": "Agent 不存在"}, status_code=404)
    return {"agent": rec}


@router.post("/agents/{agent_id}/update", summary="更新 Agent")
async def agent_update(agent_id: str, request: Request):
    api = get_api()
    body = await request.json() if request.body else {}
    rec = STORE.data["agents"].get(agent_id)
    if rec is None:
        return JSONResponse({"detail": "Agent 不存在"}, status_code=404)
    if "system_prompt" in (body or {}):
        rec["system_prompt"] = body["system_prompt"]
    STORE.audit("human", "agents.update", {"agent_id": agent_id})
    STORE.save()
    return {"ok": True, "agent": rec}


@router.post("/agents/{agent_id}/autoreply", summary="自动回复设置")
async def agent_autoreply(agent_id: str, request: Request):
    api = get_api()
    body = await request.json() if request.body else {}
    rec = STORE.data["agents"].get(agent_id)
    if rec is None:
        return JSONResponse({"detail": "Agent 不存在"}, status_code=404)
    ar = rec.setdefault("auto_reply", {})
    if "enabled" in (body or {}):
        ar["enabled"] = bool(body["enabled"])
    if body.get("reply_template") is not None:
        ar["reply_template"] = body.get("reply_template") or ""
    STORE.audit("human", "agents.autoreply", {"agent_id": agent_id, "enabled": ar.get("enabled")})
    STORE.save()
    return {"ok": True, "auto_reply": ar}


@router.get("/agents/manager/current", summary="当前管理岗")
async def agent_manager_current():
    aid = STORE.data["manager"]
    if not aid or aid not in STORE.data["agents"]:
        return {"manager": None}
    return {"manager": STORE.data["agents"][aid]}


@router.post("/agents/manager/set", summary="设置管理岗")
async def agent_manager_set(request: Request):
    body = await request.json() if request.body else {}
    aid = (body or {}).get("agent_id", "")
    if aid not in STORE.data["agents"]:
        return JSONResponse({"detail": "Agent 不存在"}, status_code=404)
    STORE.data["manager"] = aid
    STORE.audit("human", "manager.set", {"agent_id": aid})
    STORE.save()
    return {"ok": True, "manager": aid}


@router.post("/agents/manager/clear", summary="撤销管理岗")
async def agent_manager_clear():
    STORE.data["manager"] = None
    STORE.audit("human", "manager.clear", None)
    STORE.save()
    return {"ok": True}


@router.post("/agents/delegate", summary="委托任务")
async def agent_delegate(request: Request):
    api = get_api()
    body = await request.json() if request.body else {}
    frm = (body or {}).get("from_agent", "")
    to = (body or {}).get("to_agent", "")
    task = (body or {}).get("task_content", "").strip()
    if to not in STORE.data["agents"]:
        from bluedeer.roles import list_roles
        roles = list_roles(api.cfg.get("roles_dir") or os.path.join(ROOT_DIR, "roles"))
        if to not in roles:
            return JSONResponse({"detail": "目标 Agent 不存在"}, status_code=404)
    if not task:
        return JSONResponse({"detail": "任务内容不能为空"}, status_code=400)
    target = STORE.data["agents"].get(to, {})
    if target.get("auto_reply", {}).get("enabled"):
        tpl = target["auto_reply"].get("reply_template") or "收到，{from}。任务「{task}」已受理，正在处理…"
        reply = tpl.replace("{from}", frm).replace("{task}", task[:60])
    else:
        from bluedeer.agent import BlueDeerAgent
        agent = BlueDeerAgent(dict(api.cfg, system_prompt=target.get("system_prompt") or ""))
        reply = agent.run(task)
    if to in STORE.data["agents"]:
        import time
        STORE.data["agents"][to]["last_seen"] = int(time.time())
    STORE.add_message("private", frm, to, task)
    STORE.add_message("private", to, frm, reply)
    STORE.audit(frm, "delegate.to", {"to": to, "chars": len(reply)})
    STORE.save()
    return {"status": "replied" if reply != "[安全拦截]" else "blocked", "reply": reply}


# ==================== messages 路由 ====================

@router.get("/messages/history", summary="消息历史")
async def msg_history(from_agent: str = Query(""), to_agent: str = Query(""), limit: int = Query(80)):
    msgs = STORE.data["messages"]
    if from_agent:
        msgs = [m for m in msgs if m["from_agent"] == from_agent]
    if to_agent:
        msgs = [m for m in msgs if m["to_agent"] == to_agent]
    return {"messages": msgs[-limit:]}


@router.post("/messages/send", summary="发送消息")
async def msg_send(request: Request):
    if STORE.data["emergency_block"]:
        return JSONResponse({"detail": "紧急刹车已开启，消息被拦截"}, status_code=403)
    body = await request.json() if request.body else {}
    msg = STORE.add_message(body.get("channel_type"), body.get("from_agent", "human"),
                            body.get("to_agent", ""), body.get("content", ""), body.get("task_id"))
    STORE.audit(msg["from_agent"], "message.send", {"to": msg["to_agent"]})
    STORE.save()
    return {"ok": True, "message": msg}


# ==================== memories 路由 ====================

@router.get("/memories/list-domains", summary="记忆域名列表")
async def mem_domains():
    doms = sorted({m.get("domain", "") for m in STORE.data["memories"]} |
                  {a.get("domain", "") for a in STORE.data["memory_approvals"] if a.get("status") == "pending"})
    return {"domains": [d for d in doms if d]}


@router.get("/memories/read", summary="读取记忆")
async def mem_read(domain: str = Query("")):
    items = [m for m in STORE.data["memories"] if m.get("domain") == domain]
    return {"domain": domain, "items": items}


@router.post("/memories/write", summary="写入记忆")
async def mem_write(request: Request):
    import time, os
    body = await request.json() if request.body else {}
    item = {"id": "mem_%d_%s" % (int(time.time()), os.urandom(3).hex()),
            "reader": body.get("reader", "human"),
            "domain": body.get("domain", "default"),
            "content": body.get("content", ""),
            "status": "approved",
            "requested_by": body.get("reader", "human"), "created_at": int(time.time())}
    STORE.data["memories"].append(item)
    STORE.audit(item["reader"], "memory.write", {"domain": item["domain"]})
    STORE.save()
    return {"ok": True, "item": item}


@router.post("/memories/delete", summary="删除记忆")
async def mem_delete(request: Request):
    body = await request.json() if request.body else {}
    before = len(STORE.data["memories"])
    STORE.data["memories"] = [m for m in STORE.data["memories"]
                              if not (m.get("domain") == body.get("domain") and m.get("content") == body.get("content"))]
    STORE.audit("human", "memory.delete", {"removed": before - len(STORE.data["memories"])})
    STORE.save()
    return {"ok": True}


@router.get("/memories/approvals/pending", summary="待审批记忆")
async def approvals_pending():
    pend = [a for a in STORE.data["memory_approvals"] if a.get("status") == "pending"]
    return {"pending": [{
        "request_id": a.get("id"),
        "agent_id": a.get("requested_by") or a.get("reader") or "?",
        "domain": a.get("domain", ""), "action": a.get("action", "write"),
        "content": a.get("content", ""), "created_at": a.get("created_at"),
    } for a in pend]}


@router.post("/memories/approvals/decide", summary="审批记忆")
async def approval_decide_memory(request: Request):
    body = await request.json() if request.body else {}
    rid = body.get("request_id", "")
    decision = "approve" if body.get("approve") else "reject"
    bucket = STORE.data["memory_approvals"]
    for item in bucket:
        if item.get("id") == rid and item.get("status") == "pending":
            item["status"] = decision
            if decision == "approve":
                STORE.data["memories"].append({
                    "id": item["id"], "reader": item.get("reader", ""),
                    "domain": item.get("domain", ""), "content": item.get("content", ""),
                    "status": "approved", "requested_by": item.get("requested_by"),
                    "created_at": int(time.time())})
            actor = body.get("manager_id") or "human"
            STORE.audit(actor, "memory_approval." + decision, {"id": rid})
            STORE.save()
            return {"ok": True, "decision": decision}
    return JSONResponse({"detail": "审批不存在或已处理"}, status_code=404)


@router.get("/tools/requests/pending", summary="待审批工具请求")
async def tools_pending():
    pend = [t for t in STORE.data["tool_requests"] if t.get("status") == "pending"]
    return {"pending": [{
        "request_id": t.get("id"),
        "agent_id": t.get("requested_by") or "?",
        "skill_id": t.get("tool") or t.get("skill_id") or "?",
        "params": t.get("params", ""), "created_at": t.get("created_at"),
    } for t in pend]}


# ==================== skills 路由 ====================

@router.get("/skills", summary="技能列表")
async def skills_list():
    return {"skills": list(STORE.data["skills"].values())}


@router.post("/skills/register", summary="注册技能")
async def skill_register(request: Request):
    import time, os, re
    body = await request.json() if request.body else {}
    sid = (body or {}).get("name", "").strip()
    if not sid:
        return JSONResponse({"detail": "name 不能为空"}, status_code=400)
    rec = {"id": "sk_%s" % re.sub(r"\W+", "_", sid).lower()[:32],
           "name": sid, "description": body.get("description", ""),
           "owner": body.get("owner", "human"), "enabled": True, "created_at": int(time.time())}
    STORE.data["skills"][rec["id"]] = rec
    STORE.audit("human", "skills.register", {"id": rec["id"]})
    STORE.save()
    return {"ok": True, "skill": rec}


@router.post("/skills/{skill_id}/disable", summary="禁用技能")
async def skill_disable(skill_id: str):
    if skill_id in STORE.data["skills"]:
        STORE.data["skills"][skill_id]["enabled"] = False
        STORE.audit("human", "skills.disable", {"id": skill_id})
        STORE.save()
        return {"ok": True}
    return JSONResponse({"detail": "技能不存在"}, status_code=404)


# ==================== workflows 路由 ====================

@router.get("/workflows", summary="工作流列表")
async def wf_list():
    out = []
    for w in STORE.data["workflows"].values():
        out.append({**w, "runs_count": len(w.get("runs", [])),
                    "last_run": (w.get("runs") or [{}])[-1].get("status", "")})
    return {"workflows": out}


@router.post("/workflows/create", summary="创建工作流")
async def wf_create(request: Request):
    import time, os
    body = await request.json() if request.body else {}
    wid = "wf_%d_%s" % (int(time.time()), os.urandom(3).hex())
    rec = {"id": wid, "name": (body or {}).get("name", "未命名"),
           "description": body.get("description", ""), "definition": body.get("definition") or [],
           "enabled": True, "runs": [], "created_at": int(time.time())}
    STORE.data["workflows"][wid] = rec
    STORE.audit("human", "workflows.create", {"id": wid})
    STORE.save()
    return {"ok": True, "workflow": rec}


@router.get("/workflows/{workflow_id}", summary="工作流详情")
async def wf_detail(workflow_id: str):
    w = STORE.data["workflows"].get(workflow_id)
    if w is None:
        return JSONResponse({"detail": "工作流不存在"}, status_code=404)
    return {"workflow": w}


@router.post("/workflows/{workflow_id}/update", summary="更新工作流")
async def wf_update(workflow_id: str, request: Request):
    body = await request.json() if request.body else {}
    w = STORE.data["workflows"].get(workflow_id)
    if w is None:
        return JSONResponse({"detail": "工作流不存在"}, status_code=404)
    if "definition" in (body or {}):
        w["definition"] = body["definition"]
    STORE.audit("human", "workflows.update", {"id": workflow_id})
    STORE.save()
    return {"ok": True}


@router.post("/workflows/{workflow_id}/run", summary="运行工作流")
async def wf_run(workflow_id: str, request: Request):
    import time
    from bluedeer.agent import BlueDeerAgent
    api = get_api()
    w = STORE.data["workflows"].get(workflow_id)
    if w is None:
        return JSONResponse({"detail": "工作流不存在"}, status_code=404)
    body = await request.json() if request.body else {}
    steps, outputs = [], []
    carried = ""
    for i, step in enumerate(w.get("definition") or []):
        agent_id = step.get("agent_id", "")
        prompt = step.get("prompt", "").replace("{prev}", carried)
        target = STORE.data["agents"].get(agent_id, {})
        agent = BlueDeerAgent(dict(api.cfg, system_prompt=target.get("system_prompt") or ""))
        t0 = time.time()
        out = agent.run(prompt)
        carried = out
        outputs.append(out)
        steps.append({"step": i + 1, "agent_id": agent_id, "output": out,
                      "elapsed_ms": round((time.time() - t0) * 1000.0, 1),
                      "blocked": out == "[安全拦截]"})
    run = {"run_id": "wr_%d_%s" % (int(time.time()), os.urandom(3).hex()),
           "trigger_by": (body.get("trigger_by") or ["human"])[0] if isinstance(body.get("trigger_by"), list) else body.get("trigger_by") or "human",
           "status": "done", "steps": steps, "output": outputs[-1] if outputs else "",
           "created_at": int(time.time())}
    w.setdefault("runs", []).append(run)
    STORE.audit("human", "workflows.run", {"id": workflow_id})
    STORE.save()
    return {"ok": True, "run": run}


@router.get("/workflows/{workflow_id}/runs", summary="工作流运行记录")
async def wf_runs(workflow_id: str):
    w = STORE.data["workflows"].get(workflow_id)
    if w is None:
        return JSONResponse({"detail": "工作流不存在"}, status_code=404)
    return {"runs": w.get("runs", [])[::-1]}


@router.post("/workflows/{workflow_id}/delete", summary="删除工作流")
async def wf_delete(workflow_id: str):
    if workflow_id in STORE.data["workflows"]:
        del STORE.data["workflows"][workflow_id]
        STORE.audit("human", "workflows.delete", {"id": workflow_id})
        STORE.save()
        return {"ok": True}
    return JSONResponse({"detail": "工作流不存在"}, status_code=404)


# ==================== projects 路由 ====================

@router.get("/projects", summary="项目列表")
async def pj_list():
    return {"projects": list(STORE.data["projects"].values())}


@router.post("/projects/create", summary="创建项目")
async def pj_create(request: Request):
    import time, os
    body = await request.json() if request.body else {}
    pid = "pj_%d_%s" % (int(time.time()), os.urandom(3).hex())
    rec = {"id": pid, "name": (body or {}).get("name", "未命名项目"),
           "description": body.get("description", ""), "agent_ids": body.get("agent_ids") or [],
           "tasks": [], "created_at": int(time.time())}
    STORE.data["projects"][pid] = rec
    STORE.audit("human", "projects.create", {"id": pid})
    STORE.save()
    return {"ok": True, "project": rec}


@router.get("/projects/{project_id}", summary="项目详情")
async def pj_detail(project_id: str):
    p = STORE.data["projects"].get(project_id)
    if p is None:
        return JSONResponse({"detail": "项目不存在"}, status_code=404)
    return {"project": p}


@router.post("/projects/{project_id}/delete", summary="删除项目")
async def pj_delete(project_id: str):
    if project_id in STORE.data["projects"]:
        del STORE.data["projects"][project_id]
        STORE.audit("human", "projects.delete", {"id": project_id})
        STORE.save()
        return {"ok": True}
    return JSONResponse({"detail": "项目不存在"}, status_code=404)


# ==================== crons 路由 ====================

@router.get("/crons", summary="定时任务列表")
async def cron_list():
    return {"crons": list(STORE.data["crons"].values())}


@router.post("/crons/create", summary="创建定时任务")
async def cron_create(request: Request):
    import time, os
    body = await request.json() if request.body else {}
    cid = "cr_%d_%s" % (int(time.time()), os.urandom(3).hex())
    rec = {"id": cid, "name": (body or {}).get("name", "定时任务"),
           "interval_sec": int(body.get("interval_sec") or 60),
           "action": body.get("action", "message"), "target": body.get("target", ""),
           "payload": body.get("payload") or {}, "enabled": True, "history": [], "created_at": int(time.time())}
    STORE.data["crons"][cid] = rec
    STORE.audit("human", "crons.create", {"id": cid})
    STORE.save()
    return {"ok": True, "cron": rec}


@router.post("/crons/{cron_id}/toggle", summary="切换定时任务状态")
async def cron_toggle(cron_id: str):
    c = STORE.data["crons"].get(cron_id)
    if not c:
        return JSONResponse({"detail": "定时任务不存在"}, status_code=404)
    c["enabled"] = not c.get("enabled", True)
    STORE.save()
    return {"ok": True, "cron": c}


@router.post("/crons/{cron_id}/run", summary="手动执行定时任务")
async def cron_run(cron_id: str):
    import time
    from bluedeer.agent import BlueDeerAgent
    api = get_api()
    c = STORE.data["crons"].get(cron_id)
    if not c:
        return JSONResponse({"detail": "定时任务不存在"}, status_code=404)
    entry = {"at": int(time.time()), "status": "done",
             "note": "%s -> %s" % (c.get("action"), c.get("target"))}
    c["last_fired"] = int(time.time())
    if c.get("action") == "delegate" and c.get("target"):
        agent = BlueDeerAgent(dict(api.cfg, system_prompt=(STORE.data["agents"].get(c["target"], {}) or {}).get("system_prompt") or ""))
        entry["output"] = agent.run((c.get("payload") or {}).get("content", "执行定时任务"))
    c.setdefault("history", []).append(entry)
    STORE.audit("cron:" + cron_id, "cron.run", entry["note"])
    STORE.save()
    return {"ok": True, "entry": entry}


@router.post("/crons/{cron_id}/delete", summary="删除定时任务")
async def cron_delete(cron_id: str):
    if cron_id in STORE.data["crons"]:
        del STORE.data["crons"][cron_id]
        STORE.save()
        return {"ok": True}
    return JSONResponse({"detail": "定时任务不存在"}, status_code=404)


@router.get("/crons/{cron_id}/history", summary="定时任务历史")
async def cron_history(cron_id: str):
    c = STORE.data["crons"].get(cron_id)
    if not c:
        return JSONResponse({"detail": "定时任务不存在"}, status_code=404)
    return {"history": c.get("history", [])[::-1]}


# ==================== files 路由 ====================

@router.get("/files/list", summary="文件列表")
async def files_list(path: str = Query("")):
    api = get_api()
    import time, os
    rel = (path or "").lstrip("/\\").replace("..\\", "").replace("../", "")
    p = os.path.abspath(os.path.join(ROOT_DIR, rel))
    if not (p == os.path.abspath(ROOT_DIR) or p.startswith(os.path.abspath(ROOT_DIR) + os.sep)):
        return JSONResponse({"detail": "路径越界"}, status_code=403)
    try:
        items = []
        for name in os.listdir(p):
            full = os.path.join(p, name)
            items.append({"name": name, "is_dir": os.path.isdir(full), "size": os.path.getsize(full) if os.path.isfile(full) else 0})
        return {"path": rel, "items": items}
    except Exception as e:
        return JSONResponse({"detail": str(e)}, status_code=500)


@router.get("/files/content", summary="文件内容")
async def files_content(path: str = Query(""), encoding: str = Query("utf-8")):
    api = get_api()
    import time, os
    rel = (path or "").lstrip("/\\").replace("..\\", "").replace("../", "")
    p = os.path.abspath(os.path.join(ROOT_DIR, rel))
    if not (p == os.path.abspath(ROOT_DIR) or p.startswith(os.path.abspath(ROOT_DIR) + os.sep)):
        return JSONResponse({"detail": "路径越界"}, status_code=403)
    try:
        with open(p, "r", encoding=encoding) as f:
            return {"content": f.read()}
    except Exception as e:
        return JSONResponse({"detail": str(e)}, status_code=500)


@router.post("/files/content", summary="写入文件")
async def files_content_post(request: Request):
    api = get_api()
    import time, os
    body = await request.json() if request.body else {}
    path = body.get("path", "")
    content = body.get("content", "")
    rel = (path or "").lstrip("/\\").replace("..\\", "").replace("../", "")
    p = os.path.abspath(os.path.join(ROOT_DIR, rel))
    if not (p == os.path.abspath(ROOT_DIR) or p.startswith(os.path.abspath(ROOT_DIR) + os.sep)):
        return JSONResponse({"detail": "路径越界"}, status_code=403)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"detail": str(e)}, status_code=500)


@router.post("/files/create", summary="创建文件")
async def files_create(request: Request):
    api = get_api()
    import time, os
    body = await request.json() if request.body else {}
    path = body.get("path", "")
    rel = (path or "").lstrip("/\\").replace("..\\", "").replace("../", "")
    p = os.path.abspath(os.path.join(ROOT_DIR, rel))
    if not (p == os.path.abspath(ROOT_DIR) or p.startswith(os.path.abspath(ROOT_DIR) + os.sep)):
        return JSONResponse({"detail": "路径越界"}, status_code=403)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("")
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"detail": str(e)}, status_code=500)


@router.post("/files/delete", summary="删除文件")
async def files_delete(request: Request):
    api = get_api()
    import time, os
    body = await request.json() if request.body else {}
    path = body.get("path", "")
    rel = (path or "").lstrip("/\\").replace("..\\", "").replace("../", "")
    p = os.path.abspath(os.path.join(ROOT_DIR, rel))
    if not (p == os.path.abspath(ROOT_DIR) or p.startswith(os.path.abspath(ROOT_DIR) + os.sep)):
        return JSONResponse({"detail": "路径越界"}, status_code=403)
    try:
        os.remove(p)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"detail": str(e)}, status_code=500)
