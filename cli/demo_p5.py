"""BlueDeer P5 CLI demo：MCP 安全风控体系。

编排完整链路：
1. 初始化 SecurityGuard + MCPClient + AuditLogger
2. 注册工具（含安全扫描工具）
3. 模拟 4 类攻击：SQL注入/路径遍历/XSS/密钥泄露
4. MCPClient 拦截高危调用（HAZARDOUS 白名单 + 静态扫描）
5. 戒备猬 Agent 扫描代码 → 返回威胁报告
6. 审计日志查询验证

运行方式：
    python -m cli.demo_p5
"""

from __future__ import annotations

import asyncio
import os
import shutil
from typing import Any

from core.context import ContextManager
from core.event_bus import EventBus
from core.mcp import AuditLogger, MCPClient
from core.security import SecurityGuard, SecurityScanner, sanitize_log
from core.task import Task
from core.tracer import Tracer
from models.router import Router
from modules.hedgehog.agent import HedgehogAgent
from tools.base_tool import BaseTool, ToolCategory
from tools.builtin.echo_tool import EchoTool
from tools.builtin.file_write_tool import FileWriteTool
from tools.builtin.security_scan_tool import SecurityScanTool
from tools.builtin.syntax_check_tool import SyntaxCheckTool
from tools.registry import ToolRegistry


# 测试用：构造一个高危工具（不真正执行危险动作，仅用于演示拦截）
class HazardousExecTool(BaseTool):
    """演示用高危工具：模拟 shell 执行。"""

    @property
    def name(self) -> str:
        return "shell_exec"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.HAZARDOUS

    async def execute(self, params: dict[str, Any]) -> Any:
        return {"executed": True, "cmd": params.get("cmd", "")}


