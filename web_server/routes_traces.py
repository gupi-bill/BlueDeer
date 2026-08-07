# 自动拆分自 web_server.py（路由域: traces）
from fastapi import APIRouter
from web_server.app import (
    debugger, canvas,
)

router = APIRouter()


@router.get("/api/traces")
async def list_traces() -> dict[str, Any]:
    """列出所有 trace 摘要。"""
    summaries = debugger.summary()
    return {
        "traces": [
            {
                "trace_id": s.trace_id,
                "span_count": s.span_count,
                "total_duration_ms": s.total_duration_ms,
                "component_count": len(s.agent_spans),
                "error_count": len(s.errors),
                "token_usage": s.token_usage,
            }
            for s in summaries
        ],
        "total": len(summaries),
    }


@router.get("/api/traces/{trace_id}")
async def get_trace(trace_id: str) -> dict[str, Any]:
    """获取指定 trace 的 Chrome Trace Event Format 数据。"""
    # 从 debugger 导出为事件列表
    spans = debugger._spans.get(trace_id, [])
    events = []
    pid = 1
    for span in spans:
        ts_us = int(span.timestamp * 1_000_000)
        dur_us = int(span.duration_ms * 1_000) if span.duration_ms > 0 else 0
        args = dict(span.fields)
        if span.error:
            args["error"] = span.error
        events.append(
            {
                "ph": "X" if dur_us > 0 else "i",
                "name": f"{span.component}.{span.action}",
                "cat": span.component,
                "ts": ts_us,
                "dur": max(0, dur_us),
                "pid": pid,
                "tid": hash(span.component) % 1000,
                "args": args,
            }
        )
    return {"trace_id": trace_id, "events": events, "count": len(events)}


@router.get("/api/traces/{trace_id}/summary")
async def get_trace_summary(trace_id: str) -> dict[str, Any]:
    """获取指定 trace 的摘要。"""
    summaries = debugger.summary(trace_id)
    if not summaries:
        return {"summary": None}
    s = summaries[0]
    return {
        "summary": {
            "trace_id": s.trace_id,
            "total_duration_ms": s.total_duration_ms,
            "span_count": s.span_count,
            "agent_spans": {
                comp: [
                    {
                        "action": sp.action,
                        "duration_ms": sp.duration_ms,
                        "error": sp.error,
                    }
                    for sp in spans
                ]
                for comp, spans in s.agent_spans.items()
            },
            "errors": [
                {
                    "component": e.component,
                    "action": e.action,
                    "error": e.error,
                }
                for e in s.errors
            ],
            "token_usage": s.token_usage,
        }
    }


@router.get("/api/canvas/{trace_id}")
async def get_canvas(trace_id: str) -> dict[str, Any]:
    """获取指定 trace 的 Mermaid 流程图。"""
    code = canvas.render(trace_id)
    return {"trace_id": trace_id, "mermaid": code}


@router.get("/api/canvas/flow")
async def get_canvas_flow() -> dict[str, Any]:
    """获取简化流程图。"""
    code = canvas.render_flow()
    return {"mermaid": code}
