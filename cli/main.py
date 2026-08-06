"""BlueDeer 统一 CLI 入口。

用法：
    bluedeer web                  启动 Web 仪表盘
    bluedeer demo [n]             运行 demo（1-8）
    bluedeer plugins list         列出已发现插件
    bluedeer plugins install <n>  安装插件（复制到 plugins/）
    bluedeer vector               查看向量库统计
    bluedeer board [save|load|show]  任务看板管理
    bluedeer trace [--count N] [--filter key=val] [--json]  查看 trace
    bluedeer report [--format md|html] [--title T]  生成任务报告
    bluedeer schedule list|add|remove|enable|disable  定时任务管理
    bluedeer webhook list|add|remove|enable|disable   Webhook 管理
    bluedeer alert status|list|events                 告警规则与事件
    bluedeer backup create|list|restore|delete        数据备份
    bluedeer cleanup run|stats                        数据清理
    bluedeer game status                             森林生物圈状态
    bluedeer init-config [path]   生成示例配置文件
"""

from __future__ import annotations

import argparse
import os
import sys
import time


class Color:
    G = "\033[92m"  # green
    Y = "\033[93m"  # yellow
    R = "\033[91m"  # red
    B = "\033[94m"  # blue
    C = "\033[96m"  # cyan
    M = "\033[95m"  # magenta
    D = "\033[90m"  # dim/grey
    N = "\033[0m"  # reset

    @staticmethod
    def ok(msg: str) -> str:
        return f"{Color.G}{msg}{Color.N}"

    @staticmethod
    def warn(msg: str) -> str:
        return f"{Color.Y}{msg}{Color.N}"

    @staticmethod
    def err(msg: str) -> str:
        return f"{Color.R}{msg}{Color.N}"

    @staticmethod
    def info(msg: str) -> str:
        return f"{Color.B}{msg}{Color.N}"

    @staticmethod
    def dim(msg: str) -> str:
        return f"{Color.D}{msg}{Color.N}"

    @staticmethod
    def tag(t: str, msg: str) -> str:
        return f"[{Color.M}{t}{Color.N}] {msg}"

    @staticmethod
    def mute():
        return not sys.stdout.isatty()


_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from core.logger import init_logging


def cmd_web(args: argparse.Namespace) -> None:
    import uvicorn

    host = args.host or "0.0.0.0"
    port = args.port or 8080
    print(
        f"{Color.B}🌲{Color.N} BlueDeer {Color.C}Web{Color.N} 仪表盘 → http://{host}:{port}"
    )
    uvicorn.run("web_server:app", host=host, port=port, reload=args.reload)


def cmd_serve(args: argparse.Namespace) -> None:
    """一键启动（web + ws + admin，开发模式默认关闭登录认证）。"""
    import uvicorn

    host = args.host or "0.0.0.0"
    port = args.port or 8080
    if args.dev:
        os.environ["BLUEDEER_AUTH"] = "false"
        print("🦌 BlueDeer 开发模式 — admin 认证已关闭")
    print(f"🦌 BlueDeer 全栈服务 → http://{host}:{port}")
    print(f"   Admin 面板 → http://{host}:{port}/admin")
    print(f"   API 文档   → http://{host}:{port}/docs")
    print(f"   WebSocket  → ws://{host}:{port}/ws")
    uvicorn.run("web_server:app", host=host, port=port, reload=args.reload)


def cmd_demo(args: argparse.Namespace) -> None:
    level = args.level or 1
    if level == 1:
        import asyncio

        from cli.demo import run_demo

        asyncio.run(run_demo())
    elif 2 <= level <= 8:
        mod_name = f"cli.demo_p{level}"
        import importlib

        mod = importlib.import_module(mod_name)
        if hasattr(mod, "main"):
            mod.main()
        elif hasattr(mod, "run_demo"):
            import asyncio

            asyncio.run(mod.run_demo())
        else:
            print(Color.err(f"❌ demo_p{level} 没有 main/run_demo 入口"))
            sys.exit(1)
    else:
        print(Color.err(f"❌ 不支持的 demo 等级: {level}（支持 1-8）"))
        sys.exit(1)


