"""BlueDeer 梦境报告：Markdown 导出。

P2-1 拆分自 core/dream.py。
"""

from __future__ import annotations

import time

from core.dream_models import DreamReport


def export_dream_report_md(report: DreamReport) -> str:
    """将梦境报告导出为 Markdown。

    Args:
        report: DreamReport 实例。

    Returns:
        Markdown 格式字符串。
    """
    lines = [
        "# BlueDeer 梦境报告",
        "",
        f"**生成时间**: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}",
        f"**阶段**: {report.phase}",
        f"**提取记忆**: {report.memories_extracted}",
        f"**优化记忆**: {report.memories_optimized}",
        f"**固化记忆**: {report.memories_persisted}",
        "",
        "## 质量分布",
        "",
        f"- 普通: {report.quality_counts.get('normal', 0)}",
        f"- 高质量: {report.quality_counts.get('high', 0)}",
        f"- 传奇: {report.quality_counts.get('legendary', 0)}",
        f"- 本轮节省 Token: {report.total_token_saved}",
        "",
        "## 噩梦告警",
        "",
    ]
    if report.nightmares:
        for nm in report.nightmares:
            lines.append(
                f"- 错误模式: `{nm.error_pattern}` (出现 {nm.occurrences} 次)"
            )
    else:
        lines.append("- 无")

    lines.extend(["", "## 固化记忆清单", ""])
    for m in report.optimized_memories:
        pin = "📌 " if m.is_pinned else ""
        lines.append(
            f"- {pin}[{m.quality.value}] {m.agent_id}/{m.source_task_id}: "
            f"{m.content[:80]}..."
        )

    return "\n".join(lines)
