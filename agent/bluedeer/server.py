# -*- coding: utf-8 -*-
"""BlueDeer 底座 REST API —— 纯标准库实现，给 BlueDeer-Console 前端供真实数据。

启动: python -m bluedeer.server   (默认 127.0.0.1:8000, config.json 可改 server_port)

数据全部真实:
- Agent 注册表 / 管理岗 / 自动应答 / 消息流水 → data/api_store.json 落盘
- 运行轨迹统计(图表) → runs/*/final.json 真实扫描
- 模型探测 → 本地 Ollama /api/tags 或任意 OpenAI 兼容 /models
- 委托调用 → 真跑 Agent 十三层流水线, 并写入 runs/ 轨迹
"""
import json
import os
import re
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from .config import DEFAULT_CONFIG, ROOT_DIR, get_env, load_config, save_config, resolve_path
from .agent import BlueDeerAgent
from .roles import list_roles, load_role

VERSION = "1.0.0"
STORE_PATH = os.path.join(ROOT_DIR, "data", "api_store.json")
_LOCK = threading.RLock()

_EMPTY_STORE = {
    "agents": {},          # agent_id -> {agent_id,name,role,capabilities,status,last_seen,system_prompt,auto_reply{}}
    "manager": None,
    "messages": [],        # {msg_id,channel_type,from_agent,to_agent,content,task_id,created_at}
    "memories": [],        # {id,reader,domain,content,created_at}
    "memory_approvals": [],# {id,reader,domain,content,status,requested_by,created_at}
    "tool_requests": [],   # {id,tool,args,status,requested_by,created_at}
    "skills": {},          # id -> {id,name,description,owner,enabled,created_at}
    "workflows": {},       # id -> {id,name,description,definition,runs:[{run_id,status,steps,output,created_at}]}
    "projects": {},        # id -> {id,name,description,agent_ids,tasks:[],created_at}
    "crons": {},           # id -> {id,name,interval_sec,action,target,payload,enabled,history:[],created_at}
    "audit_logs": [],
    "emergency_block": False,
}


def _now():
    return int(time.time())


class Store:
    """单文件 JSON 存储 + 线程锁。所有页面读写都过这里。"""

    def __init__(self, path=STORE_PATH):
        self.path = path
        self.lock = _LOCK
        self.data = json.loads(json.dumps(_EMPTY_STORE))
        self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for k, v in saved.items():
                if k in self.data:
                    self.data[k] = v
        except Exception:
            pass

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def audit(self, actor, action, detail=None):
        self.data["audit_logs"].append({
            "actor": actor, "action": action,
            "detail": detail if isinstance(detail, (dict, str)) else None,
            "created_at": _now(),
        })
        self.data["audit_logs"] = self.data["audit_logs"][-2000:]

    def add_message(self, channel_type, from_agent, to_agent, content, task_id=None):
        msg = {
            "msg_id": "m_%d_%s" % (_now(), os.urandom(3).hex()),
            "channel_type": channel_type or "private",
            "from_agent": from_agent, "to_agent": to_agent,
            "content": content, "task_id": task_id, "created_at": _now(),
        }
        self.data["messages"].append(msg)
        self.data["messages"] = self.data["messages"][-3000:]
        return msg


STORE = Store()


def seed_agents_from_roles(cfg=None):
    """把 roles/ 目录的真实角色注册为节点（增量：已存在的不动，缺的补上）。"""
    rd = (cfg or {}).get("roles_dir") or os.path.join(ROOT_DIR, "roles")
    try:
        names = list_roles(rd)
    except Exception:
        return 0
    n = 0
    for name in names:
        aid = "agent_" + name
        if aid in STORE.data["agents"]:
            continue
        role = load_role(rd, name)
        if not role:
            continue
        STORE.data["agents"][aid] = {
            "agent_id": aid, "name": name, "role": role.title or name,
            "status": "offline", "last_seen": 0,
            "capabilities": [role.title or name],
            "system_prompt": role.system_prompt or "",
            "auto_reply": {"enabled": False, "reply_template": ""},
            "registered_at": _now(),
        }
        n += 1
    if n:
        STORE.audit("system", "agents.seed_roles", {"count": n})
        STORE.save()
    return n


