"""BlueDeer P3 CLI demo：梦境记忆 + RAG 向量库端到端链路。

编排完整链路：
1. 初始化 RAGSystem，注入全局规范 + 岗位历史方案
2. SquirrelAgent 带 RAG 检索的代码生成链路
3. 任务成功后方案自动写入岗位 RAG 库
4. 触发梦境系统：浅睡→REM→深睡→噩梦
5. 打印梦境报告 + RAG 检索验证

运行方式：
    python -m cli.demo_p3
"""

from __future__ import annotations

import asyncio
import os
import shutil

from core.context import ContextManager
from core.dream import DreamSystem
from core.event_bus import EventBus
from core.harness import Harness
from core.rag import SCOPE_AGENT, SCOPE_GLOBAL, RAGSystem
from core.task import Task, TaskStatus
from core.tracer import Tracer
from models.router import Router
from modules.squirrel.agent import SquirrelAgent
from tools.builtin.echo_tool import EchoTool
from tools.builtin.file_write_tool import FileWriteTool
from tools.builtin.syntax_check_tool import SyntaxCheckTool
from tools.registry import ToolRegistry


async def run_demo() -> None:
    """运行 P3 端到端 demo。"""
    print("=" * 60)
    print("BlueDeer P3 — 梦境记忆 + RAG 向量库 CLI Demo")
    print("=" * 60)

    # 清理旧数据
    if os.path.exists("vector_db/data"):
        shutil.rmtree("vector_db/data")

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
    rag = RAGSystem()
    dream = DreamSystem()

    # 注入全局规范
    rag.ingest(
        scope=SCOPE_GLOBAL,
        id="coding_standard",
        text="BlueDeer 项目编码规范：遵循 PEP 8，函数需包含 docstring，变量名使用 snake_case",
        metadata={"type": "standard"},
    )
    rag.ingest(
        scope=SCOPE_GLOBAL,
        id="project_arch",
        text="BlueDeer 多智能体架构：事件总线调度，11 角色，梦境记忆系统，RAG 向量库",
        metadata={"type": "architecture"},
    )

    # 注入岗位历史方案
    rag.ingest(
        scope=SCOPE_AGENT,
        id="historical_adder",
        text="def add(a, b):\n    return a + b\n",
        metadata={"task_type": "code", "description": "加法函数"},
        sub_id="squirrel",
    )

    harness = Harness(event_bus=bus, tracer=tracer)
    SquirrelAgent(
        event_bus=bus,
        router=router,
        tool_registry=tools,
        context=context,
        tracer=tracer,
        rag=rag,
    )

    context.set_global("project", "BlueDeer")
    context.set_global("phase", "P3")

    print(
        f"  RAG        ✓ (全局库: {rag.get_store_size(SCOPE_GLOBAL)} 条, 松鼠库: {rag.get_store_size(SCOPE_AGENT, 'squirrel')} 条)"
    )
    print("  Dream      ✓ (梦境系统就绪)")
    print("  Squirrel   ✓ (带 RAG 检索的较真松鼠)")

    # 2. 下发任务
    print("\n[2] 下发代码生成任务（带 RAG 检索）...")
    task = Task(
        type="code",
        payload={
            "description": "创建一个 Python 加法函数 add(a, b)，返回两数之和",
            "target_file": "output/p3_adder.py",
            "language": "python",
        },
        assignee="squirrel",
    )
    print(f"  Task ID:  {task.id}")
    print(f"  描述:     {task.payload['description']}")

    # 3. 等待结果
    print("\n[3] 等待较真松鼠处理（RAG 检索 + 代码生成 + 写入 + 校验）...")
    result = await harness.submit_and_wait(task, timeout=30.0)

    print("\n[4] 任务结果:")
    print(f"  Status:     {result.status.value}")
    if result.output:
        print(f"  模型:       {result.output.get('model_used', 'N/A')}")
        print(
            f"  语法校验:   {'通过' if result.output.get('syntax_check', {}).get('valid') else '失败'}"
        )
        print(f"  写入字节:   {result.output.get('write_result', {}).get('bytes', 0)}")

    # 4. RAG 验证
    print("\n[5] RAG 验证:")
    agent_size = rag.get_store_size(SCOPE_AGENT, "squirrel")
    print(f"  松鼠岗位库文档数: {agent_size}（含历史 1 + 新增 1）")

    search_results = rag.retrieve("加法函数 add", SCOPE_AGENT, "squirrel", top_k=3)
    print("  检索 '加法函数 add' 结果:")
    for r in search_results:
        print(f"    - id={r.id}, score={r.score:.4f}, text={r.text[:50]}...")

    # 5. 梦境系统
    print("\n[6] 触发梦境系统...")
    all_results = list(harness._task_board.values())
    report, memories = dream.dream(
        results=all_results,
        agent_id_map={task.id: "squirrel"},
    )

    # 深睡固化：将梦境记忆写入 RAG
    for memory in memories:
        rag.ingest(
            scope=SCOPE_AGENT,
            id=f"dream_{memory.source_task_id}",
            text=memory.content,
            metadata={
                "source": "dream",
                "optimized": memory.metadata.get("optimized", False),
                "task_type": memory.task_type,
            },
            sub_id=memory.agent_id,
        )

    print("\n[7] 梦境报告:")
    print("  " + "-" * 50)
    for line in report.summary().split("\n"):
        print(f"  | {line}")
    print("  " + "-" * 50)

    # 6. 最终汇总
    print("\n[8] 最终汇总:")
    print(
        f"  松鼠岗位库文档数: {rag.get_store_size(SCOPE_AGENT, 'squirrel')}（含梦境固化）"
    )
    board = harness.aggregate()
    print(
        f"  任务看板: 总{board['total']} 成功{board['success']} 失败{board['failed']}"
    )

    print("\n" + "=" * 60)
    if result.status == TaskStatus.SUCCESS and report.memories_persisted > 0:
        print("✓ P3 端到端链路验证通过！")
        print(
            "  RAG 注入 → SquirrelAgent 检索历史 → 代码生成 → 写入 → 校验 → 方案回写 RAG"
        )
        print("  梦境系统: 浅睡分拣 → REM 推演 → 深睡固化 → 噩梦告警")
    else:
        print("✗ P3 端到端链路验证失败！")
    print("=" * 60)
    print("\n完整 trace 已写入 logs/trace.log")
    print("RAG 向量库已持久化至 vector_db/data/")


if __name__ == "__main__":
    asyncio.run(run_demo())
