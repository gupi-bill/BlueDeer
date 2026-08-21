"""BlueDeer 报表/导出系统：将 task board + trace 导出为 Markdown / HTML。"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger("bluedeer.reporter")


_TEMPLATES: dict[str, str] = {}


class ReportGenerator:
    """报表生成器。"""

    FORMATS = ("markdown", "html", "json", "csv")

    def __init__(self, output_dir: str = "reports") -> None:
        self._output_dir = output_dir

    # ---- 公开入口 ----

    def generate(
        self,
        task_board: dict[str, dict[str, Any]],
        aggregate_stats: dict[str, Any] | None = None,
        trace_lines: list[str] | None = None,
        fmt: str = "markdown",
        title: str = "BlueDeer 任务报告",
    ) -> str:
        """生成报告并写入文件。

        Returns:
            输出文件路径。
        """
        if fmt not in self.FORMATS:
            raise ValueError(f"不支持的格式: {fmt}，可选: {self.FORMATS}")

        os.makedirs(self._output_dir, exist_ok=True)
        ext = "md" if fmt == "markdown" else "html"
        path = os.path.join(self._output_dir, f"report.{ext}")

        body = self._render_markdown(task_board, aggregate_stats, trace_lines, title)
        if fmt == "html":
            body = self._markdown_to_html(body)

        with open(path, "w", encoding="utf-8") as f:
            f.write(body)

        logger.info("报告已生成: %s (%s, %d 字符)", path, fmt, len(body))
        return path

    def render_text(
        self,
        task_board: dict[str, dict[str, Any]],
        aggregate_stats: dict[str, Any] | None = None,
        trace_lines: list[str] | None = None,
        title: str = "BlueDeer 任务报告",
    ) -> str:
        """返回 Markdown 文本（不写文件）。"""
        return self._render_markdown(task_board, aggregate_stats, trace_lines, title)

    # ---- 导出 ----

    def export(
        self,
        task_board: dict[str, dict[str, Any]],
        aggregate_stats: dict[str, Any] | None = None,
        trace_lines: list[str] | None = None,
        fmt: str = "json",
        title: str = "BlueDeer 任务报告",
    ) -> str:
        """导出报告为指定格式并返回内容字符串。"""
        if fmt == "json":
            return json.dumps(
                {
                    "title": title,
                    "generated_at": _now(),
                    "stats": aggregate_stats or {},
                    "tasks": task_board,
                    "trace": trace_lines or [],
                },
                ensure_ascii=False,
                indent=2,
            )
        elif fmt == "csv":
            lines = ["TaskID,Status,Tokens,Error"]
            for tid, r in task_board.items():
                status = r.get("status", "?")
                tokens = r.get("tokens", "—")
                error = (r.get("error") or "")[:60]
                lines.append(f"{tid[:16]},{status},{tokens},{error}")
            return "\n".join(lines)
        elif fmt == "html":
            return self._markdown_to_html(
                self._render_markdown(task_board, aggregate_stats, trace_lines, title)
            )
        return self._render_markdown(task_board, aggregate_stats, trace_lines, title)

    def add_template(self, name: str, content: str) -> None:
        """添加自定义报表模板。"""
        _TEMPLATES[name] = content

    def generate_summary(self, task_board: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """生成聚合统计摘要。"""
        total = len(task_board)
        success = sum(1 for r in task_board.values() if r.get("status") == "success")
        failed = sum(1 for r in task_board.values() if r.get("status") == "failed")
        pending = sum(1 for r in task_board.values() if r.get("status") == "pending")
        total_tokens = sum(r.get("tokens", 0) or 0 for r in task_board.values())
        return {
            "total": total,
            "success": success,
            "failed": failed,
            "pending": pending,
            "total_tokens": total_tokens,
            "success_rate": round(success / total * 100, 1) if total else 0.0,
        }

    # ---- Markdown 渲染 ----

    def _render_markdown(
        self,
        task_board: dict[str, dict[str, Any]],
        aggregate_stats: dict[str, Any] | None,
        trace_lines: list[str] | None,
        title: str,
    ) -> str:
        lines: list[str] = [
            f"# {title}",
            "",
            f"_生成时间: {_now()}_",
            "",
        ]

        if aggregate_stats:
            lines.append("## 汇总统计")
            lines.append("")
            lines.append("| 指标 | 数值 |")
            lines.append("|------|------|")
            for key in ("total", "success", "failed", "pending", "total_tokens"):
                val = aggregate_stats.get(key, "—")
                label = {
                    "total": "任务总数",
                    "success": "成功",
                    "failed": "失败",
                    "pending": "待处理",
                    "total_tokens": "Token 消耗",
                }.get(key, key)
                lines.append(f"| {label} | {val} |")
            if aggregate_stats.get("in_flight"):
                lines.append("")
                lines.append("### 在途任务（按 Agent）")
                lines.append("")
                for agent, count in aggregate_stats["in_flight"].items():
                    lines.append(f"- **{agent}**: {count}")
            if aggregate_stats.get("rewards"):
                lines.append("")
                lines.append("### 排行榜")
                lines.append("")
                lines.append("| Agent | 等级 | 金币 | 经验 |")
                lines.append("|-------|------|------|------|")
                for entry in aggregate_stats["rewards"]:
                    lines.append(
                        f"| {entry.get('agent_id', '?')} | {entry.get('level', '?')} "
                        f"| {entry.get('coins', '?')} | {entry.get('exp', '?')} |"
                    )
            lines.append("")

        if task_board:
            lines.append("## 任务明细")
            lines.append("")
            lines.append("| 任务 ID | 状态 | Token | 错误 |")
            lines.append("|---------|------|-------|------|")
            for tid, r in task_board.items():
                status = r.get("status", "?")
                tokens = r.get("tokens", "—")
                error = (r.get("error") or "")[:60] if r.get("error") else ""
                lines.append(f"| {tid[:16]} | {status} | {tokens} | {error} |")
            lines.append("")

        if trace_lines:
            lines.append("## Trace 日志")
            lines.append("")
            lines.append("```")
            for line in trace_lines[-50:]:
                lines.append(line.rstrip())
            lines.append("```")
            lines.append("")

        return "\n".join(lines)

    # ---- HTML 渲染 ----

    def _markdown_to_html(self, md_body: str) -> str:
        lines = md_body.split("\n")
        html_parts: list[str] = [
            "<!DOCTYPE html>",
            '<html lang="zh-CN">',
            "<head><meta charset='utf-8'>",
            "<title>BlueDeer 报告</title>",
            "<style>",
            "  body { font-family: -apple-system, 'Segoe UI', sans-serif; max-width: 960px; margin: 2em auto; padding: 0 1em; color: #1a1a2e; background: #f8f9fa; }",
            "  h1 { color: #0f3460; border-bottom: 2px solid #e94560; padding-bottom: .3em; }",
            "  h2 { color: #16213e; margin-top: 1.5em; }",
            "  h3 { color: #0f3460; }",
            "  table { border-collapse: collapse; width: 100%; margin: 1em 0; }",
            "  th, td { border: 1px solid #dde; padding: .5em .8em; text-align: left; }",
            "  th { background: #0f3460; color: #fff; }",
            "  tr:nth-child(even) { background: #f0f1f5; }",
            "  pre { background: #1a1a2e; color: #e8e8e8; padding: 1em; border-radius: 6px; overflow-x: auto; }",
            "  code { font-family: 'Fira Code', monospace; font-size: .9em; }",
            "  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px,1fr)); gap: 1em; margin: 1em 0; }",
            "  .stat-card { background: #fff; border-radius: 8px; padding: 1em; box-shadow: 0 1px 3px rgba(0,0,0,.1); text-align: center; }",
            "  .stat-card .num { font-size: 2em; font-weight: 700; color: #e94560; }",
            "  .stat-card .label { font-size: .85em; color: #555; }",
            "</style></head><body>",
        ]

        in_table = False
        in_code = False
        for line in lines:
            if line.startswith("```"):
                if in_code:
                    html_parts.append("</pre>")
                    in_code = False
                else:
                    html_parts.append("<pre>")
                    in_code = True
                continue
            if in_code:
                html_parts.append(line.replace("<", "&lt;").replace(">", "&gt;"))
                continue

            if line.startswith("# "):
                html_parts.append(f"<h1>{line[2:]}</h1>")
            elif line.startswith("## "):
                html_parts.append(f"<h2>{line[3:]}</h2>")
            elif line.startswith("### "):
                html_parts.append(f"<h3>{line[4:]}</h3>")
            elif line.startswith("|") and line.endswith("|"):
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if line.startswith("|---"):
                    continue
                if not in_table:
                    html_parts.append("<table>")
                    in_table = True
                tag = (
                    "th"
                    if in_table and _is_header_row(lines, lines.index(line))
                    else "td"
                )
                html_parts.append(
                    f"<tr>{''.join(f'<{tag}>{c}</{tag}>' for c in cells)}</tr>"
                )
            else:
                if in_table:
                    html_parts.append("</table>")
                    in_table = False
                if line.startswith("- **"):
                    html_parts.append(f"<li>{line[2:]}</li>")
                elif line.startswith("_"):
                    html_parts.append(f"<p><em>{line.strip('_')}</em></p>")
                elif line.strip():
                    html_parts.append(f"<p>{line}</p>")

        if in_table:
            html_parts.append("</table>")
        html_parts.append("</body></html>")
        return "\n".join(html_parts)


def _now() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _is_header_row(lines: list[str], idx: int) -> bool:
    """判断表格行是否为表头（表头后一行是分隔行）。"""
    for i in range(idx + 1, min(idx + 5, len(lines))):
        l = lines[i].strip()
        if l.startswith("|---"):
            return True
        if l.startswith("|") and not l.startswith("|---"):
            return False
    return False
