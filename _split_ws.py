#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性机械拆分 web_server.py -> web_server/ 包。
规则：保留 app 实例/全局/中间件/startup/shutdown/websocket/静态挂载在主文件，
路由块按路径前缀分到 routes_*.py（@app.x -> @router.x），末尾 __main__ 提取。
运行后验证：import web_server; 路由路径集合不变。
"""
import os, re, shutil

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "web_server.py")
PKG = os.path.join(BASE, "web_server")

lines = open(SRC, encoding="utf-8").read().split("\n")
n = len(lines)

# 找缩进为 0 的 @app. 装饰行作为 anchor
anchor_re = re.compile(r'^@app\.(\w+)\(')
anchors = []  # (lineno0based, method, raw)
for i, ln in enumerate(lines):
    if ln.startswith("@app.") and anchor_re.match(ln):
        m = anchor_re.match(ln)
        anchors.append((i, m.group(1), ln.strip()))

def path_of(deco_line):
    mm = re.search(r'"([^"]+)"', deco_line)
    return mm.group(1) if mm else ""

def classify(method, deco_line):
    if method in ("middleware", "on_event", "websocket"):
        return "app"
    p = path_of(deco_line)
    if p.startswith("/admin"):
        return "admin"
    if p.startswith("/api/users"):
        return "users"
    if p in ("/api/status", "/api/scene", "/api/jarvis", "/api/github") \
       or p.startswith("/api/system") or p.startswith("/api/rag") \
       or p.startswith("/api/rewards") or p.startswith("/api/cleanup") \
       or p.startswith("/api/backups"):
        return "system"
    if p.startswith("/api/traces") or p.startswith("/api/canvas"):
        return "traces"
    if p.startswith("/api/plugins"):
        return "plugins"
    if p.startswith("/api/agents"):
        return "agents"
    if p.startswith("/api/dag") or p in ("/api/gantt", "/api/tasks/retry") \
       or p.startswith("/api/dag-templates") or p == "/api/audit":
        return "dag"
    if p.startswith("/api/alerts"):
        return "alerts"
    if p.startswith("/api/vector"):
        return "vector"
    if p in ("/", "/vector", "/debug"):
        return "pages"
    return "misc"

# 分组
groups = {}  # name -> list of block text
# 收集原路径集合（用于验证）
orig_paths = set()
for ai, (ln, method, deco) in enumerate(anchors):
    end = anchors[ai + 1][0] if ai + 1 < len(anchors) else n
    block = "\n".join(lines[ln:end]).rstrip("\n")
    if method in ("get", "post", "put", "delete", "patch"):
        orig_paths.add(path_of(deco))
    g = classify(method, deco)
    if g == "app":
        groups.setdefault("__app__", []).append(block)
    else:
        # 改装饰器 @app. -> @router.
        new_block = re.sub(r'^@app\.', '@router.', block, flags=re.M)
        groups.setdefault(g, []).append(new_block)

# 头部 [0, first_anchor)
first = anchors[0][0]
header = "\n".join(lines[:first]).rstrip("\n") + "\n"

# 尾部（最后一个 anchor 之后）
last = anchors[-1][0]
tail = "\n".join(lines[last + 1:]).rstrip("\n")
# 提取 if __name__ 块到 __main__
main_block = ""
mm = re.search(r'if __name__ == ["\']__main__["\']:.*', tail, re.DOTALL)
if mm:
    main_block = mm.group(0)

# 写包
if os.path.isdir(PKG):
    shutil.rmtree(PKG)
os.makedirs(PKG)

GLOBALS_IMPORT = (
    "from web_server.app import (\n"
    "    app, cache_response, invalidate_cache,\n"
    "    library, breakroom, office_manager, rest_area, jarvis,\n"
    "    plugin_manager, vector_browser, debugger, canvas, scene,\n"
    "    github_kb, scheduler, webhook, harness, ws_manager,\n"
    ")\n"
)

router_files = {
    "admin": "routes_admin.py",
    "users": "routes_users.py",
    "system": "routes_system.py",
    "traces": "routes_traces.py",
    "plugins": "routes_plugins.py",
    "agents": "routes_agents.py",
    "dag": "routes_dag.py",
    "alerts": "routes_alerts.py",
    "vector": "routes_vector.py",
    "pages": "routes_pages.py",
    "misc": "routes_misc.py",
}

router_regions = []
for g, fname in router_files.items():
    if g not in groups:
        continue
    body = "\n\n\n".join(groups[g])
    content = (
        "# 自动拆分自 web_server.py（路由域: %s）\n"
        "from fastapi import APIRouter\n"
        "%s\n"
        "router = APIRouter()\n\n\n"
        "%s\n" % (g, GLOBALS_IMPORT, body)
    )
    open(os.path.join(PKG, fname), "w", encoding="utf-8").write(content)
    router_regions.append((g, fname))

# app.py：header + app类块 + 路由注册 + 静态/尾部
app_parts = [header]
app_parts.append("\n".join(groups.get("__app__", [])))
# 路由注册区
reg_lines = ["\n\n# ===== 路由注册（自动拆分） ====="]
for g, fname in router_regions:
    mod = fname[:-3]
    reg_lines.append("from .%s import router as _%s_router" % (mod, g))
reg_lines.append("")
for g, fname in router_regions:
    reg_lines.append("app.include_router(_%s_router)" % g)
app_parts.append("\n".join(reg_lines))
app_py = "\n".join(app_parts).rstrip("\n") + "\n"
open(os.path.join(PKG, "app.py"), "w", encoding="utf-8").write(app_py)

# __init__.py
open(os.path.join(PKG, "__init__.py"), "w", encoding="utf-8").write(
    "from .app import app\n\n__all__ = [\"app\"]\n"
)
# __main__.py
main_content = (
    "from web_server.app import app\n"
    "import uvicorn\n\n"
    "if __name__ == \"__main__\":\n"
    "    uvicorn.run(app, host=\"0.0.0.0\", port=8080)\n"
) if not main_block else (
    "from web_server.app import app\n"
    "import uvicorn\n\n" + main_block + "\n"
)
open(os.path.join(PKG, "__main__.py"), "w", encoding="utf-8").write(main_content)

# 备份并移走原文件
trash = os.path.join(BASE, "._trash")
os.makedirs(trash, exist_ok=True)
shutil.move(SRC, os.path.join(trash, "web_server.py.bak"))
print("拆分完成。")
print("app类块数:", len(groups.get("__app__", [])))
print("路由分组:", {g: len(groups[g]) for g in groups if g != "__app__"})
print("原路由路径数:", len(orig_paths))
print("已备份原文件 -> ._trash/web_server.py.bak")