def cmd_plugins(args: argparse.Namespace) -> None:
    import asyncio

    from core.plugin_manager import PluginManager
    from core.plugin_repo import PluginRepo

    pm = PluginManager(plugin_dir="plugins")
    repo = PluginRepo(plugin_dir="plugins")
    if args.action == "list":
        names = pm.discover()
        if not names:
            print(Color.dim("📭 未发现插件"))
            return
        print(Color.info(f"📦 发现 {len(names)} 个插件:"))
        for name in names:
            status = pm.get_status(name)
            m = status.get("manifest", {})
            print(
                f"  [{status.get('status','?')}] {m.get('name', name)} v{m.get('version', '?')}"
            )
            if m.get("description"):
                print(f"       {m['description']}")
    elif args.action == "search":
        from core.plugin_repo import PluginRepo

        pr = PluginRepo()
        result = pr.search_github(query=args.name, max_results=20)
        if result.error:
            print(Color.err(f"❌ {result.error}"))
            return
        if not result.plugins:
            print(Color.dim("📭 未搜索到远程插件"))
            return
        print(Color.info(f"🔍 搜索到 {result.total} 个远程插件:"))
        for p in result.plugins:
            tag = "✅ 已安装" if p.installed else "⬇️ 可安装"
            print(f"  {tag} {p.name} v{p.version}")
            print(f"       {p.description[:80]}")
            print(f"       👤 {p.author}  🔗 {p.source_url}")
    elif args.action == "install":
        if args.zip:
            ok, msg = repo.install_from_zip(args.zip, target_name=args.name or "")
        else:
            name = args.name
            src = (
                os.path.join("plugins_src", name)
                if os.path.isdir(os.path.join("plugins_src", name))
                else name
            )
            if not os.path.exists(src):
                print(Color.err(f"❌ 未找到插件源: {src}"))
                sys.exit(1)
            dst = os.path.join("plugins", os.path.basename(name))
            import shutil

            if os.path.exists(dst):
                print(Color.warn(f"⚠️ 插件 {name} 已存在，覆盖..."))
                shutil.rmtree(dst) if os.path.isdir(dst) else os.remove(dst)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            print(Color.ok(f"✅ 插件 {name} 已安装 → {dst}"))
            loaded = asyncio.run(pm.load_one(os.path.basename(name)))
            if loaded:
                print(Color.ok(f"✅ 插件 {name} 加载成功"))
            return
        print(msg)
        if ok:
            loaded = asyncio.run(pm.load_one(args.name or os.path.basename(args.zip)))
            if loaded:
                print(Color.ok("✅ 插件加载成功"))
    elif args.action == "install-git":
        if not args.url:
            print(Color.err("❌ 请指定 --url Git 仓库地址"))
            sys.exit(1)
        ok, msg = repo.install_from_git(
            args.url, branch=args.branch, target_name=args.name
        )
        print(msg)
        if ok:
            loaded = asyncio.run(
                pm.load_one(args.name or os.path.basename(args.url).replace(".git", ""))
            )
            if loaded:
                print(Color.ok("✅ 插件加载成功"))
    elif args.action == "uninstall":
        ok, msg = repo.uninstall(args.name)
        print(msg)
    elif args.action == "enable":
        ok = pm.enable(args.name)
        print(Color.ok("✅") if ok else Color.err("❌"))
    elif args.action == "disable":
        ok = pm.disable(args.name)
        print(Color.ok("✅") if ok else Color.err("❌"))
    else:
        print(Color.err(f"❌ 未知插件操作: {args.action}"))
        sys.exit(1)