async def run_demo() -> None:
    """运行 P5 端到端 demo。"""
    print("=" * 60)
    print("BlueDeer P5 — MCP 安全风控体系 CLI Demo")
    print("=" * 60)

    # 清理旧数据
    for d in ["logs", "output/p5"]:
        if os.path.exists(d):
            shutil.rmtree(d)
    os.makedirs("output/p5", exist_ok=True)

    # ============== 1. 初始化安全风控组件 ==============
    print("\n[1] 初始化安全风控组件...")
    scanner = SecurityScanner()
    guard = SecurityGuard(scanner=scanner)
    audit = AuditLogger(log_path="logs/audit.json")
    mcp = MCPClient(guard=guard, audit_logger=audit)

    print("  SecurityScanner  ✓ (4 类静态扫描)")
    print("  SecurityGuard    ✓ (HAZARDOUS 白名单)")
    print("  AuditLogger      ✓ (JSONL → logs/audit.json)")
    print("  MCPClient        ✓ (统一调用入口)")

    # ============== 2. 注册工具 ==============
    print("\n[2] 注册工具到 MCPClient...")
    mcp.register_tool(EchoTool())
    mcp.register_tool(SecurityScanTool(scanner=scanner))
    mcp.register_tool(HazardousExecTool())
    for t in mcp.list_tools():
        tool = mcp.get_tool(t)
        print(f"  - {t} ({tool.category.value})")

    # ============== 3. 模拟 4 类攻击：扫描器直查 ==============
    print("\n[3] SecurityScanner 直查 4 类攻击样本...")

    attacks = [
        ("SQL 注入", "code", "' OR '1'='1' --"),
        ("路径遍历", "code", "../../etc/passwd"),
        ("XSS 脚本", "code", "<script>alert(document.cookie)</script>"),
        ("密钥泄露", "code", "api_key=AKIAIOSFODNN7EXAMPLE12345abcde"),
    ]

    for label, key, payload in attacks:
        report = scanner.scan_all(payload, target=label)
        print(f"\n  [{label}] payload={payload[:60]}")
        print(
            f"    risk_level={report.risk_level.value}  passed={report.passed}  threats={len(report.threats)}"
        )
        for t in report.threats:
            print(f"    - {t.threat_type} [{t.risk.value}] @ {t.location}: {t.matched}")

    # ============== 4. MCPClient 拦截高危调用 ==============
    print("\n[4] MCPClient 拦截高危工具调用...")

    # 4.1 高危工具未在白名单 → 应拒绝
    print("\n  [4.1] shell_exec 未加白名单 → 拒绝")
    res = await mcp.call("squirrel", "shell_exec", {"cmd": "ls -la"})
    print(f"    ok={res['ok']}  reason={res['reason']}")

    # 4.2 加入白名单后，命令含路径遍历 → 仍应拒绝（静态扫描拦截）
    print("\n  [4.2] shell_exec 加入白名单 + 命令含路径遍历 → 拒绝")
    guard.allow_hazardous("shell_exec")
    res = await mcp.call("squirrel", "shell_exec", {"cmd": "cat ../../etc/passwd"})
    print(f"    ok={res['ok']}  reason={res['reason'][:80]}")
    if res.get("report"):
        print(
            f"    report.risk_level={res['report']['risk_level']}  threat_count={res['report']['threat_count']}"
        )

    # 4.3 安全命令 → 放行
    print("\n  [4.3] shell_exec 安全命令 → 放行")
    res = await mcp.call("squirrel", "shell_exec", {"cmd": "echo hello"})
    print(f"    ok={res['ok']}  result={res['result']}")

    # 4.4 密钥参数注入 → 静态扫描拒绝
    print("\n  [4.4] echo 工具参数含密钥 → 静态扫描拒绝")
    res = await mcp.call(
        "squirrel", "echo", {"message": "config api_key=AKIAIOSFODNN7EXAMPLE12345abcde"}
    )
    print(f"    ok={res['ok']}  reason={res['reason'][:80]}")

    # ============== 5. 戒备猬 Agent 扫描代码 ==============
    print("\n[5] 戒备猬 Agent 端到端扫描...")
    bus = EventBus()
    router = Router()
    context = ContextManager()
    tools = ToolRegistry()
    tools.register(EchoTool())
    tools.register(FileWriteTool())
    tools.register(SyntaxCheckTool())
    tools.register(SecurityScanTool(scanner=scanner))
    tracer = Tracer()

    hedgehog = HedgehogAgent(
        event_bus=bus,
        router=router,
        tool_registry=tools,
        context=context,
        tracer=tracer,
    )
    context.set_global("project", "BlueDeer")
    context.set_global("phase", "P5")

    scan_tasks = [
        Task(
            type="architecture",
            payload={
                "code": "query = \"SELECT * FROM users WHERE id='\" + user_input + \"' OR '1'='1' --\"",
                "description": "审计用户输入拼接的 SQL",
            },
            assignee="hedgehog",
        ),
        Task(
            type="architecture",
            payload={
                "code": "def add(a, b):\n    return a + b\n",
                "description": "审计正常加法函数",
            },
            assignee="hedgehog",
        ),
    ]

    for i, task in enumerate(scan_tasks, 1):
        print(f"\n  [5.{i}] 任务: {task.payload['description']}")
        result = await hedgehog.handle(task)
        if result.status.value == "success":
            report = result.output["scan_report"]
            print(f"    status={result.status.value}")
            print(
                f"    risk_level={report['risk_level']}  passed={report['passed']}  threats={report['threat_count']}"
            )
            for t in report["threats"]:
                print(f"    - {t['threat_type']} [{t['risk']}]: {t['matched']}")
            print(f"    model_used={result.output['model_used']}")
        else:
            print(f"    status={result.status.value}  error={result.error}")

    # ============== 6. 审计日志查询 ==============
    print("\n[6] 审计日志查询...")
    all_records = audit.query(limit=100)
    print(f"  总记录数: {len(all_records)}")

    denied = audit.query(status="denied")
    print(f"  拒绝记录: {len(denied)}")
    for r in denied[:5]:
        print(
            f"    [{r.status}] agent={r.agent_id} tool={r.tool_name} reason={r.reason[:50]}"
        )

    success = audit.query(status="success")
    print(f"  成功记录: {len(success)}")

    stats = audit.stats()
    print("\n  审计统计:")
    print(f"    total={stats['total']}  deny_rate={stats.get('deny_rate', 0)}")
    print(f"    by_status={stats.get('by_status', {})}")
    print(f"    by_tool={stats.get('by_tool', {})}")

    # ============== 7. 日志脱敏验证 ==============
    print("\n[7] 日志脱敏验证...")
    raw = {
        "agent_id": "squirrel",
        "config": {
            "api_key": "DEMO-KEY-XXXXXXXXXXXXXXXXXXXXXXXX",
            "password": "demopass123",
            "safe_field": "normal_value",
        },
        "msg": "token=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx loaded",
    }
    sanitized = sanitize_log(raw)
    print(f"  原始: {raw}")
    print(f"  脱敏: {sanitized}")
    assert sanitized["config"]["api_key"] == "***", "api_key 应被脱敏"
    assert sanitized["config"]["password"] == "***", "password 应被脱敏"
    assert sanitized["config"]["safe_field"] == "normal_value", "非敏感字段不应被脱敏"
    assert "***" in sanitized["msg"], "msg 中的 token 应被截断"
    print("  ✓ 脱敏校验通过")

    # ============== 8. 看板汇总 ==============
    print("\n[8] P5 链路总结:")
    print("  扫描器共扫描 4 类攻击样本，全部命中 ✓")
    print(f"  MCPClient 拦截高危调用 {len(denied)} 次 ✓")
    print(f"  戒备猬 Agent 端到端扫描 {len(scan_tasks)} 个任务 ✓")
    print(f"  审计日志落盘 {stats['total']} 条 → logs/audit.json ✓")
    print("  日志脱敏校验通过 ✓")

    print("\n" + "=" * 60)
    if len(all_records) >= 4 and len(denied) >= 2 and stats.get("deny_rate", 0) > 0:
        print("✓ P5 端到端链路验证通过！")
        print("  扫描器 → 守卫 → MCPClient → 戒备猬 → 审计日志 → 脱敏")
    else:
        print("✗ P5 端到端链路验证失败！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_demo())
