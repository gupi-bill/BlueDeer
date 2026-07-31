"""BlueDeer P1 CLI demo：端到端链路验证。

编排完整链路：
忧郁鹿下发任务 → 基座 Agent 接收 → 模型路由 → 工具调用 → 结果回传 → 日志汇总

运行方式：
    python -m cli.demo
"""

from __future__ import annotations

import asyncio
import json

from core.base_agent import BaseAgent
from core.context import ContextManager
from core.event_bus import EventBus
from core.harness import Harness
from core.task import Task, TaskStatus
from core.tracer import Tracer
from models.router import Router
from tools.builtin.echo_tool import EchoTool
from tools.registry import ToolRegistry


async def run_demo() -> None:
    """运行 P1 端到端 demo。"""
    print("=" * 60)
    print("BlueDeer P1 — 调度核心地基 CLI Demo")
    print("=" * 60)

    # 1. 初始化组件
    print("\n[1] 初始化组件...")
    tracer = Tracer()
    bus = EventBus(tracer=tracer)
    router = Router()
    context = ContextManager()
    tools = ToolRegistry(max_retries=3)
    tools.register(EchoTool())

    # 设置全局上下文
    context.set_global("project", "BlueDeer")
    context.set_global("phase", "P1")

    harness = Harness(event_bus=bus, tracer=tracer)

    # 注册 demo-agent
    agent = BaseAgent(
        agent_id="demo-agent",
        role="demo",
        event_bus=bus,
        router=router,
        tool_registry=tools,
        context=context,
        tracer=tracer,
    )
    print(f"  EventBus   ✓")
    print(f"  Router     ✓ (默认模型: {router.default_model})")
    print(f"  Context    ✓ (全局: project=BlueDeer, phase=P1)")
    print(f"  Tools      ✓ (已注册: {tools.list_tools()})")
    print(f"  Harness    ✓ (忧郁鹿总经理)")
    print(f"  Agent      ✓ (demo-agent, topic={agent.topic})")

    # 2. 构造并下发任务
    print("\n[2] 下发任务...")
    task = Task(
        type="code",
        payload={
            "description": "回显测试",
            "tool": "echo",
            "tool_params": {"message": "Hello BlueDeer!"},
        },
        assignee="demo-agent",
    )
    print(f"  Task ID:    {task.id}")
    print(f"  Task Type:  {task.type}")
    print(f"  Assignee:   {task.assignee}")
    print(f"  Trace ID:   {task.trace_id}")

    # 3. 等待结果
    print("\n[3] 等待 Agent 处理...")
    result = await harness.submit_and_wait(task, timeout=10.0)

    # 4. 打印结果
    print("\n[4] 执行结果:")
    print(f"  Status:       {result.status.value}")
    print(f"  Token In:     {result.token_usage.tokens_in}")
    print(f"  Token Out:    {result.token_usage.tokens_out}")
    print(f"  Token Total:  {result.token_usage.total}")
    if result.error:
        print(f"  Error:        {result.error}")
    if result.output:
        print(f"  Model Output: {result.output.get('model_response', 'N/A')}")
        print(f"  Tool Output:  {json.dumps(result.output.get('tool_output'), ensure_ascii=False)}")

    # 5. 汇总看板
    print("\n[5] 任务看板汇总:")
    board = harness.aggregate()
    print(f"  总任务:   {board['total']}")
    print(f"  成功:     {board['success']}")
    print(f"  失败:     {board['failed']}")
    print(f"  待处理:   {board['pending']}")
    print(f"  总 Token: {board['total_tokens']}")

    # 6. 验证结论
    print("\n" + "=" * 60)
    if result.status == TaskStatus.SUCCESS:
        print("✓ P1 端到端链路验证通过！")
        print("  忧郁鹿下发 → Agent 接收 → 模型路由 → 工具调用 → 结果回传 → 日志汇总")
    else:
        print("✗ P1 端到端链路验证失败！")
        print(f"  错误: {result.error}")
    print("=" * 60)
    print("\n完整 trace 已写入 logs/trace.log")


def main() -> None:
    """同步入口（供 setup.py entry_points 使用）。"""
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()
