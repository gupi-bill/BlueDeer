"""BlueDeer 调试模式：结构化 trace 聚合、耗时分析、火焰图导出。

基于 Tracer 已有的 JSON span 日志，增加：
- 耗时计算（start/end 配对）
- Chrome Trace Event Format 导出（兼容 chrome://tracing 和 Perfetto）
- 调试摘要报告

用法：
    debugger = Debugger(tracer=tracer)
    debugger.attach()
    # ... run tasks ...
    report = debugger.summary()
    debugger.export_chrome_trace("logs/flame.json")
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("bluedeer.debugger")


@dataclass
class SpanEvent:
    """单次 span 事件（与 Tracer.span 对应，增加时间字段）。"""

    trace_id: str
    component: str
    action: str
    timestamp: float = 0.0
    duration_ms: float = 0.0
    fields: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class TraceSummary:
    """单条 trace 的摘要。"""

    trace_id: str
    total_duration_ms: float = 0.0
    span_count: int = 0
    agent_spans: dict[str, list[SpanEvent]] = field(default_factory=dict)
    errors: list[SpanEvent] = field(default_factory=list)
    token_usage: dict[str, int] = field(default_factory=lambda: {"in": 0, "out": 0})


class Debugger:
    """调试器：聚合 trace span 数据，提供诊断报告。"""

    def __init__(
        self,
        tracer: Any = None,
        trace_dir: str = "logs",
        enabled: bool = False,
    ) -> None:
        self._tracer = tracer
        self._trace_dir = trace_dir
        self._enabled = enabled
        self._spans: dict[str, list[SpanEvent]] = defaultdict(list)
        self._active_spans: dict[str, float] = {}
        self._breakpoints: list[str] = []
        self._step_mode: str = ""
        self._watched_vars: dict[str, Any] = {}
        self._execution_state: str = "running"

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True
        logger.info("Debugger 已启用")

    def disable(self) -> None:
        self._enabled = False

    def attach(self) -> None:
        """附加到全局 Tracer（拦截 span 调用）。"""
        if not self._tracer:
            logger.warning("Debugger 无 tracer 可附加")
            return
        self._enabled = True
        logger.info("Debugger 已附加到 Tracer")

    def record_span(
        self,
        trace_id: str,
        component: str,
        action: str,
        **fields: Any,
    ) -> None:
        """记录一个 span（由 Tracer 或 Agent 调用）。"""
        if not self._enabled:
            return
        now = time.time()
        span = SpanEvent(
            trace_id=trace_id,
            component=component,
            action=action,
            timestamp=now,
            fields=fields,
        )
        # 计算 duration：匹配 start/end 成对的 action
        span_key = f"{trace_id}:{component}:{action}"
        if action.endswith("_start") or action == "handle_start":
            self._active_spans[span_key] = now
        elif (
            action.endswith("_success")
            or action.endswith("_failed")
            or action == "handle_success"
        ):
            start = self._active_spans.pop(span_key, None)
            if start is not None:
                span.duration_ms = (now - start) * 1000

        self._spans[trace_id].append(span)
        self._check_error(action, fields, span)

    def _check_error(
        self, action: str, fields: dict[str, Any], span: SpanEvent
    ) -> None:
        error = fields.get("error")
        if error or "failed" in action.lower():
            span.error = str(error) if error else action

    def summary(self, trace_id: str | None = None) -> list[TraceSummary]:
        """生成 trace 摘要（可按 trace_id 筛选）。"""
        summaries: list[TraceSummary] = []
        target_traces = [trace_id] if trace_id else list(self._spans.keys())

        for tid in target_traces:
            spans = self._spans.get(tid, [])
            if not spans:
                continue
            s = TraceSummary(trace_id=tid, span_count=len(spans))
            for span in spans:
                s.agent_spans.setdefault(span.component, []).append(span)
                if span.error:
                    s.errors.append(span)
                s.total_duration_ms = max(
                    s.total_duration_ms, span.timestamp + span.duration_ms / 1000
                )
                tokens_in = span.fields.get("tokens_in", 0)
                tokens_out = span.fields.get("tokens_out", 0)
                if isinstance(tokens_in, int):
                    s.token_usage["in"] += tokens_in
                if isinstance(tokens_out, int):
                    s.token_usage["out"] += tokens_out
            summaries.append(s)

        return summaries

    def export_chrome_trace(self, output_path: str = "logs/flame_trace.json") -> str:
        """导出 Chrome Trace Event Format（兼容 chrome://tracing 和 Perfetto）。

        返回写入的文件路径。
        """
        events: list[dict[str, Any]] = []
        pid = 1
        for trace_id, spans in self._spans.items():
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

        chrome_trace = {
            "displayTimeUnit": "ms",
            "traceEvents": events,
        }

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(chrome_trace, f, ensure_ascii=False, default=str)

        logger.info("Chrome trace 已导出: %s（%d 事件）", output_path, len(events))
        return output_path

    def set_breakpoint(self, condition: str = "") -> None:
        """设置断点条件。空字符串表示无条件断点。"""
        self._breakpoints.append(condition)
        logger.info("断点已设置: %s", condition or "无条件")

    def step_over(self) -> None:
        """单步跳过（不进入子调用）。"""
        self._step_mode = "over"
        self._execution_state = "paused"
        logger.info("步进模式: over")

    def step_into(self) -> None:
        """单步进入（进入子调用）。"""
        self._step_mode = "into"
        self._execution_state = "paused"
        logger.info("步进模式: into")

    def continue_execution(self) -> None:
        """继续执行直到下一个断点。"""
        self._step_mode = ""
        self._execution_state = "running"
        logger.info("继续执行")

    def watch_variable(self, name: str) -> Any:
        """获取被监视变量的当前值。"""
        return self._watched_vars.get(name)

    def print_summary(self, trace_id: str | None = None) -> None:
        """打印调试摘要到控制台。"""
        summaries = self.summary(trace_id)
        if not summaries:
            logger.info("[Debugger] 无 trace 数据")
            return

        for s in summaries:
            logger.info("\n%s", "=" * 60)
            logger.info("Trace: %s", s.trace_id)
            logger.info("Spans: %d | Tokens: %s", s.span_count, s.token_usage)
            if s.errors:
                logger.info("Errors: %d", len(s.errors))
                for e in s.errors:
                    logger.info("  ✗ %s.%s: %s", e.component, e.action, e.error)
            for comp, spans in sorted(s.agent_spans.items()):
                total_ms = sum(sp.duration_ms for sp in spans if sp.duration_ms > 0)
                logger.info("  %s: %d spans, %.1fms", comp, len(spans), total_ms)
            logger.info("%s", "=" * 60)
