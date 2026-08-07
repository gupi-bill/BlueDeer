# 自动拆分自 web_server.py（路由域: misc）
import logging
logger = logging.getLogger(__name__)
from fastapi import APIRouter

from web_server.app import (
    debugger,
)

router = APIRouter()


@router.post("/api/test_traces")
async def generate_test_traces() -> dict[str, Any]:
    """生成测试 trace 数据用于演示。"""
    import random

    trace_id = f"test_{int(time.time())}_{random.randint(1000, 9999)}"
    agents = [
        "Squirrel",
        "Fox",
        "Beaver",
        "Owl",
        "Hedgehog",
        "EventBus",
        "ToolRegistry",
    ]
    actions = [
        "handle_start",
        "handle_success",
        "tool_call",
        "tool_result",
        "model_query",
        "model_response",
        "rag_retrieve",
        "rag_result",
        "event_publish",
        "event_receive",
    ]

    # 生成 agent 级 span
    debugger.record_span(trace_id, "Workflow", "orchestrate_start")
    await asyncio.sleep(0.01)

    for agent in agents[: random.randint(3, 6)]:
        debugger.record_span(
            trace_id, agent, "handle_start", tokens_in=random.randint(50, 500)
        )
        await asyncio.sleep(random.uniform(0.005, 0.03))

        # sub-actions
        for _ in range(random.randint(1, 3)):
            action = random.choice(actions)
            debugger.record_span(
                trace_id,
                agent,
                action,
                tokens_in=random.randint(10, 200),
                tokens_out=random.randint(5, 100),
            )
            await asyncio.sleep(random.uniform(0.002, 0.015))

        # 随机错误
        if random.random() < 0.15:
            debugger.record_span(
                trace_id,
                agent,
                "handle_failed",
                error=f"模拟超时 ({random.randint(1, 5)}s)",
            )
        else:
            debugger.record_span(
                trace_id, agent, "handle_success", tokens_out=random.randint(20, 300)
            )

    debugger.record_span(trace_id, "Workflow", "orchestrate_success")
    await asyncio.sleep(0.01)

    return {
        "trace_id": trace_id,
        "message": f"已生成测试 trace: {trace_id[:12]}…",
    }


@router.get("/api/comm-log")
async def comm_log_query(
    trace_id: str = "",
    agent: str = "",
    action: str = "",
    max_chains: int = 50,
) -> dict[str, Any]:
    log = _get_comm_log()
    result = log.query(
        trace_id=trace_id or None,
        agent=agent or None,
        action=action or None,
        max_chains=max_chains,
    )
    return {
        "chains": [
            {
                "trace_id": c.trace_id,
                "agents": c.agents,
                "agent_count": c.agent_count,
                "entry_count": c.entry_count,
                "error_count": c.error_count,
                "start_ts": c.start_ts,
                "end_ts": c.end_ts,
                "duration_sec": c.duration_sec,
                "entries": [
                    {
                        "ts": e.ts,
                        "ts_str": e.ts_str,
                        "component": e.component,
                        "action": e.action,
                        "level": e.level,
                        "message": e.message,
                        "duration_ms": e.duration_ms,
                        "error": e.error,
                    }
                    for e in c.entries
                ],
            }
            for c in result.chains
        ],
        "total_chains": result.total_chains,
        "total_entries": result.total_entries,
        "agent_list": result.agent_list,
    }


@router.get("/api/comm-log/summary")
async def comm_log_summary() -> dict[str, Any]:
    from core.comm_log import CommLogViewer

    log = _get_comm_log()
    return CommLogViewer.summary(log)


# ── Plugin Repository ──

_plugin_repo = None


def _get_plugin_repo():
    global _plugin_repo
    if _plugin_repo is None:
        from core.plugin_repo import PluginRepo

        _plugin_repo = PluginRepo()
    return _plugin_repo
