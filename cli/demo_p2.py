"""BlueDeer P2 CLI demo：较真松鼠端到端代码生成链路。

编排完整链路：
Harness 下发代码任务 → SquirrelAgent 接收 → LLM 生成代码 → 写入文件 → 语法校验 → 返回结果

运行方式：
    python -m cli.demo_p2

有 DOUBAO_API_KEY 时走真实 API，无 Key 时走 mock。
"""

from __future__ import annotations

import asyncio

from core.context import ContextManager
from core.event_bus import EventBus
from core.harness import Harness
from core.task import Task, TaskStatus
from core.tracer import Tracer
from models.router import Router
from modules.squirrel.agent import SquirrelAgent
from tools.builtin.echo_tool import EchoTool
from tools.builtin.file_write_tool import FileWriteTool
from tools.builtin.syntax_check_tool import SyntaxCheckTool
from tools.registry import ToolRegistry


async def run_demo() -> None:
    """运行 P2 端到端 demo。"""
    print("=" * 60)
    print("BlueDeer P2 — 较真松鼠代码生成 CLI Demo")
    print("=" * 60)

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

    # 设置上下文
    context.set_global("project", "BlueDeer")
    context.set_global("phase", "P2")
    context.set_agent("squirrel", "coding_standard", "PEP8")

    harness = Harness(event_bus=bus, tracer=tracer)
    squirrel = SquirrelAgent(
        event_bus=bus,
        router=router,
        tool_registry=tools,
        context=context,
        tracer=tracer,
    )

    mode = "真实 Doubao API" if router.use_real_api else "MockClient（无 API Key）"
    print(f"  Router     ✓ ({mode})")
    print(f"  Tools      ✓ (已注册: {tools.list_tools()})")
    print("  Harness    ✓ (忧郁鹿总经理)")
    print(f"  Squirrel   ✓ (较真松鼠, topic={squirrel.topic})")

    # 2. 构造并下发任务
    print("\n[2] 下发代码生成任务...")
    task = Task(
        type="code",
        payload={
            "description": "创建一个 Python 加法函数 add(a, b)，返回两数之和",
            "target_file": "output/adder.py",
            "language": "python",
        },
        assignee="squirrel",
    )
    print(f"  Task ID:    {task.id}")
    print(f"  Task Type:  {task.type}")
    print(f"  Assignee:   {task.assignee}")
    print(f"  Trace ID:   {task.trace_id}")
    print(f"  描述:       {task.payload['description']}")
    print(f"  目标文件:   {task.payload['target_file']}")

    # 3. 等待结果
    print("\n[3] 等待较真松鼠处理...")
    result = await harness.submit_and_wait(task, timeout=30.0)

    # 4. 打印结果
    print("\n[4] 执行结果:")
    print(f"  Status:       {result.status.value}")
    print(f"  Token In:     {result.token_usage.tokens_in}")
    print(f"  Token Out:    {result.token_usage.tokens_out}")
    print(f"  Token Total:  {result.token_usage.total}")

    if result.error:
        print(f"  Error:        {result.error}")

    if result.output:
        print(f"  模型:         {result.output.get('model_used', 'N/A')}")
        print(
            f"  写入路径:     {result.output.get('write_result', {}).get('path', 'N/A')}"
        )
        print(
            f"  写入字节:     {result.output.get('write_result', {}).get('bytes', 0)}"
        )
        check = result.output.get("syntax_check", {})
        print(f"  语法校验:     {'通过' if check.get('valid') else '失败'}")
        if check.get("error"):
            print(f"  校验错误:     {check.get('error')}")

        print("\n  生成的代码:")
        print("  " + "-" * 50)
        code = result.output.get("generated_code", "")
        for line in code.split("\n"):
            print(f"  | {line}")
        print("  " + "-" * 50)

    # 5. 汇总看板
    print("\n[5] 任务看板汇总:")
    board = harness.aggregate()
    print(f"  总任务:   {board['total']}")
    print(f"  成功:     {board['success']}")
    print(f"  失败:     {board['failed']}")
    print(f"  总 Token: {board['total_tokens']}")

    # 6. 验证结论
    print("\n" + "=" * 60)
    if result.status == TaskStatus.SUCCESS:
        print("✓ P2 端到端链路验证通过！")
        print(
            "  Harness 下发 → SquirrelAgent 接收 → LLM 生成代码 → 文件写入 → 语法校验 → 自检通过"
        )
    else:
        print("✗ P2 端到端链路验证失败！")
        print(f"  错误: {result.error}")
    print("=" * 60)
    print("\n完整 trace 已写入 logs/trace.log")


if __name__ == "__main__":
    asyncio.run(run_demo())
