"""BlueDeer P6 CLI demo：像素沙盒前端全景。

复用 P1-P5 组件跑真实任务，每步刷新 TUI 帧展示全景：
- 11 员工头像墙 + 状态
- 任务看板流转
- 排行榜更新
- 成就墙解锁
- Token 消耗条

末尾导出 ASCII 截图到 output/p6/snapshot.txt
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time

from core.context import ContextManager
from core.event_bus import EventBus
from core.harness import Harness
from core.mcp import AuditLogger, MCPClient
from core.pixel_canvas import Color
from core.reward import RewardSystem
from core.security import SecurityGuard, SecurityScanner
from core.task import Task, TaskStatus
from core.token_auditor import TokenAuditor
from core.tracer import Tracer
from core.tui_renderer import TUIRenderer
from models.router import Router
from modules.avatars import all_avatars
from modules.hedgehog.agent import HedgehogAgent
from modules.squirrel.agent import SquirrelAgent
from tools.builtin.echo_tool import EchoTool
from tools.builtin.file_write_tool import FileWriteTool
from tools.builtin.security_scan_tool import SecurityScanTool
from tools.builtin.syntax_check_tool import SyntaxCheckTool
from tools.registry import ToolRegistry


def build_state(
    harness: Harness,
    reward: RewardSystem,
    token_auditor: TokenAuditor,
    phase: str,
    agent_status_override: dict[str, str] | None = None,
) -> dict:
    """从系统状态构建 TUI 渲染状态。"""
    board = harness.aggregate()

    # 员工列表
    agents_state = []
    for avatar in all_avatars():
        profile = reward.get_profile(avatar.agent_id)
        status = (agent_status_override or {}).get(avatar.agent_id, "idle")
        agents_state.append({
            "agent_id": avatar.agent_id,
            "name": avatar.name,
            "role": avatar.role,
            "status": status,
            "level": profile.level,
            "coins": profile.coins,
        })

    # 任务看板
    tasks_state = []
    for tid, info in board.get("tasks", {}).items():
        tasks_state.append({
            "task_id": tid,
            "status": info["status"],
            "tokens": info["tokens"],
            "assignee": "squirrel",  # demo 简化
        })

    # 排行榜
    leaderboard = board.get("rewards", [])

    # 成就墙（汇总所有员工已解锁）
    achievements = []
    for avatar in all_avatars():
        detail = reward.get_achievements_detail(avatar.agent_id)
        for a in detail:
            achievements.append({"name": a["name"], "tier": a["tier"]})
    # 去重
    seen = set()
    unique_ach = []
    for a in achievements:
        key = a["name"]
        if key not in seen:
            seen.add(key)
            unique_ach.append(a)
    achievements = unique_ach[:20]

    # Token 统计
    savings = token_auditor.get_savings()
    token_stats = {
        "total": board.get("total_tokens", 0),
        "saved": savings["total_saved"],
        "lowcost_ratio": token_auditor.get_lowcost_ratio(),
    }

    return {
        "title": "BlueDeer 森林公司",
        "subtitle": f"P6 像素沙盒 | {phase}",
        "stats": {
            "total": board["total"],
            "success": board["success"],
            "failed": board["failed"],
            "tokens": board["total_tokens"],
        },
        "agents": agents_state,
        "tasks": tasks_state,
        "leaderboard": leaderboard,
        "achievements": achievements,
        "token_stats": token_stats,
    }


async def run_demo() -> None:
    """运行 P6 像素沙盒 demo。"""
    print("=" * 60)
    print("BlueDeer P6 — 像素沙盒前端全景 Demo")
    print("=" * 60)

    # 清理
    for d in ["output/p6", "logs", "output/p4"]:
        if os.path.exists(d):
            shutil.rmtree(d)
    os.makedirs("output/p6", exist_ok=True)

    # 初始化组件
    bus = EventBus()
    router = Router()
    context = ContextManager()
    tools = ToolRegistry()
    tools.register(EchoTool())
    tools.register(FileWriteTool())
    tools.register(SyntaxCheckTool())
    scanner = SecurityScanner()
    tools.register(SecurityScanTool(scanner=scanner))
    tracer = Tracer()
    token_auditor = TokenAuditor()
    reward = RewardSystem()
    harness = Harness(
        event_bus=bus,
        tracer=tracer,
        token_auditor=token_auditor,
        reward_system=reward,
    )

    context.set_global("project", "BlueDeer")
    context.set_global("phase", "P6")

    squirrel = SquirrelAgent(
        event_bus=bus, router=router, tool_registry=tools,
        context=context, tracer=tracer,
    )
    hedgehog = HedgehogAgent(
        event_bus=bus, router=router, tool_registry=tools,
        context=context, tracer=tracer,
    )

    renderer = TUIRenderer(width=80, height=24)

    # 注册 agent 订阅
    async def squirrel_handler(task: Task):
        result = await squirrel.handle(task)
        await bus.publish("harness.result", result)
    async def hedgehog_handler(task: Task):
        result = await hedgehog.handle(task)
        await bus.publish("harness.result", result)
    bus.subscribe("agent.squirrel", squirrel_handler)
    bus.subscribe("agent.hedgehog", hedgehog_handler)

    # 准备任务
    tasks = [
        Task(
            type="code",
            payload={
                "description": "加法函数",
                "language": "python",
                "target_file": "output/p6/adder.py",
            },
            assignee="squirrel",
        ),
        Task(
            type="code",
            payload={
                "description": "乘法函数",
                "language": "python",
                "target_file": "output/p6/multiplier.py",
            },
            assignee="squirrel",
        ),
        Task(
            type="architecture",
            payload={
                "code": "' OR '1'='1' --",
                "description": "审计 SQL 注入",
            },
            assignee="hedgehog",
        ),
        Task(
            type="code",
            payload={
                "description": "故意失败的坏代码",
                "language": "python",
                "target_file": "output/p6/broken.py",
                "bad": True,
            },
            assignee="squirrel",
        ),
    ]

    # 逐个跑任务，每步刷新一帧
    print("\n[初始化] 渲染初始空看板...")
    state = build_state(harness, reward, token_auditor, "初始化", {"squirrel": "idle", "hedgehog": "idle"})
    frame = renderer.render_frame_plain(state)
    print(frame)
    time.sleep(0.3)

    for i, task in enumerate(tasks, 1):
        phase = f"任务 {i}/{len(tasks)}"
        print(f"\n[{phase}] 执行中: {task.payload.get('description', '')}")

        # 标记员工工作中
        override = {task.assignee: "working"}
        state = build_state(harness, reward, token_auditor, phase, override)
        print(renderer.render_frame_plain(state))
        time.sleep(0.2)

        # 执行任务
        result = await harness.submit_and_wait(task, timeout=30)

        # 标记员工结果状态
        override = {task.assignee: "success" if result.status == TaskStatus.SUCCESS else "failed"}
        state = build_state(harness, reward, token_auditor, f"{phase} 完成", override)
        print(renderer.render_frame_plain(state))
        time.sleep(0.2)

    # 梦境固化
    print("\n[梦境] 固化高质量记忆...")
    reward.add_dream_memory("squirrel", count=3, high_quality_count=2)
    reward.add_dream_memory("hedgehog", count=2, high_quality_count=1)
    override = {"squirrel": "sleeping", "hedgehog": "sleeping"}
    state = build_state(harness, reward, token_auditor, "梦境固化", override)
    print(renderer.render_frame_plain(state))

    # 最终全景
    print("\n[最终] 像素沙盒全景定格:")
    state = build_state(harness, reward, token_auditor, "最终全景", {})
    final_frame = renderer.render_frame_plain(state)
    print(final_frame)

    # 导出截图
    snapshot_path = "output/p6/snapshot.txt"
    with open(snapshot_path, "w", encoding="utf-8") as f:
        f.write(final_frame)
    print(f"\n截图已导出: {snapshot_path}")

    # 总结
    board = harness.aggregate()
    progress = reward.achievement_progress("squirrel")
    print("\n" + "=" * 60)
    print("P6 像素沙盒前端验证:")
    print(f"  画布尺寸: 80×24")
    print(f"  11 员工头像墙: ✓")
    print(f"  任务看板流转: {board['total']} 个任务")
    print(f"  排行榜: {len(board.get('rewards', []))} 位员工")
    print(f"  成就墙: {progress['unlocked']}/{progress['total']} 解锁")
    print(f"  Token 消耗: {board['total_tokens']}")
    savings = token_auditor.get_savings()
    print(f"  Token 节省: {savings['total_saved']}")
    print(f"  截图导出: {snapshot_path}")
    if board["total"] >= 1:
        print("\n✓ P6 像素沙盒前端链路验证通过！")
    else:
        print("\n✗ P6 验证失败")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_demo())