def _scheduler_loop(api, stop_evt):
    """真实后台调度线程：每 5s 扫描启用的定时任务，到点真执行（delegate/message/workflow）。"""
    while not stop_evt.wait(5):
        try:
            now = _now()
            for cid, c in list(STORE.data["crons"].items()):
                if not c.get("enabled"):
                    continue
                interval = max(5, int(c.get("interval_sec") or 60))
                if now - int(c.get("last_fired", 0)) < interval:
                    continue
                c["last_fired"] = now
                entry = {"at": now, "status": "done", "trigger": "auto",
                         "note": "%s -> %s" % (c.get("action"), c.get("target"))}
                try:
                    act, tgt = c.get("action"), c.get("target")
                    if act == "delegate" and tgt:
                        agent = BlueDeerAgent(dict(
                            api.cfg,
                            system_prompt=(STORE.data["agents"].get(tgt, {}) or {}).get("system_prompt") or ""))
                        entry["output"] = agent.run((c.get("payload") or {}).get("content", "执行定时任务"))
                        if tgt in STORE.data["agents"]:
                            STORE.data["agents"][tgt]["last_seen"] = now
                    elif act == "message" and tgt and not STORE.data["emergency_block"]:
                        STORE.add_message("private", "cron:" + cid, tgt,
                                          (c.get("payload") or {}).get("content", ""))
                    elif act == "workflow" and tgt:
                        api.wf_run(tgt, {"trigger_by": ["cron:" + cid]}, {})
                except Exception as e:
                    entry["status"] = "error"
                    entry["error"] = str(e)
                c.setdefault("history", []).append(entry)
                c["history"] = c["history"][-100:]
                STORE.audit("cron:" + cid, "cron.auto", entry["note"])
                STORE.save()
        except Exception:
            pass


def _scan_runs(runs_dir):
    """扫描 runs/*/final.json → [{run_id, ts, output_len, blocked, layer_timings{}, role}] 全真实。"""
    out = []
    if not os.path.isdir(runs_dir):
        return out
    for name in sorted(os.listdir(runs_dir)):
        fp = os.path.join(runs_dir, name, "final.json")
        if not os.path.isfile(fp):
            continue
        try:
            with open(fp, "r", encoding="utf-8") as f:
                d = json.load(f)
            ts = name.split("_")
            t = int(time.mktime(time.strptime("%s-%s-%s %s:%s:%s" % (ts[0][:4], ts[0][4:6], ts[0][6:], ts[1][:2], ts[1][2:4], ts[1][4:]), "%Y-%m-%d %H:%M:%S")))
            out.append({
                "run_id": d.get("run_id") or name,
                "dir": name, "ts": t,
                "blocked": bool(d.get("blocked")),
                "block_reason": d.get("block_reason"),
                "output_len": len(str(d.get("output") or "")),
                "layer_timings": d.get("layer_timings") or {},
                "role": (d.get("metadata") or {}).get("role", ""),
                "provider": (d.get("metadata") or {}).get("provider", ""),
            })
        except Exception:
            continue
    return out


def usage_report(cfg):
    """真数据报表: 近14天运行趋势 / 各层平均耗时 / 角色分布 / 成功率。"""
    runs = _scan_runs(str(resolve_path(cfg, "runs_dir")))
    days = {}
    layer_sum, layer_cnt = {}, {}
    role_cnt, provider_cnt = {}, {}
    blocked = 0
    for r in runs:
        day = time.strftime("%m-%d", time.localtime(r["ts"]))
        days.setdefault(day, {"date": day, "count": 0, "blocked": 0})
        days[day]["count"] += 1
        if r["blocked"]:
            days[day]["blocked"] += 1
            blocked += 1
        for lk, lv in (r["layer_timings"] or {}).items():
            try:
                layer_sum[lk] = layer_sum.get(lk, 0.0) + float(lv)
                layer_cnt[lk] = layer_cnt.get(lk, 0) + 1
            except (TypeError, ValueError):
                pass
        rk = r["role"] or "(default)"
        role_cnt[rk] = role_cnt.get(rk, 0) + 1
        pk = r["provider"] or cfg.get("provider", "?")
        provider_cnt[pk] = provider_cnt.get(pk, 0) + 1
    timeline = [days[d] for d in sorted(days)][-14:]
    layers = [{"layer": k, "avg_ms": round(layer_sum[k] / layer_cnt[k], 1)} for k in sorted(layer_sum)]
    total = len(runs)
    return {
        "total_runs": total,
        "blocked_runs": blocked,
        "success_rate": round((total - blocked) * 100.0 / total, 1) if total else 100.0,
        "runs_per_day": timeline,
        "layer_avg_ms": layers,
        "role_distribution": role_cnt,
        "provider_distribution": provider_cnt,
    }


def build_stats(cfg):
    st = STORE.data
    agents = list(st["agents"].values())
    online = [a for a in agents if a.get("status") == "online"]
    wfs = st["workflows"]
    usage = usage_report(cfg)
    return {
        "agents_online": len(online),
        "agents_total": len(agents),
        "approvals_pending": len([x for x in st["memory_approvals"] if x.get("status") == "pending"]),
        "tool_requests": len([x for x in st["tool_requests"] if x.get("status") == "pending"]),
        "workflows_running": 0,
        "workflow_runs": sum(len(w.get("runs", [])) for w in wfs.values()),
        "workflows_active": len([w for w in wfs.values() if w.get("enabled", True)]),
        "tasks_pending": sum(len(p.get("tasks", [])) for p in st["projects"].values()),
        "messages_total": len(st["messages"]),
        "total_runs": usage["total_runs"],
        "emergency_block": bool(st["emergency_block"]),
        "usage": usage,
    }