def cmd_agent(args: argparse.Namespace) -> None:
    """Agent 市场：列出、搜索、查看详情。"""
    from core.agent_registry import AgentRegistry

    registry = AgentRegistry()
    if args.action == "list":
        agents = registry.list_agents()
        if not agents:
            print(Color.dim("📭 尚未注册任何 Agent"))
            return
        print(f"🤖 已注册 Agent ({len(agents)}):")
        for a in agents:
            icon = "✅" if a.enabled else "⏸️"
            print(
                f"  {icon} {a.name:20s} v{a.version:6s} [{a.role:12s}] {a.description[:50]}"
            )
    elif args.action == "info":
        info = registry.get_agent(args.name)
        if not info:
            print(Color.err(f"❌ Agent 未找到: {args.name}"))
            return
        print(f"🤖 {info.name}")
        print(f"  角色:        {info.role}")
        print(f"  模块:        {info.module}")
        print(f"  版本:        {info.version}")
        print(f"  描述:        {info.description}")
        print(f"  能力:        {', '.join(info.capabilities) or '—'}")
        print(f"  基类:        {info.base_class}")
        print(f"  来源:        {info.source} {info.source_url}")
        print(f"  状态:        {'✅ 已启用' if info.enabled else '⏸️ 已禁用'}")
    elif args.action == "search":
        if not args.query:
            print(Color.err("❌ 请输入搜索关键词: --query Q"))
            return
        hits = registry.search(args.query)
        if not hits:
            print(f"📭 未找到匹配: {args.query}")
            return
        print(Color.info(f"🔍 搜索「{args.query}」找到 {len(hits)} 个结果:"))
        for a in hits:
            print(f"  {a.name:20s} [{a.role:12s}] {a.description[:60]}")
    else:
        print(Color.err(f"❌ 未知操作: {args.action}"))
        sys.exit(1)


def cmd_vector(args: argparse.Namespace) -> None:
    from core.vector_browser import VectorBrowser

    browser = VectorBrowser(db_root="data")
    stats = browser.layer_stats()
    print(Color.info("📊 向量库统计:"))
    print(f"  总层数:    {stats['total_layers']}")
    print(f"  总文档数:  {stats['total_docs']}")
    for l in stats["layers"]:
        scope = l["scope"]
        sub = f"/{l['sub_id']}" if l["sub_id"] else ""
        print(f"  [{scope}]{sub} → {l['doc_count']} 篇文档")


def cmd_board(args: argparse.Namespace) -> None:
    from core.event_bus import EventBus
    from core.harness import Harness

    bus = EventBus()
    h = Harness(bus)
    path = args.file or "data/task_state.json"
    if args.action == "save":
        count = h.save_state(path)
        print(Color.info(f"💾 已保存 {count} 条任务记录 → {path}"))
    elif args.action == "load":
        count = h.load_state(path)
        print(Color.info(f"📂 已恢复 {count} 条任务记录 ← {path}"))
    elif args.action == "show":
        stats = h.aggregate()
        print(
            Color.info(
                f"📊 任务看板: {stats['total']} 总计, {stats['success']} 成功, {stats['failed']} 失败, {stats['pending']} 待处理"
            )
        )
        for tid, r in stats["tasks"].items():
            print(
                f"  [{r['status']}] {tid}"
                + (f" — {r.get('error','')}" if r.get("error") else "")
            )


