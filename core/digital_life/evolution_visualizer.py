"""进化可视化 EvolutionVisualizer。

职责：
- 文本报告：render_text 返回 ASCII 文本摘要
- ASCII 折线图：用 ─│╭╮╰╯● 字符画平滑曲线
- Markdown 报告：render_markdown 返回 6 章节报告
- 状态摘要：status

零基础读者可以这样理解：
- 把 EvolutionTracker 拍的快照画成图给人看。
- 文本报告像"公司体检报告"。
- ASCII 折线图就是用键盘字符画的曲线图。
"""

from __future__ import annotations

import datetime
import threading


class EvolutionVisualizer:
    """进化可视化器。"""

    def __init__(self, tracker) -> None:
        self._tracker = tracker
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # 文本报告
    # ------------------------------------------------------------------

    def render_text(self) -> str:
        """渲染文本报告。"""
        with self._lock:
            st = self._tracker.status()
            snaps = list(self._tracker._snapshots)

        lines = [
            "=" * 60,
            "BlueDeer 进化追踪报告（文本）",
            f"生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 60,
            "",
            "【全局指标】",
            f"  当前世代：{st['generation']}",
            f"  快照数：{st['snapshot_count']}",
            f"  累计出生：{st['birth_count']}",
            f"  累计死亡：{st['death_count']}",
            "",
            "【按物种累计】",
        ]
        for sp, b in st["species_births"].items():
            d = st["species_deaths"].get(sp, 0)
            r = st["species_reproductions"].get(sp, 0)
            lines.append(f"  {sp}: 出生 {b}  死亡 {d}  繁殖 {r}")

        if snaps:
            last = snaps[-1]
            lines.extend(
                [
                    "",
                    "【最近快照】",
                    f"  时间戳：{datetime.datetime.fromtimestamp(last.timestamp).strftime('%Y-%m-%d %H:%M:%S')}",
                    f"  存活总数：{last.global_stats.get('total_alive', 0)}",
                    f"  Shannon 多样性：{last.global_stats.get('biodiversity', 0):.4f}",
                    f"  季节：{last.global_stats.get('season', '?')}",
                    "",
                    "【最近快照·各物种】",
                ]
            )
            for sp, s in last.species_stats.items():
                lines.append(
                    f"  {sp}: 数量 {s['count']}  "
                    f"平均能量 {s['avg_energy']:.1f}  "
                    f"平均健康 {s['avg_health']:.1f}  "
                    f"平均年龄 {s['avg_age_days']:.2f} 天"
                )

        # ASCII 折线图
        if len(snaps) >= 2:
            lines.extend(
                [
                    "",
                    "【种群总数趋势（最近 20 张快照）】",
                ]
            )
            trend = [s.global_stats.get("total_alive", 0) for s in snaps[-20:]]
            lines.extend(self._ascii_line_chart(trend, "total"))

        lines.extend(["", "=" * 60])
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # ASCII 折线图
    # ------------------------------------------------------------------

    def _ascii_line_chart(
        self, values: list, label: str = "", width: int = 50, height: int = 10
    ) -> list:
        """把 values 画成 ASCII 折线图，返回字符串列表。

        用 ─│╭╮╰╯● 字符画平滑曲线。
        """
        if not values:
            return [f"  ({label}: 无数据)"]

        n = len(values)
        v_min = min(values)
        v_max = max(values)
        if v_max == v_min:
            v_max = v_min + 1

        # 网格：height 行 × width 列
        grid = [[" "] * width for _ in range(height)]

        # 把每个 value 映射到 grid 坐标
        points = []
        for i, v in enumerate(values):
            x = int(i * (width - 1) / max(1, n - 1))
            y = int((v_max - v) / (v_max - v_min) * (height - 1))
            y = max(0, min(height - 1, y))
            points.append((x, y))

        # 画线
        for i in range(1, len(points)):
            x0, y0 = points[i - 1]
            x1, y1 = points[i]
            if x0 == x1:
                # 垂直
                for y in range(min(y0, y1), max(y0, y1) + 1):
                    grid[y][x0] = "│"
            elif y0 == y1:
                # 水平
                for x in range(x0, x1 + 1):
                    grid[y0][x] = "─"
            elif y1 > y0:
                # 下降
                grid[y0][x0] = "╭"
                grid[y1][x1] = "╯"
                for x in range(x0 + 1, x1):
                    grid[y0][x] = "─"
                for y in range(y0 + 1, y1):
                    grid[y][x1] = "│"
            else:
                # 上升
                grid[y0][x0] = "╰"
                grid[y1][x1] = "╮"
                for x in range(x0 + 1, x1):
                    grid[y0][x] = "─"
                for y in range(y1 + 1, y0):
                    grid[y][x1] = "│"

        # 画点
        for x, y in points:
            grid[y][x] = "●"

        # 输出
        lines = [f"  {label} (min={v_min}, max={v_max})"]
        for row in grid:
            lines.append("  " + "".join(row))
        return lines

    # ------------------------------------------------------------------
    # Markdown 报告
    # ------------------------------------------------------------------

    def render_markdown(self) -> str:
        """渲染 Markdown 6 章节报告。"""
        with self._lock:
            st = self._tracker.status()
            snaps = list(self._tracker._snapshots)

        lines = [
            "# BlueDeer 进化追踪报告",
            "",
            f"> 生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 1. 全局指标",
            "",
            f"- 当前世代：**{st['generation']}**",
            f"- 快照数：**{st['snapshot_count']}**",
            f"- 累计出生：**{st['birth_count']}**",
            f"- 累计死亡：**{st['death_count']}**",
            "",
            "## 2. 按物种累计",
            "",
            "| 物种 | 出生 | 死亡 | 繁殖 |",
            "|------|------|------|------|",
        ]
        all_species = (
            set(st["species_births"])
            | set(st["species_deaths"])
            | set(st["species_reproductions"])
        )
        for sp in sorted(all_species):
            b = st["species_births"].get(sp, 0)
            d = st["species_deaths"].get(sp, 0)
            r = st["species_reproductions"].get(sp, 0)
            lines.append(f"| {sp} | {b} | {d} | {r} |")

        if snaps:
            last = snaps[-1]
            lines.extend(
                [
                    "",
                    "## 3. 最近快照",
                    "",
                    f"- 时间：{datetime.datetime.fromtimestamp(last.timestamp).strftime('%Y-%m-%d %H:%M:%S')}",
                    f"- 存活总数：**{last.global_stats.get('total_alive', 0)}**",
                    f"- Shannon 多样性：**{last.global_stats.get('biodiversity', 0):.4f}**",
                    f"- 季节：**{last.global_stats.get('season', '?')}**",
                    "",
                    "## 4. 各物种详情",
                    "",
                    "| 物种 | 数量 | 平均能量 | 平均健康 | 平均年龄(天) |",
                    "|------|------|----------|----------|--------------|",
                ]
            )
            for sp, s in last.species_stats.items():
                lines.append(
                    f"| {sp} | {s['count']} | {s['avg_energy']:.1f} | "
                    f"{s['avg_health']:.1f} | {s['avg_age_days']:.2f} |"
                )

            # 趋势
            if len(snaps) >= 2:
                lines.extend(["", "## 5. 趋势", ""])
                for sp in last.species_stats:
                    trend = self._tracker.get_species_trend(sp, last_n=20)
                    if trend:
                        lines.append(f"### {sp} 数量趋势")
                        lines.append(f"  最近 20 张快照：{trend}")
                        lines.append("")

        lines.extend(
            [
                "",
                "## 6. 生存指标",
                "",
            ]
        )
        survival = self._tracker.get_survival_metrics()
        lines.append(f"- 总出生：{survival.get('total_births', 0)}")
        lines.append(f"- 总死亡：{survival.get('total_deaths', 0)}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """返回可视化器状态。"""
        with self._lock:
            t = self._tracker
            return {
                "tracker_status": t.status(),
                "snapshot_count": len(t._snapshots),
            }