# ---------------------------------------------------------------- 探测模型
def probe_models(api_base, api_key):
    base = (api_base or "").strip().rstrip("/")
    if not base or "11434" in base:
        url = "http://127.0.0.1:11434/api/tags"
        try:
            with urllib.request.urlopen(url, timeout=4) as r:
                names = [m.get("name", "") for m in json.loads(r.read().decode("utf-8")).get("models", [])]
            return {"ok": True, "source": "ollama", "models": sorted(n for n in names if n)}
        except Exception as e:
            return {"ok": False, "error": "本地 Ollama 不可达(%s)" % e}
    req = urllib.request.Request(base + "/models")
    if api_key:
        req.add_header("Authorization", "Bearer " + api_key)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            j = json.loads(r.read().decode("utf-8"))
        models = [m.get("id", "") for m in j.get("data", [])]
        return {"ok": True, "source": base, "models": sorted(m for m in models if m)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------- 业务处理
class Api:
    """路由处理器: path -> callable(query, body) -> (status, payload)"""

    def __init__(self, cfg):
        self.cfg = cfg
        self.agent = BlueDeerAgent(cfg)

    # ---- system ----
    def root(self, q, b):
        return 200, {"version": VERSION, "name": "BlueDeer 底座"}

    def stats(self, q, b):
        return 200, {"stats": build_stats(self.cfg)}

    def usage(self, q, b):
        return 200, usage_report(self.cfg)

    def settings_get(self, q, b):
        keys = ["provider", "ollama_model", "ollama_base_url", "trace", "role",
                "roles_dir", "system_prompt", "server_host", "server_port",
                "api_base", "api_model"]
        s = {k: self.cfg.get(k, DEFAULT_CONFIG.get(k)) for k in keys}
        s["api_key_set"] = bool(self.cfg.get("api_key") or get_env("BLUEDEER_API_KEY"))
        return 200, {"settings": s}

    def settings_post(self, q, b):
        allowed = {"provider", "ollama_model", "ollama_base_url", "trace", "role",
                   "roles_dir", "system_prompt", "default_auto_reply_template",
                   "api_base", "api_key", "api_model"}
        changed = []
        fresh = load_config()  # 读-改-写，避免把服务器运行时覆盖(如测试临时目录)落盘
        for k, v in (b or {}).items():
            if k in allowed and v is not None:
                self.cfg[k] = v
                fresh[k] = v
                changed.append(k)
        STORE.audit("human", "settings.update", {"keys": changed})
        STORE.save()
        if set(changed) & {"provider", "ollama_model", "ollama_base_url",
                           "api_base", "api_key", "api_model"}:
            self.agent = BlueDeerAgent(self.cfg)  # 模型配置热生效，无需重启
        save_config(fresh)
        return 200, {"ok": True, "changed": changed}

    def audit_logs(self, q, b):
        logs = STORE.data["audit_logs"]
        actor = (q.get("actor") or [""])[0]
        if actor:
            logs = [l for l in logs if l.get("actor") == actor]
        limit = int((q.get("limit") or ["50"])[0])
        return 200, {"logs": logs[-limit:][::-1]}

    def emergency_toggle(self, q, b):
        want = (q.get("active") or [""])[0].lower()
        cur = bool(STORE.data["emergency_block"])
        nxt = (want == "true") if want else (not cur)
        STORE.data["emergency_block"] = nxt
        STORE.audit("human", "emergency_block.toggle", {"active": nxt})
        STORE.save()
        return 200, {"ok": True, "emergency_block": nxt}

    def probe(self, q, b):
        return 200, probe_models((q.get("api_base") or [""])[0], (q.get("api_key") or [""])[0])

    # ---- agents ----
    def agents_list(self, q, b):
        ags = list(STORE.data["agents"].values())
        now = _now()
        for a in ags:
            a["last_seen"] = a.get("last_seen") or 0
            # 真实在线判定：最近 10 分钟内有实际活动（委托/定时触发）才算在线
            a["status"] = "online" if a["last_seen"] and now - int(a["last_seen"]) <= 600 else "offline"
        return 200, {"agents": ags}

    def agent_register(self, q, b):
        aid = (b or {}).get("agent_id", "").strip()
        if not aid:
            return 400, {"detail": "agent_id 不能为空"}
        existed = aid in STORE.data["agents"]
        rec = STORE.data["agents"].get(aid, {})
        rec.update({
            "agent_id": aid,
            "name": b.get("name") or aid,
            "role": b.get("role") or "worker",
            "capabilities": b.get("capabilities") or [],
            "system_prompt": b.get("system_prompt") or rec.get("system_prompt") or "",
            "auto_reply": b.get("auto_reply") or rec.get("auto_reply") or {"enabled": False},
            "status": "online", "last_seen": _now(), "created_at": rec.get("created_at", _now()),
        })
        STORE.data["agents"][aid] = rec
        STORE.audit("human", "agents.register", {"agent_id": aid})
        STORE.save()
        return 200, {"ok": True, "registered_before": existed, "agent": rec}

    def agent_detail(self, aid, q, b):
        rec = STORE.data["agents"].get(aid)
        if rec is None:
            roles = list_roles(self.cfg.get("roles_dir") or "")
            if aid in roles:
                r = load_role(self.cfg.get("roles_dir") or "", aid)
                rec = {"agent_id": aid, "name": aid, "role": "worker",
                       "capabilities": ["内置角色"], "system_prompt": r.system_prompt,
                       "auto_reply": {"enabled": False}, "status": "online", "last_seen": _now()}
            else:
                return 404, {"detail": "Agent 不存在"}
        return 200, {"agent": rec}

    def agent_update(self, aid, q, b):
        rec = STORE.data["agents"].get(aid)
        if rec is None:
            return 404, {"detail": "Agent 不存在"}
        if "system_prompt" in (b or {}):
            rec["system_prompt"] = b["system_prompt"]
        STORE.audit("human", "agents.update", {"agent_id": aid})
        STORE.save()
        return 200, {"ok": True, "agent": rec}

    def agent_autoreply(self, aid, q, b):
        rec = STORE.data["agents"].get(aid)
        if rec is None:
            return 404, {"detail": "Agent 不存在"}
        ar = rec.setdefault("auto_reply", {})
        if "enabled" in (b or {}):
            ar["enabled"] = bool(b["enabled"])
        if b.get("reply_template"):
            ar["reply_template"] = b["reply_template"]
        elif "reply_template" in (b or {}):
            ar["reply_template"] = ""
        STORE.audit("human", "agents.autoreply", {"agent_id": aid, "enabled": ar.get("enabled")})
        STORE.save()
        return 200, {"ok": True, "auto_reply": ar}

    def manager_set(self, q, b):
        aid = (b or {}).get("agent_id", "")
        if aid not in STORE.data["agents"]:
            return 404, {"detail": "Agent 不存在"}
        STORE.data["manager"] = aid
        STORE.audit("human", "manager.set", {"agent_id": aid})
        STORE.save()
        return 200, {"ok": True, "manager": aid}

    def manager_clear(self, q, b):
        STORE.data["manager"] = None
        STORE.audit("human", "manager.clear", None)
        STORE.save()
        return 200, {"ok": True}

    def manager_current(self, q, b):
        aid = STORE.data["manager"]
        if not aid or aid not in STORE.data["agents"]:
            return 200, {"manager": None}
        return 200, {"manager": STORE.data["agents"][aid]}

    def delegate(self, q, b):
        frm = (b or {}).get("from_agent", "")
        to = (b or {}).get("to_agent", "")
        task = (b or {}).get("task_content", "").strip()
        if to not in STORE.data["agents"] and to not in list_roles(self.cfg.get("roles_dir") or os.path.join(ROOT_DIR, "roles")):
            return 404, {"detail": "目标 Agent 不存在"}
        if not task:
            return 400, {"detail": "任务内容不能为空"}
        target = STORE.data["agents"].get(to, {})
        if target.get("auto_reply", {}).get("enabled"):
            tpl = target["auto_reply"].get("reply_template") or "收到，{from}。任务「{task}」已受理，正在处理…"
            reply = tpl.replace("{from}", frm).replace("{task}", task[:60])
        else:
            agent = BlueDeerAgent(dict(self.cfg, system_prompt=target.get("system_prompt") or ""))
            reply = agent.run(task)
        if to in STORE.data["agents"]:
            STORE.data["agents"][to]["last_seen"] = _now()
        STORE.add_message("private", frm, to, task)
        STORE.add_message("private", to, frm, reply)
        STORE.audit(frm, "delegate.to", {"to": to, "chars": len(reply)})
        STORE.save()
        return 200, {"status": "replied" if reply != "[安全拦截]" else "blocked", "reply": reply}

    # ---- messages ----
    def msg_history(self, q, b):
        msgs = STORE.data["messages"]
        fa = (q.get("from_agent") or [""])[0]
        ta = (q.get("to_agent") or [""])[0]
        if fa:
            msgs = [m for m in msgs if m["from_agent"] == fa]
        if ta:
            msgs = [m for m in msgs if m["to_agent"] == ta]
        limit = int((q.get("limit") or ["80"])[0])
        return 200, {"messages": msgs[-limit:]}

    def msg_send(self, q, b):
        if STORE.data["emergency_block"]:
            return 403, {"detail": "紧急刹车已开启，消息被拦截"}
        body = b or {}
        msg = STORE.add_message(body.get("channel_type"), body.get("from_agent", "human"),
                                body.get("to_agent", ""), body.get("content", ""), body.get("task_id"))
        STORE.audit(msg["from_agent"], "message.send", {"to": msg["to_agent"]})
        STORE.save()
        return 200, {"ok": True, "message": msg}

    # ---- memories & approvals ----
    def mem_domains(self, q, b):
        doms = sorted({m.get("domain", "") for m in STORE.data["memories"]} |
                      {a.get("domain", "") for a in STORE.data["memory_approvals"] if a.get("status") == "pending"})
        return 200, {"domains": [d for d in doms if d]}

    def mem_read(self, q, b):
        dom = (q.get("domain") or [""])[0]
        items = [m for m in STORE.data["memories"] if m.get("domain") == dom]
        return 200, {"domain": dom, "items": items}

    def mem_write(self, q, b):
        body = b or {}
        item = {"id": "mem_%d_%s" % (_now(), os.urandom(3).hex()),
                "reader": body.get("reader", "human"),
                "domain": body.get("domain", "default"),
                "content": body.get("content", ""),
                "status": "approved",
                "requested_by": body.get("reader", "human"), "created_at": _now()}
        STORE.data["memories"].append(item)
        STORE.audit(item["reader"], "memory.write", {"domain": item["domain"]})
        STORE.save()
        return 200, {"ok": True, "item": item}

    def mem_delete(self, q, b):
        body = b or {}
        before = len(STORE.data["memories"])
        STORE.data["memories"] = [m for m in STORE.data["memories"]
                                  if not (m.get("domain") == body.get("domain") and m.get("content") == body.get("content"))]
        STORE.audit("human", "memory.delete", {"removed": before - len(STORE.data["memories"])})
        STORE.save()
        return 200, {"ok": True}

    def approvals_pending(self, q, b):
        pend = [a for a in STORE.data["memory_approvals"] if a.get("status") == "pending"]
        return 200, {"pending": [{
            "request_id": a.get("id"),
            "agent_id": a.get("requested_by") or a.get("reader") or "?",
            "domain": a.get("domain", ""), "action": a.get("action", "write"),
            "content": a.get("content", ""), "created_at": a.get("created_at"),
        } for a in pend]}

    def approval_decide(self, kind, q, b):
        body = b or {}
        rid = body.get("request_id", "")
        decision = "approve" if body.get("approve") else "reject"
        bucket = STORE.data["memory_approvals"] if kind == "memory" else STORE.data["tool_requests"]
        for item in bucket:
            if item.get("id") == rid and item.get("status") == "pending":
                item["status"] = decision
                if kind == "memory" and decision == "approve":
                    STORE.data["memories"].append({
                        "id": item["id"], "reader": item.get("reader", ""),
                        "domain": item.get("domain", ""), "content": item.get("content", ""),
                        "status": "approved", "requested_by": item.get("requested_by"),
                        "created_at": _now()})
                actor = body.get("manager_id") or "human"
                STORE.audit(actor, kind + "_approval." + decision, {"id": rid})
                STORE.save()
                return 200, {"ok": True, "decision": decision}
        return 404, {"detail": "审批不存在或已处理"}

    def tools_pending(self, q, b):
        pend = [t for t in STORE.data["tool_requests"] if t.get("status") == "pending"]
        return 200, {"pending": [{
            "request_id": t.get("id"),
            "agent_id": t.get("requested_by") or "?",
            "skill_id": t.get("tool") or t.get("skill_id") or "?",
            "params": t.get("params", ""), "created_at": t.get("created_at"),
        } for t in pend]}

    # ---- skills ----
    def skills_list(self, q, b):
        return 200, {"skills": list(STORE.data["skills"].values())}

    def skill_register(self, q, b):
        sid = (b or {}).get("name", "").strip()
        if not sid:
            return 400, {"detail": "name 不能为空"}
        rec = {"id": "sk_%s" % re.sub(r"\W+", "_", sid).lower()[:32],
               "name": sid, "description": b.get("description", ""),
               "owner": b.get("owner", "human"), "enabled": True, "created_at": _now()}
        STORE.data["skills"][rec["id"]] = rec
        STORE.audit("human", "skills.register", {"id": rec["id"]})
        STORE.save()
        return 200, {"ok": True, "skill": rec}

    def skill_disable(self, sid, q, b):
        if sid in STORE.data["skills"]:
            STORE.data["skills"][sid]["enabled"] = False
            STORE.audit("human", "skills.disable", {"id": sid})
            STORE.save()
            return 200, {"ok": True}
        return 404, {"detail": "技能不存在"}

    # ---- workflows ----
    def wf_list(self, q, b):
        out = []
        for w in STORE.data["workflows"].values():
            out.append({**w, "runs_count": len(w.get("runs", [])), "last_run": (w.get("runs") or [{}])[-1].get("status", "")})
        return 200, {"workflows": out}

    def wf_create(self, q, b):
        wid = "wf_%d_%s" % (_now(), os.urandom(3).hex())
        rec = {"id": wid, "name": (b or {}).get("name", "未命名"),
               "description": b.get("description", ""), "definition": b.get("definition") or [],
               "enabled": True, "runs": [], "created_at": _now()}
        STORE.data["workflows"][wid] = rec
        STORE.audit("human", "workflows.create", {"id": wid})
        STORE.save()
        return 200, {"ok": True, "workflow": rec}

    def _wf(self, wid):
        return STORE.data["workflows"].get(wid)

    def wf_detail(self, wid, q, b):
        w = self._wf(wid)
        return (200, {"workflow": w}) if w else (404, {"detail": "工作流不存在"})

    def wf_update(self, wid, q, b):
        w = self._wf(wid)
        if not w:
            return 404, {"detail": "工作流不存在"}
        if "definition" in (b or {}):
            w["definition"] = b["definition"]
        STORE.audit("human", "workflows.update", {"id": wid})
        STORE.save()
        return 200, {"ok": True}

    def wf_run(self, wid, q, b):
        w = self._wf(wid)
        if not w:
            return 404, {"detail": "工作流不存在"}
        steps, outputs = [], []
        carried = ""
        for i, step in enumerate(w.get("definition") or []):
            agent_id = step.get("agent_id", "")
            prompt = step.get("prompt", "").replace("{prev}", carried)
            target = STORE.data["agents"].get(agent_id, {})
            agent = BlueDeerAgent(dict(self.cfg, system_prompt=target.get("system_prompt") or ""))
            t0 = time.time()
            out = agent.run(prompt)
            carried = out
            outputs.append(out)
            steps.append({"step": i + 1, "agent_id": agent_id, "output": out,
                          "elapsed_ms": round((time.time() - t0) * 1000.0, 1),
                          "blocked": out == "[安全拦截]"})
        run = {"run_id": "wr_%d_%s" % (_now(), os.urandom(3).hex()),
               "trigger_by": (q.get("trigger_by") or ["human"])[0],
               "status": "done", "steps": steps, "output": outputs[-1] if outputs else "",
               "created_at": _now()}
        w.setdefault("runs", []).append(run)
        STORE.audit("human", "workflows.run", {"id": wid})
        STORE.save()
        return 200, {"ok": True, "run": run}

    def wf_runs(self, wid, q, b):
        w = self._wf(wid)
        if not w:
            return 404, {"detail": "工作流不存在"}
        return 200, {"runs": w.get("runs", [])[::-1]}

    def wf_delete(self, wid, q, b):
        if wid in STORE.data["workflows"]:
            del STORE.data["workflows"][wid]
            STORE.audit("human", "workflows.delete", {"id": wid})
            STORE.save()
            return 200, {"ok": True}
        return 404, {"detail": "工作流不存在"}

    # ---- projects ----
    def pj_list(self, q, b):
        return 200, {"projects": list(STORE.data["projects"].values())}

    def pj_create(self, q, b):
        pid = "pj_%d_%s" % (_now(), os.urandom(3).hex())
        rec = {"id": pid, "name": (b or {}).get("name", "未命名项目"),
               "description": b.get("description", ""), "agent_ids": b.get("agent_ids") or [],
               "tasks": [], "created_at": _now()}
        STORE.data["projects"][pid] = rec
        STORE.audit("human", "projects.create", {"id": pid})
        STORE.save()
        return 200, {"ok": True, "project": rec}

    def pj_detail(self, pid, q, b):
        p = STORE.data["projects"].get(pid)
        return (200, {"project": p}) if p else (404, {"detail": "项目不存在"})

    def pj_delete(self, pid, q, b):
        if pid in STORE.data["projects"]:
            del STORE.data["projects"][pid]
            STORE.audit("human", "projects.delete", {"id": pid})
            STORE.save()
            return 200, {"ok": True}
        return 404, {"detail": "项目不存在"}

    # ---- crons ----
    def cron_list(self, q, b):
        return 200, {"crons": list(STORE.data["crons"].values())}

    def cron_create(self, q, b):
        cid = "cr_%d_%s" % (_now(), os.urandom(3).hex())
        rec = {"id": cid, "name": (b or {}).get("name", "定时任务"),
               "interval_sec": int(b.get("interval_sec") or 60),
               "action": b.get("action", "message"), "target": b.get("target", ""),
               "payload": b.get("payload") or {}, "enabled": True, "history": [], "created_at": _now()}
        STORE.data["crons"][cid] = rec
        STORE.audit("human", "crons.create", {"id": cid})
        STORE.save()
        return 200, {"ok": True, "cron": rec}

    def _cron(self, cid):
        return STORE.data["crons"].get(cid)

    def cron_toggle(self, cid, q, b):
        c = self._cron(cid)
        if not c:
            return 404, {"detail": "定时任务不存在"}
        c["enabled"] = not c.get("enabled", True)
        STORE.save()
        return 200, {"ok": True, "cron": c}

    def cron_run(self, cid, q, b):
        c = self._cron(cid)
        if not c:
            return 404, {"detail": "定时任务不存在"}
        entry = {"at": _now(), "status": "done",
                 "note": "%s -> %s" % (c.get("action"), c.get("target"))}
        c["last_fired"] = _now()
        if c.get("action") == "delegate" and c.get("target"):
            agent = BlueDeerAgent(dict(self.cfg, system_prompt=(STORE.data["agents"].get(c["target"], {}) or {}).get("system_prompt") or ""))
            entry["output"] = agent.run((c.get("payload") or {}).get("content", "执行定时任务"))
        c.setdefault("history", []).append(entry)
        STORE.audit("cron:" + cid, "cron.run", entry["note"])
        STORE.save()
        return 200, {"ok": True, "entry": entry}

    def cron_delete(self, cid, q, b):
        if cid in STORE.data["crons"]:
            del STORE.data["crons"][cid]
            STORE.save()
            return 200, {"ok": True}
        return 404, {"detail": "定时任务不存在"}

    def cron_history(self, cid, q, b):
        c = self._cron(cid)
        if not c:
            return 404, {"detail": "定时任务不存在"}
        return 200, {"history": c.get("history", [])[::-1]}

    # ---- files (IDE, 限定 ROOT_DIR 内) ----
    def _safe_path(self, rel):
        rel = (rel or "").lstrip("/\\").replace("..\\", "").replace("../", "")
        p = os.path.abspath(os.path.join(ROOT_DIR, rel))
        if not (p == os.path.abspath(ROOT_DIR) or p.startswith(os.path.abspath(ROOT_DIR) + os.sep)):
            raise PermissionError("路径越界")
        return p

    def files_list(self, q, b):
        try:
            p = self._safe_path((q.get("path") or [""])[0])
        except PermissionError:
            return 403, {"detail": "路径越界"}
        if not os.path.isdir(p):
            return 404, {"detail": "目录不存在"}
        items = []
        for name in sorted(os.listdir(p)):
            full = os.path.join(p, name)
            if name.startswith(".") or name in ("__pycache__", "node_modules", ".venv"):
                continue
            items.append({"name": name, "is_dir": os.path.isdir(full),
                          "size": os.path.getsize(full) if os.path.isfile(full) else 0})
        dirs = [i for i in items if i["is_dir"]]
        files = [i for i in items if not i["is_dir"]]
        return 200, {"path": (q.get("path") or [""])[0], "entries": dirs + files}

    def files_content(self, q, b):
        if q.get("path"):  # GET
            try:
                p = self._safe_path(q["path"][0])
            except PermissionError:
                return 403, {"detail": "路径越界"}
            if not os.path.isfile(p):
                return 404, {"detail": "文件不存在"}
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return 200, {"path": q["path"][0], "content": f.read()}
            except UnicodeDecodeError:
                return 200, {"path": q["path"][0], "content": "(二进制文件，不支持预览)"}
        body = b or {}     # POST 保存
        try:
            p = self._safe_path(body.get("path", ""))
        except PermissionError:
            return 403, {"detail": "路径越界"}
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(body.get("content", ""))
        STORE.audit("human", "files.save", {"path": body.get("path")})
        STORE.save()
        return 200, {"ok": True}

    def files_create(self, q, b):
        body = b or {}
        try:
            p = self._safe_path(body.get("path", ""))
        except PermissionError:
            return 403, {"detail": "路径越界"}
        if body.get("is_dir"):
            os.makedirs(p, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "a", encoding="utf-8").close()
        STORE.audit("human", "files.create", {"path": body.get("path"), "is_dir": bool(body.get("is_dir"))})
        STORE.save()
        return 200, {"ok": True}

    def files_delete(self, q, b):
        body = b or {}
        try:
            p = self._safe_path(body.get("path", ""))
        except PermissionError:
            return 403, {"detail": "路径越界"}
        if not os.path.exists(p):
            return 404, {"detail": "不存在"}
        import shutil
        if os.path.isdir(p):
            shutil.rmtree(p)
        else:
            os.remove(p)
        STORE.audit("human", "files.delete", {"path": body.get("path")})
        STORE.save()
        return 200, {"ok": True}


def make_api(cfg=None):
    cfg = load_config() if cfg is None else dict(load_config(), **cfg)
    return Api(cfg)


ROUTES = [
    (re.compile(r"^/$"), "GET", lambda a, q, b, m=None: a.root(q, b)),
]


def dispatch(api, method, path, q, b):
    """把 path 分发到 Api 方法。返回 (status, payload)。"""
    m = re.match(r"^/$", path)
    if m and method == "GET":
        return api.root(q, b)
    parts = [p for p in path.strip("/").split("/") if p]

    simple = {
        ("GET", "system", "stats"): api.stats,
        ("GET", "system", "usage"): api.usage,
        ("GET", "system", "settings"): api.settings_get,
        ("POST", "system", "settings"): api.settings_post,
        ("GET", "system", "audit-logs"): api.audit_logs,
        ("POST", "system", "emergency-block", "toggle"): api.emergency_toggle,
        ("GET", "system", "probe-models"): api.probe,
        ("GET", "agents"): api.agents_list,
        ("POST", "agents", "register"): api.agent_register,
        ("GET", "agents", "manager", "current"): api.manager_current,
        ("POST", "agents", "manager", "set"): api.manager_set,
        ("POST", "agents", "manager", "clear"): api.manager_clear,
        ("POST", "agents", "delegate"): api.delegate,
        ("GET", "messages", "history"): api.msg_history,
        ("POST", "messages", "send"): api.msg_send,
        ("GET", "memories", "list-domains"): api.mem_domains,
        ("GET", "memories", "read"): api.mem_read,
        ("POST", "memories", "write"): api.mem_write,
        ("POST", "memories", "delete"): api.mem_delete,
        ("GET", "memories", "approvals", "pending"): api.approvals_pending,
        ("GET", "tools", "requests", "pending"): api.tools_pending,
        ("GET", "skills"): api.skills_list,
        ("POST", "skills", "register"): api.skill_register,
        ("GET", "workflows"): api.wf_list,
        ("POST", "workflows", "create"): api.wf_create,
        ("GET", "projects"): api.pj_list,
        ("POST", "projects", "create"): api.pj_create,
        ("GET", "crons"): api.cron_list,
        ("POST", "crons", "create"): api.cron_create,
    }
    key = (method,) + tuple(parts)
    fn = simple.get(key)
    if fn:
        return fn(q, b)

    if method == "GET" and len(parts) == 2 and parts[0] == "agents":
        return api.agent_detail(parts[1], q, b)
    if method == "POST" and len(parts) == 3 and parts[0] == "agents":
        if parts[2] == "update":
            return api.agent_update(parts[1], q, b)
        if parts[2] == "autoreply":
            return api.agent_autoreply(parts[1], q, b)
    if method == "POST" and parts[:3] == ["memories", "approvals", "decide"]:
        return api.approval_decide("memory", q, b)
    if method == "POST" and parts[:3] == ["tools", "approvals", "decide"]:
        return api.approval_decide("tool", q, b)
    if method == "POST" and len(parts) == 3 and parts[0] == "skills":
        return api.skill_disable(parts[1], q, b)
    if len(parts) >= 3 and parts[0] == "workflows":
        wid = parts[1]
        rest = parts[2:]
        if method == "GET" and not rest:
            return api.wf_detail(wid, q, b)
        if method == "POST" and rest == ["update"]:
            return api.wf_update(wid, q, b)
        if method == "POST" and rest == ["run"]:
            return api.wf_run(wid, q, b)
        if method == "GET" and rest == ["runs"]:
            return api.wf_runs(wid, q, b)
        if method == "POST" and rest == ["delete"]:
            return api.wf_delete(wid, q, b)
    if parts[0] == "projects":
        pid = parts[1] if len(parts) > 1 else ""
        if method == "GET" and len(parts) == 2:
            return api.pj_detail(pid, q, b)
        if method == "POST" and len(parts) == 3 and parts[2] == "delete":
            return api.pj_delete(pid, q, b)
    if len(parts) >= 3 and parts[0] == "crons":
        cid = parts[1]
        rest = parts[2:]
        if method == "POST" and rest == ["toggle"]:
            return api.cron_toggle(cid, q, b)
        if method == "POST" and rest == ["run"]:
            return api.cron_run(cid, q, b)
        if method == "POST" and rest == ["delete"]:
            return api.cron_delete(cid, q, b)
        if method == "GET" and rest == ["history"]:
            return api.cron_history(cid, q, b)
    if method == "GET" and parts[:2] == ["files", "list"]:
        return api.files_list(q, b)
    if method == "GET" and parts[:2] == ["files", "content"]:
        return api.files_content(q, b)
    if method == "POST" and len(parts) == 2 and parts[0] == "files":
        if parts[1] == "content":
            return api.files_content(q, b)
        if parts[1] == "create":
            return api.files_create(q, b)
        if parts[1] == "delete":
            return api.files_delete(q, b)
    return 404, {"detail": "未知接口: %s %s" % (method, path)}


class Handler(BaseHTTPRequestHandler):
    api = None  # 注入

    def log_message(self, fmt, *args):  # 安静模式，避免控制台刷屏
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _handle(self, method):
        parsed = urlparse(self.path)
        q = parse_qs(parsed.query)
        body = {}
        if method == "POST":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except (ValueError, json.JSONDecodeError):
                body = {}
        try:
            status, payload = dispatch(self.api, method, parsed.path, q, body)
        except Exception as e:  # 兜底：任何异常都回 JSON 而不是断连
            status, payload = 500, {"detail": "服务器内部错误: %s" % e}
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")


def serve(host=None, port=None, cfg=None):
    cfg = load_config() if cfg is None else dict(load_config(), **(cfg or {}))
    host = host or cfg.get("server_host", DEFAULT_CONFIG.get("server_host", "127.0.0.1"))
    port = int(port or cfg.get("server_port", DEFAULT_CONFIG.get("server_port", 8000)))
    Handler.api = make_api(cfg)
    seed_agents_from_roles(cfg)
    stop_evt = threading.Event()
    threading.Thread(target=_scheduler_loop, args=(Handler.api, stop_evt), daemon=True).start()
    httpd = ThreadingHTTPServer((host, port), Handler)
    print("BlueDeer 底座 API 已启动: http://%s:%d  (前端请指向此地址)" % (host, port))
    print("Ctrl+C 停止。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_evt.set()
        httpd.server_close()


if __name__ == "__main__":
    args = sys.argv[1:]
    h = None
    p = None
    if "--port" in args:
        p = args[args.index("--port") + 1]
    serve(host=h, port=p)