def cmd_trace(args: argparse.Namespace) -> None:
    trace_file = "logs/trace.log"
    if not os.path.exists(trace_file):
        print(Color.dim("📭 暂无 trace 日志"))
        return
    with open(trace_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 过滤
    filter_by = getattr(args, "filter", None)
    if filter_by:
        parts = filter_by.split("=", 1)
        if len(parts) == 2:
            key, val = parts
            filtered = [
                l for l in lines if f'"{key}": "{val}"' in l or f'"{key}": "{val}' in l
            ]
            lines = filtered or lines
            print(Color.info(f"🔍 过滤条件 {key}={val} → {len(lines)} 条匹配"))

    # JSON 模式
    if getattr(args, "json_output", False):
        import json

        parsed: list[dict] = []
        for line in lines:
            try:
                parsed.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
        count = args.count or 20
        tail = parsed[-count:]
        print(json.dumps(tail, ensure_ascii=False, indent=2))
        return

    count = args.count or 20
    tail = lines[-count:]
    print(Color.info(f"📜 最近 {len(tail)} 条 trace 日志:"))
    for line in tail:
        print(line.rstrip())


def cmd_report(args: argparse.Namespace) -> None:
    from core.event_bus import EventBus
    from core.harness import Harness
    from core.reporter import ReportGenerator

    bus = EventBus()
    h = Harness(bus)
    stats = h.aggregate()
    task_board = stats.get("tasks", {})

    trace_lines: list[str] = []
    trace_file = "logs/trace.log"
    if os.path.exists(trace_file):
        with open(trace_file, "r", encoding="utf-8") as f:
            trace_lines = f.readlines()

    gen = ReportGenerator()
    fmt = args.format or "markdown"
    path = gen.generate(
        task_board=task_board,
        aggregate_stats=stats,
        trace_lines=trace_lines,
        fmt=fmt,
        title=args.title or "BlueDeer 任务报告",
    )
    print(Color.info(f"📄 报告已生成: {path}"))


def cmd_schedule(args: argparse.Namespace) -> None:
    import asyncio

    from core.event_bus import EventBus
    from core.harness import Harness
    from core.scheduler import JobDef, Scheduler

    bus = EventBus()
    h = Harness(bus)
    sched = Scheduler(bus, h)

    if args.action == "list":
        jobs = sched.list_jobs()
        if not jobs:
            print(Color.dim("📭 无定时任务"))
            return
        print(Color.info(f"📋 定时任务 ({len(jobs)}):"))
        for jid, j in jobs.items():
            flag = "✅" if j.enabled else "⏸️"
            print(
                f"  {flag} [{jid}] {j.cron} → {j.task_type} {'| ' + j.description if j.description else ''}"
            )
    elif args.action == "add":
        job = JobDef(
            id=args.id or f"job_{int(__import__('time').time())}",
            cron=args.cron,
            task_type=args.task_type or "general",
            task_payload={},
            assignee=args.assignee or "",
            description=args.description or "",
        )
        sched.add_job(job)
        print(Color.ok(f"✅ 定时任务已添加: {job.id} [{job.cron}]"))
    elif args.action == "remove":
        ok = sched.remove_job(args.id)
        print(Color.ok("✅") if ok else Color.err("❌"))
    elif args.action == "enable":
        ok = sched.enable_job(args.id)
        print(Color.ok("✅") if ok else Color.err("❌"))
    elif args.action == "disable":
        ok = sched.disable_job(args.id)
        print(Color.ok("✅") if ok else Color.err("❌"))

    asyncio.run(sched.start())


def cmd_webhook(args: argparse.Namespace) -> None:
    import asyncio

    from core.event_bus import EventBus
    from core.webhook import _ALL_EVENTS, WebhookDef, WebhookDispatcher

    bus = EventBus()
    disp = WebhookDispatcher(bus)

    if args.action == "list":
        hooks = disp.list_hooks()
        if not hooks:
            print(Color.dim("📭 无 Webhook 配置"))
            return
        print(Color.info(f"📋 Webhook ({len(hooks)}):"))
        for hid, h in hooks.items():
            flag = "✅" if h.enabled else "⏸️"
            print(f"  {flag} [{hid}] → {h.url}")
            print(f"       事件: {', '.join(h.events)}")
    elif args.action == "add":
        events = args.events or list(_ALL_EVENTS)
        hook = WebhookDef(
            id=args.id or f"hook_{int(__import__('time').time())}",
            url=args.url,
            events=events,
            description=args.description or "",
            secret=args.secret or "",
        )
        disp.add_hook(hook)
        print(Color.ok(f"✅ Webhook 已添加: {hook.id} → {hook.url}"))
    elif args.action == "remove":
        ok = disp.remove_hook(args.id)
        print(Color.ok("✅") if ok else Color.err("❌"))
    elif args.action == "enable":
        ok = disp.enable_hook(args.id)
        print(Color.ok("✅") if ok else Color.err("❌"))
    elif args.action == "disable":
        ok = disp.disable_hook(args.id)
        print(Color.ok("✅") if ok else Color.err("❌"))

    asyncio.run(disp.start())


def cmd_alert(args: argparse.Namespace) -> None:
    """告警规则管理。"""
    from core.alert import get_alert_engine

    ae = get_alert_engine()
    if args.action in ("status", "list"):
        rules = ae.list_rules()
        if not rules:
            print(Color.dim("暂无告警规则"))
            return
        print(f"告警规则 ({len(rules)}):")
        print(
            f"{'ID':20s} {'名称':20s} {'指标':16s} {'条件':12s} {'严重度':10s} {'启用':6s}"
        )
        print("-" * 90)
        for r in rules:
            enabled = "✅" if r["enabled"] else "❌"
            print(
                f"{r['id']:20s} {r['name']:20s} {r['metric']:16s} "
                f"{r['operator']} {r['threshold']:<5.1f} {r['severity']:10s} {enabled:6s}"
            )
    elif args.action == "events":
        events = ae.recent_alerts(limit=args.limit)
        if not events:
            print(Color.dim("暂无告警事件"))
            return
        for e in events:
            ts = __import__("time").strftime(
                "%m-%d %H:%M:%S", __import__("time").localtime(e.get("ts", 0))
            )
            sev = e.get("severity", "?")
            msg = e.get("message", "")[:80]
            print(f"[{ts}] {sev:8s} | {msg}")


def cmd_dag(args: argparse.Namespace) -> None:
    """任务 DAG 依赖图管理。"""
    from core.task_dag import TaskDAG

    dag = TaskDAG()

    if args.action == "list":
        nodes = dag.list_nodes()
        if not nodes:
            print("DAG 为空")
            return
        print(f"DAG 节点 ({len(nodes)}):")
        for n in nodes:
            deps = ", ".join(n.depends_on) if n.depends_on else "无"
            print(f"  [{n.id}] 前置: {deps}  |  {n.description}")
        order = dag.topological_sort()
        print(f"\n拓扑排序: {' → '.join(order)}")
        print("\n执行计划（每行可并行）:")
        for i, layer in enumerate(dag.execution_plan(), 1):
            print(f"  第{i}层: {', '.join(layer)}")

    elif args.action == "add":
        if not args.id:
            print(Color.err("❌ 请指定 --id"))
            return
        dag.add_node(args.id, depends_on=args.depends_on, description=args.description)
        dag.save()
        print(Color.ok(f"✅ DAG 节点已添加: [{args.id}]"))
        if args.depends_on:
            print(f"   前置: {', '.join(args.depends_on)}")

    elif args.action == "remove":
        if not args.id:
            print(Color.err("❌ 请指定 --id"))
            return
        ok = dag.remove_node(args.id)
        dag.save()
        print(Color.ok("✅") if ok else Color.err("❌"))

    elif args.action == "plan":
        if args.from_id:
            nodes = dag.subgraph(args.from_id)
            print(f"子图 [{args.from_id}] 包含 {len(nodes)} 个节点")
        nodes = dag.list_nodes()
        if not nodes:
            print("DAG 为空")
            return
        print(f"\n执行计划（共 {len(nodes)} 节点）:")
        plan = dag.execution_plan()
        for i, layer in enumerate(plan, 1):
            print(f"  第{i}层: {', '.join(layer)}")

    elif args.action == "export":
        path = args.file
        dag.export_json(path)
        print(Color.ok(f"✅ DAG 已导出: {path} ({len(dag.list_nodes())} 节点)"))

    elif args.action == "import":
        path = args.file
        new_dag = TaskDAG.import_json(path)
        new_dag.save()
        print(Color.ok(f"✅ DAG 已导入: {path} ({len(new_dag.list_nodes())} 节点)"))


def cmd_retry(args: argparse.Namespace) -> None:
    """任务重试策略管理。"""
    cfg = get_config().task

    if args.action == "status":
        from core.harness import Harness

        h = Harness()
        mgr = getattr(h, "_retry_mgr", None)
        print("重试策略配置:")
        print(f"  启用:           {'✅' if cfg.retry_enabled else '❌'}")
        print(f"  最大尝试次数:   {cfg.retry_max_attempts}")
        print(f"  基准延迟:       {cfg.retry_base_delay}s")
        print(f"  最大延迟:       {cfg.retry_max_delay}s")
        print(f"  抖动:           {'开' if cfg.retry_jitter else '关'}")
        print(f"  重分配上限:     {cfg.max_reallocate}")
        if mgr:
            summary = mgr.retry_summary()
            if summary:
                print(f"\n活跃重试 ({len(summary)}):")
                for tid, s in summary.items():
                    print(
                        f"  {tid}: 第{s['attempt']}次, 剩余{s['remaining']}次, {s['error'][:60]}"
                    )
            else:
                print("\n无活跃重试")
    elif args.action == "set":
        if args.max_attempts is not None:
            cfg.retry_max_attempts = args.max_attempts
        if args.base_delay is not None:
            cfg.retry_base_delay = args.base_delay
        if args.max_delay is not None:
            cfg.retry_max_delay = args.max_delay
        if args.jitter is not None:
            cfg.retry_jitter = args.jitter
        print(Color.ok("✅ 重试配置已更新"))


def cmd_game(args: argparse.Namespace) -> None:
    """森林生物圈游戏。"""
    if args.action == "start":
        # 生物圈已集成到 Web 服务器中，直接启动服务即可
        print("🌿 森林生物圈已集成到 Web 服务器中")
        print("   运行 bluedeer serve 自动启动生物圈")
        print("   访问 http://127.0.0.1:8080/game 进入游戏")
    elif args.action == "status":
        import json
        import urllib.request

        try:
            resp = urllib.request.urlopen(
                "http://127.0.0.1:8080/game/api/health", timeout=3
            )
            d = json.loads(resp.read())
            print(Color.ok(f"🟢 生物圈运行中 ({d.get('employees',0)} 名员工)"))
        except Exception:
            print(Color.err("🔴 生物圈未启动"))


def cmd_cleanup(args: argparse.Namespace) -> None:
    """数据清理与维护。"""
    from core.cleanup import get_storage_stats, run_cleanup

    if args.action == "stats":
        stats = get_storage_stats()
        print(
            Color.info(
                f"📊 存储用量: {stats['total_str']} ({len(stats['files'])} 个文件)\n"
            )
        )
        for f in stats["files"][:20]:
            print(f"  {f['size_str']:>8}  {f['path']}")
        if len(stats["files"]) > 20:
            print(f"  ... 以及 {len(stats['files'])-20} 个其他文件")
        return

    if args.action == "run":
        result = run_cleanup(dry_run=args.dry_run, max_days=args.max_days)
        tag = " [试运行]" if args.dry_run else ""
        print(Color.ok(f"✅ 清理完成{tag}"))
        print(f"  移除: {result.removed} 条记录")
        print(f"  释放: {result.freed_bytes/1024:.1f} KB")
        if result.db_vacuumed:
            print("  🗃️  数据库已压缩")
        if result.errors:
            for e in result.errors:
                print(f"  ❌ {e}")


def cmd_backup(args: argparse.Namespace) -> None:
    """数据备份与恢复。"""
    from core.backup import create_backup, delete_backup, list_backups, restore_backup

    if args.action == "create":
        path = create_backup(name=args.name, db_only=args.db_only)
        print(Color.ok(f"✅ 备份完成: {path}"))

    elif args.action == "list":
        backups = list_backups()
        if not backups:
            print(Color.dim("暂无备份"))
            return
        print(f"共 {len(backups)} 个备份:\n")
        for b in backups:
            size_mb = b["size_bytes"] / 1024 / 1024
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(b["created_at"]))
            name = b["filename"]
            print(f"  {name}  ({size_mb:.1f} MB, {ts})")

    elif args.action == "restore":
        fp = args.file or ""
        if not fp:
            backups = list_backups()
            if not backups:
                print("无备份可用")
                return
            fp = backups[0]["path"]
        files = restore_backup(fp, dry_run=args.dry_run)
        tag = " [试运行]" if args.dry_run else ""
        print(Color.ok(f"✅ 恢复完成{tag}: {len(files)} 个文件"))

    elif args.action == "delete":
        if not args.file:
            print("请指定 --file")
            return
        ok = delete_backup(args.file)
        print(f"{'✅ 已删除' if ok else '❌ 删除失败'}: {args.file}")


