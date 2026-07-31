"""BlueDeer Canvas：从 Debugger trace 生成 Mermaid 流程图。

用法：
    from core.debugger import Debugger
    from core.canvas import Canvas
    canvas = Canvas(debugger)
    mermaid_code = canvas.render()
    canvas.save("docs/flow.md")
"""

from __future__ import annotations

import os
from typing import Any

from core.debugger import Debugger, SpanEvent


class Canvas:
    """将 Debugger 的 trace 数据渲染为 Mermaid 流程图。"""

    # Mermaid 主题色（森林风）
    _STYLES = """
    classDef agent fill:#1b5e20,stroke:#4caf50,color:#e8f5e9
    classDef tool fill:#0d47a1,stroke:#42a5f5,color:#e3f2fd
    classDef model fill:#e65100,stroke:#ff9800,color:#fff3e0
    classDef event fill:#4a148c,stroke:#ab47bc,color:#f3e5f5
    classDef error fill:#b71c1c,stroke:#ef5350,color:#ffebee
    """

    def __init__(self, debugger: Debugger) -> None:
        self._debugger = debugger
        self._undo_stack: list[dict[str, Any]] = []
        self._redo_stack: list[dict[str, Any]] = []
        self._layers: dict[str, list[dict[str, Any]]] = {}

    # ---- 撤销/重做 ----

    def _push_command(self, command: dict[str, Any]) -> None:
        self._undo_stack.append(command)
        self._redo_stack.clear()

    def undo(self) -> bool:
        """撤销上一次操作。"""
        if not self._undo_stack:
            return False
        cmd = self._undo_stack.pop()
        self._redo_stack.append(cmd)
        return True

    def redo(self) -> bool:
        """重做上一次撤销。"""
        if not self._redo_stack:
            return False
        cmd = self._redo_stack.pop()
        self._undo_stack.append(cmd)
        return True

    # ---- 图层 ----

    def add_layer(self, name: str) -> None:
        """添加图层。"""
        if name not in self._layers:
            self._layers[name] = []
            self._push_command({"type": "add_layer", "name": name})

    def remove_layer(self, name: str) -> bool:
        """删除图层。"""
        if name not in self._layers:
            return False
        data = self._layers.pop(name)
        self._push_command({"type": "remove_layer", "name": name, "data": data})
        return True

    def merge_layers(self, target: str, source: str) -> bool:
        """合并 source 到 target 图层。"""
        if target not in self._layers or source not in self._layers:
            return False
        self._layers[target].extend(self._layers[source])
        del self._layers[source]
        self._push_command({"type": "merge_layers", "target": target, "source": source})
        return True

    def render(self, trace_id: str | None = None) -> str:
        """生成 Mermaid flowchart 代码。

        Args:
            trace_id: 指定 trace，为空则合并所有 trace。

        Returns:
            Mermaid 格式的流程图代码。
        """
        lines: list[str] = [
            "```mermaid",
            "flowchart TD",
            self._STYLES.strip(),
        ]

        summaries = self._debugger.summary(trace_id)
        if not summaries:
            lines.append("    start([暂无 trace 数据])")
            lines.append("```")
            return "\n".join(lines)

        node_ids: set[str] = set()
        edges: list[str] = []
        errors: list[str] = []
        # 页码
        page_idx = 1

        for s in summaries:
            # trace 入口节点
            trace_node = f"trace_{s.trace_id[:8]}"
            lines.append(f"    {trace_node}([\"Trace {s.trace_id[:8]}\"]):::event")
            node_ids.add(trace_node)

            prev_node = trace_node
            comp_order = sorted(s.agent_spans.keys())

            for comp in comp_order:
                comp_node = f"comp_{s.trace_id[:8]}_{comp.replace(':', '_')}"
                safe_label = comp.replace(":", "<br>")
                lines.append(f"    {comp_node}[\"{safe_label}\"]:::agent")
                node_ids.add(comp_node)
                edges.append(f"    {prev_node} --> {comp_node}")
                edges.append(f"    {prev_node} -- \"→\" --> {comp_node}")

                spans = s.agent_spans[comp]
                inner_prev = comp_node

                for span in spans:
                    span_id = f"span_{s.trace_id[:8]}_{page_idx}"
                    page_idx += 1
                    label = self._span_label(span)
                    if span.error:
                        lines.append(f"    {span_id}{{\"{label}\"}}:::error")
                        errors.append(span_id)
                    elif "model" in span.action or "complete" in span.action:
                        lines.append(f"    {span_id}[{label}]:::model")
                    elif "tool" in span.action:
                        lines.append(f"    {span_id}[{label}]:::tool")
                    else:
                        lines.append(f"    {span_id}[{label}]")
                    node_ids.add(span_id)
                    edges.append(f"    {inner_prev} --> {span_id}")
                    inner_prev = span_id

                prev_node = comp_node

            # token 信息
            if s.token_usage["in"] > 0 or s.token_usage["out"] > 0:
                token_node = f"token_{s.trace_id[:8]}"
                lines.append(
                    f"    {token_node}(\"Token: in={s.token_usage['in']} "
                    f"out={s.token_usage['out']}\"):::model"
                )
                node_ids.add(token_node)
                edges.append(f"    {prev_node} -.-> {token_node}")

            # 错误汇总
            if s.errors:
                err_node = f"err_{s.trace_id[:8]}"
                err_count = len(s.errors)
                lines.append(f"    {err_node}{{\"✗ {err_count} errors\"}}:::error")
                node_ids.add(err_node)
                edges.append(f"    {prev_node} --> {err_node}")

        # 去重 edges
        seen_edges: set[str] = set()
        for e in edges:
            if e not in seen_edges:
                lines.append(e)
                seen_edges.add(e)

        lines.append("```")
        return "\n".join(lines)

    def render_flow(self) -> str:
        """生成简化的 Agent 交互流图（不含详细 span）。"""
        lines = [
            "```mermaid",
            "flowchart LR",
            self._STYLES.strip(),
        ]
        summaries = self._debugger.summary()
        if not summaries:
            lines.append("    start([暂无数据])")
            lines.append("```")
            return "\n".join(lines)

        all_components: set[str] = set()
        for s in summaries:
            all_components.update(s.agent_spans.keys())

        # 每个组件一个节点
        nodes: list[str] = []
        for comp in sorted(all_components):
            safe = comp.replace(":", "_").replace(".", "_")
            label = comp.replace(":", "<br>")
            style = "agent"
            if "EventBus" in comp:
                style = "event"
            elif "Router" in comp or "Model" in comp:
                style = "model"
            elif "Tool" in comp:
                style = "tool"
            nodes.append(f"    {safe}[{label}]:::{style}")

        # 按 trace 连接
        edges: list[str] = []
        for s in summaries[:5]:
            comps = list(s.agent_spans.keys())
            for i in range(len(comps) - 1):
                a = comps[i].replace(":", "_").replace(".", "_")
                b = comps[i + 1].replace(":", "_").replace(".", "_")
                edge = f"    {a} --> {b}"
                if edge not in edges:
                    edges.append(edge)

        lines.extend(nodes)
        lines.extend(edges)
        lines.append("```")
        return "\n".join(lines)

    def save(self, path: str, trace_id: str | None = None) -> str:
        """渲染并保存到 markdown 文件。

        Args:
            path: 输出路径。
            trace_id: 指定 trace。

        Returns:
            写入的 Mermaid 代码。
        """
        code = self.render(trace_id)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        return code

    def _span_label(self, span: SpanEvent) -> str:
        """将 SpanEvent 转为简短的节点标签。"""
        action = span.action.replace("_", " ")
        label = action[:25]
        if span.duration_ms > 0:
            label += f"<br>{span.duration_ms:.0f}ms"
        tokens_in = span.fields.get("tokens_in")
        tokens_out = span.fields.get("tokens_out")
        if tokens_in or tokens_out:
            label += f"<br>tok:{tokens_in or 0}/{tokens_out or 0}"
        return label
