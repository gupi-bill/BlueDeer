"""BlueDeer P4 CLI demo：Token 审计 + 游戏化奖惩统计。

编排完整链路：
1. 初始化 TokenAuditor + RewardSystem + Harness（带审计与奖惩）
2. 下发多个代码生成任务（含成功和失败）
3. 每个任务自动记录 Token + 结算金币/经验/好感度
4. 触发成就解锁
5. 打印排行榜 + 各员工档案
6. 导出月度成本报表 MD

运行方式：
    python -m cli.demo_p4
"""

from __future__ import annotations

import asyncio
import os
import shutil

from core.context import ContextManager
from core.event_bus import EventBus
from core.harness import Harness
from core.reward import RewardSystem
from core.task import Task
from core.token_auditor import TokenAuditor
from core.tracer import Tracer
from models.router import Router
from modules.squirrel.agent import SquirrelAgent
from tools.builtin.echo_tool import EchoTool
from tools.builtin.file_write_tool import FileWriteTool
from tools.builtin.syntax_check_tool import SyntaxCheckTool
from tools.registry import ToolRegistry


async def run_demo() -> None:
    """运行 P4 端到端 demo。"""
    print("=" * 60)
    print("BlueDeer P4 — Token 审计 + 游戏化奖惩 CLI Demo")
    print("=" * 60)

    # 清理旧数据
    for d in ["snapshot/stats", "output/p4"]:
        if os.path.exists(d):
            shutil.rmtree(d)

    # 1. 初始化组件
    print("\n[1] 初始化组件...")
    tracer = Tracer()
    bus = EventBus(tracer=tracer)
    router = Router()
    context = ContextManager()
    tools = ToolRegistry(max_retries=3)
    tools.register(EchoTool())
    tools.register(FileWriteTool())
    tools.register(SyntaxCheckTool())
    rag = None  # P4 demo 聚焦 Token+奖惩，不接 RAG

    token_auditor = TokenAuditor()
    reward_system = RewardSystem()

    harness = Harness(
        event_bus=bus,
        tracer=tracer,
        token_auditor=token_auditor,
        reward_system=reward_system,
    )
    squirrel = SquirrelAgent(
        event_bus=bus,
        router=router,
        tool_registry=tools,
        context=context,
        tracer=tracer,
        rag=rag,
    )

    context.set_global("project", "BlueDeer")
    context.set_global("phase", "P4")

    print(f"  TokenAuditor  ✓ (阈值: {token_auditor._threshold})")
    print("  RewardSystem  ✓ (32 项成就三梯次)")
    print("  Harness       ✓ (带审计+奖惩+P6 节省同步)")

    # 2. 下发多个任务
    print("\n[2] 下发 3 个任务（2 成功 + 1 失败）...")

    tasks = [
        Task(
            type="code",
            payload={
                "description": "创建一个 Python 加法函数 add(a, b)",
                "target_file": "output/p4/adder.py",
                "language": "python",
            },
            assignee="squirrel",
        ),
        Task(
            type="code",
            payload={
                "description": "创建一个 Python 乘法函数 multiply(a, b)",
                "target_file": "output/p4/multiplier.py",
                "language": "python",
            },
            assignee="squirrel",
        ),
        Task(
            type="code",
            payload={
                "description": "创建一个故意语法错误的函数",
                "target_file": "output/p4/broken.py",
                "language": "python",
            },
            assignee="squirrel",
        ),
    ]

    # 第 3 个任务注入语法错误来制造失败
    original_handle = squirrel.handle

    async def failing_handle(task: Task):
        """第 3 个任务故意失败。"""
        if task.payload["target_file"] == "output/p4/broken.py":
            # 手动写入语法错误代码
            from core.task import TaskResult, TaskStatus, TokenUsage
            from tools.builtin.file_write_tool import FileWriteTool

            fw = FileWriteTool()
            await fw.execute({"path": "output/p4/broken.py", "content": "def (\n"})
            return TaskResult(
                trace_id=task.trace_id,
                task_id=task.id,
                status=TaskStatus.FAILED,
                error="自检失败：语法校验未通过: SyntaxError",
                token_usage=TokenUsage(tokens_in=50, tokens_out=20),
            )
        return await original_handle(task)

    squirrel.handle = failing_handle

    results = []
    for i, task in enumerate(tasks):
        print(f"\n  任务 {i+1}: {task.payload['description']}")
        result = await harness.submit_and_wait(task, timeout=30.0)
        results.append(result)
        print(f"    Status: {result.status.value}")

        # 打印奖惩变化
        profile = reward_system.get_profile("squirrel")
        print(
            f"    金币={profile.coins}  经验={profile.exp}  好感={profile.favor}  连胜={profile.streak}"
        )

        # 成就解锁
        achievements = reward_system.get_achievements_detail("squirrel")
        if achievements and i == 0:
            print(f"    成就解锁: {[a['name'] for a in achievements]}")

    # 3. 梦境记忆计入奖惩
    print("\n[3] 梦境固化记忆计入奖惩...")
    # P6: 模拟高质量梦境记忆（含质量分级）
    reward_system.add_dream_memory("squirrel", count=5, high_quality_count=3)
    profile = reward_system.get_profile("squirrel")
    dream_achievements = reward_system.get_achievements_detail("squirrel")
    new_ach = [a for a in dream_achievements if a["id"] in ("dream_1",)]
    if new_ach:
        print(f"    成就解锁: {new_ach[0]['name']} — {new_ach[0]['desc']}")
    print(
        f"    梦境记忆: {profile.dream_memories} 条 (高质量 {profile.dream_quality_high} 条)"
    )

    # 4. 排行榜（多维）
    print("\n[4] 排行榜（综合分 = level*1000 + coins）:")
    print("  " + "-" * 70)
    board = reward_system.leaderboard(sort_by="composite")
    for entry in board:
        print(
            f"  {entry['agent_id']:12s} | Lv.{entry['level']} | "
            f"金币={entry['coins']:4d} | 经验={entry['exp']:4d} | "
            f"好感={entry['favor']:3d} | 成就={len(entry['achievements'])}项"
        )
    print("  " + "-" * 70)

    # 5. Token 统计
    print("\n[5] Token 统计:")
    stats = token_auditor.get_total_stats()
    print(f"  总调用: {stats['total_calls']}")
    print(f"  总输入 Token: {stats['tokens_in']}")
    print(f"  总输出 Token: {stats['tokens_out']}")
    print(f"  总 Token: {stats['tokens_total']}")

    # 6. 月度报表导出
    print("\n[6] 导出月度成本报表...")
    report_path = "snapshot/stats/monthly_report.md"
    token_auditor.save_report(report_path)
    print(f"  报表已保存: {report_path}")

    # 持久化
    token_auditor.save("snapshot/stats/token_audit.json")
    reward_system.save("snapshot/stats/rewards.json")
    print("  审计数据已保存: snapshot/stats/token_audit.json")
    print("  奖惩数据已保存: snapshot/stats/rewards.json")

    # 7. 看板汇总
    print("\n[7] 看板汇总:")
    board = harness.aggregate()
    print(
        f"  总任务: {board['total']}  成功: {board['success']}  失败: {board['failed']}"
    )
    # P6 新增字段
    savings = board.get("token_savings", {})
    print(
        f"  Token 节省: {savings.get('total_saved', 0)}  低成本调用: {savings.get('lowcost_calls', 0)}/{savings.get('total_calls', 0)}"
    )

    # 8. 成就总览 + 进度
    print("\n[8] 较真松鼠成就总览:")
    all_achievements = reward_system.get_achievements_detail("squirrel")
    for a in all_achievements:
        print(f"  [{a['tier']}] {a['name']}: {a['desc']}  ({a['dimension']})")

    progress = reward_system.achievement_progress("squirrel")
    print(f"\n  成就进度: {progress['unlocked']}/{progress['total']}")
    for tier, info in progress["by_tier"].items():
        print(f"    {tier}: {info['unlocked']}/{info['total']}")

    # 9. P6 新增：Token 节省指标
    print("\n[9] P6 Token 节省指标:")
    agent_savings = token_auditor.get_savings("squirrel")
    agent_ratio = token_auditor.get_lowcost_ratio("squirrel")
    print(f"  squirrel 节省 Token: {agent_savings['total_saved']}")
    print(f"  squirrel 低成本占比: {agent_ratio}%")

    print("\n" + "=" * 60)
    if board["success"] >= 1 and stats["total_calls"] >= 1:
        print("✓ P4 端到端链路验证通过！（P6 优化版数值体系）")
        print("  Token 审计 → 奖惩结算 → 成就解锁 → 排行榜 → 月度报表")
        print("  30 项成就三梯次 | 指数等级 | 递减好感 | Token 节省指标")
    else:
        print("✗ P4 端到端链路验证失败！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_demo())