def cmd_init_config(args: argparse.Namespace) -> None:
    path = args.path or "bluedeer.toml"
    content = """# BlueDeer 配置文件
# 复制此文件并按需修改，然后运行: bluedeer --config bluedeer.toml web

[app]
environment = "local"
db_root = "vector_db/data"
use_real_api = false

[model]
default_model = "Doubao-Seed-2.1-Pro"
fail_threshold = 3
degrade_ttl_seconds = 30.0

[reward]
coins_success = 10
coins_failed = -8
exp_success = 20
exp_failed = 2

[task]
timeout_seconds = 120.0
max_reallocate = 2
retry_enabled = true
retry_max_attempts = 3
retry_base_delay = 2.0
retry_max_delay = 120.0
retry_jitter = true

[tool]
max_retries = 3
circuit_threshold = 5

[log]
level = "INFO"
log_dir = "logs"

[scheduler]
enabled = false

[webhook]
default_timeout_seconds = 10.0
default_max_retries = 3
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(Color.ok(f"✅ 示例配置文件已生成: {path}"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="🦌 BlueDeer 森林公司 — 多智能体协同框架",
    )
    parser.add_argument("--config", "-c", help="配置文件路径（TOML/YAML）")
    sub = parser.add_subparsers(dest="command", help="子命令")
    try:
        import argcomplete

        argcomplete.autocomplete(parser)
    except ImportError:
        pass

    web_p = sub.add_parser("web", help="启动 Web 仪表盘")
    web_p.add_argument("--host", default="0.0.0.0")
    web_p.add_argument("--port", type=int, default=8080)
    web_p.add_argument("--reload", action="store_true", help="热重载")

    serve_p = sub.add_parser("serve", help="一键启动全栈服务（web + ws + admin）")
    serve_p.add_argument("--host", default="0.0.0.0")
    serve_p.add_argument("--port", type=int, default=8080)
    serve_p.add_argument(
        "--dev", action="store_true", help="开发模式（关闭 admin 认证）"
    )
    serve_p.add_argument("--reload", action="store_true", help="热重载")

    demo_p = sub.add_parser("demo", help="运行 demo")
    demo_p.add_argument("level", nargs="?", type=int, default=1)

    plugin_p = sub.add_parser("plugins", help="插件管理")
    plugin_p.add_argument(
        "action",
        choices=[
            "list",
            "install",
            "enable",
            "disable",
            "search",
            "install-git",
            "uninstall",
        ],
    )
    plugin_p.add_argument("name", nargs="?", default="", help="插件名或搜索词")
    plugin_p.add_argument("--url", default="", help="Git 仓库 URL（install-git 用）")
    plugin_p.add_argument("--branch", default="main", help="Git 分支（默认 main）")
    plugin_p.add_argument("--zip", default="", help="ZIP 下载 URL（install 用）")

    sub.add_parser("vector", help="查看向量库统计")

    board_p = sub.add_parser("board", help="任务看板管理")
    board_p.add_argument(
        "action", choices=["save", "load", "show"], default="show", nargs="?"
    )
    board_p.add_argument("--file", "-f", default="data/task_state.json")

    trace_p = sub.add_parser("trace", help="查看 trace 日志")
    trace_p.add_argument("--count", "-n", type=int, default=20)
    trace_p.add_argument("--filter", help="过滤条件 key=val")
    trace_p.add_argument(
        "--json", dest="json_output", action="store_true", help="JSON 格式输出"
    )

    report_p = sub.add_parser("report", help="生成任务报告")
    report_p.add_argument("--format", choices=["markdown", "html"], default="markdown")
    report_p.add_argument("--title", default="BlueDeer 任务报告")
    report_p.add_argument("--output", "-o", default="")

    sched_p = sub.add_parser("schedule", help="定时任务管理")
    sched_p.add_argument(
        "action", choices=["list", "add", "remove", "enable", "disable"]
    )
    sched_p.add_argument("--id", help="任务 ID")
    sched_p.add_argument("--cron", help="cron 表达式（6 段）")
    sched_p.add_argument("--task-type", default="general")
    sched_p.add_argument("--assignee", default="")
    sched_p.add_argument("--desc", dest="description", default="")

    wh_p = sub.add_parser("webhook", help="Webhook 管理")
    wh_p.add_argument("action", choices=["list", "add", "remove", "enable", "disable"])
    wh_p.add_argument("--id", help="Hook ID")
    wh_p.add_argument("--url", help="回调 URL")
    wh_p.add_argument("--events", nargs="*", help="监听事件列表")
    wh_p.add_argument("--secret", default="", help="签名密钥")
    wh_p.add_argument("--desc", dest="description", default="")

    dag_p = sub.add_parser("dag", help="任务 DAG 依赖图管理")
    dag_p.add_argument(
        "action", choices=["list", "add", "remove", "plan", "export", "import"]
    )
    dag_p.add_argument("--id", help="节点 ID")
    dag_p.add_argument("--depends-on", nargs="*", default=[], help="前置任务 ID 列表")
    dag_p.add_argument("--desc", dest="description", default="")
    dag_p.add_argument("--from", dest="from_id", default="", help="子图根节点")
    dag_p.add_argument(
        "--file", "-f", default="bluedeer_dag.json", help="导入/导出文件路径"
    )

    agent_p = sub.add_parser("agent", help="Agent 市场：列出、搜索、查看详情")
    agent_p.add_argument("action", choices=["list", "info", "search"])
    agent_p.add_argument("name", nargs="?", default="", help="Agent 名称（info 用）")
    agent_p.add_argument("--query", "-q", default="", help="搜索关键词（search 用）")

    agents_p = sub.add_parser("agents", help="Agent 市场（别名）")
    agents_p.add_argument("action", choices=["list", "info", "search"])
    agents_p.add_argument("name", nargs="?", default="")
    agents_p.add_argument("--query", "-q", default="", help="搜索关键词")

    retry_p = sub.add_parser("retry", help="任务重试策略管理")
    retry_p.add_argument("action", choices=["status", "set"])
    retry_p.add_argument("--max-attempts", type=int, help="最大尝试次数")
    retry_p.add_argument("--base-delay", type=float, help="基准延迟（秒）")
    retry_p.add_argument("--max-delay", type=float, help="最大延迟（秒）")
    retry_p.add_argument("--jitter", type=bool, help="启用抖动")

    alert_p = sub.add_parser("alert", help="告警规则管理")
    alert_p.add_argument("action", choices=["status", "list", "events"])
    alert_p.add_argument("--limit", type=int, default=20, help="事件条数")

    game_p = sub.add_parser("game", help="启动森林生物圈游戏")
    game_p.add_argument("--host", default="0.0.0.0")
    game_p.add_argument("--port", type=int, default=9090)
    game_p.add_argument("--password", default="", help="访问密码")
    game_p.add_argument(
        "action", choices=["start", "status"], default="start", nargs="?"
    )

    cleanup_p = sub.add_parser("cleanup", help="数据清理与维护")
    cleanup_p.add_argument(
        "--dry-run", action="store_true", help="试运行（不实际删除）"
    )
    cleanup_p.add_argument(
        "--max-days", type=int, default=14, help="保留天数（默认 14）"
    )
    cleanup_p.add_argument(
        "action", choices=["run", "stats"], default="stats", nargs="?"
    )

    backup_p = sub.add_parser("backup", help="数据备份管理")
    backup_p.add_argument(
        "action",
        choices=["create", "list", "restore", "delete"],
        default="list",
        nargs="?",
    )
    backup_p.add_argument("--name", "-n", default="", help="备份名称")
    backup_p.add_argument("--db-only", action="store_true", help="仅备份数据库")
    backup_p.add_argument("--dry-run", action="store_true", help="试运行（不实际写入）")
    backup_p.add_argument(
        "--file", "-f", default="", help="备份文件路径（restore/delete 用）"
    )

    init_p = sub.add_parser("init-config", help="生成示例配置文件")
    init_p.add_argument("path", nargs="?", default="bluedeer.toml")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    init_logging(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        log_dir="logs",
    )

    if args.config:
        from core.config import AppConfig, set_config

        cfg = AppConfig.from_file(args.config)
        set_config(cfg)

    {
        "web": cmd_web,
        "serve": cmd_serve,
        "demo": cmd_demo,
        "plugins": cmd_plugins,
        "agent": cmd_agent,
        "agents": cmd_agent,
        "vector": cmd_vector,
        "board": cmd_board,
        "trace": cmd_trace,
        "report": cmd_report,
        "schedule": cmd_schedule,
        "webhook": cmd_webhook,
        "dag": cmd_dag,
        "retry": cmd_retry,
        "alert": cmd_alert,
        "backup": cmd_backup,
        "game": cmd_game,
        "cleanup": cmd_cleanup,
        "init-config": cmd_init_config,
    }[args.command](args)


if __name__ == "__main__":
    main()
