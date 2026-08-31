from __future__ import annotations

import asyncio
from typing import Any

from core.pixel_canvas import Color, PixelCanvas
from modules.avatars import (
    all_avatars,
    anim_tick,
    avatar_color_map,
    to_anim_state,
)
from modules.glow.alert_glow import AlertGlowRenderer
from modules.glow.role_glow import RoleGlowRenderer
from modules.scene_assets import (
    LANTERN_COLOR,
    LANTERN_SPRITE,
    STATUS_ICON_COLORS,
    STATUS_ICONS,
    TASK_FLOW_COLOR,
    TASK_FLOW_FRAMES,
    TREE_COLOR,
    TREE_SPRITE,
)

DEFAULT_WIDTH = 100
DEFAULT_HEIGHT = 30
LEGACY_WIDTH = 80
LEGACY_HEIGHT = 24

LEADERBOARD_DIMENSIONS: list[tuple[str, str]] = [
    ("composite", "综合"),
    ("coins", "金币"),
    ("exp", "经验"),
    ("level", "等级"),
    ("favor", "好感"),
    ("achievements", "成就"),
    ("code_lines", "代码行"),
    ("dream_memories", "梦境"),
    ("scan_count", "扫描"),
    ("block_count", "拦截"),
    ("token_saved", "省Token"),
    ("lowcost_ratio", "低成本%"),
]

DEFAULT_LB_INDEX = 0


class DirtyTracker:
    def __init__(self):
        self._dirty: set[tuple[int, int, int, int]] = set()

    def mark(self, x: int, y: int, w: int, h: int) -> None:
        self._dirty.add((x, y, w, h))

    def drain(self) -> set[tuple[int, int, int, int]]:
        out = self._dirty
        self._dirty = set()
        return out

    def clear(self) -> None:
        self._dirty.clear()


class VirtualViewport:
    def __init__(self, total_lines: int, view_h: int, scroll_y: int = 0):
        self._total = total_lines
        self._view_h = view_h
        self._scroll_y = scroll_y

    @property
    def scroll_y(self) -> int:
        return self._scroll_y

    def scroll_to(self, y: int) -> None:
        self._scroll_y = max(0, min(y, self._total - self._view_h))

    def scroll_by(self, dy: int) -> None:
        self.scroll_to(self._scroll_y + dy)

    @property
    def visible_range(self) -> tuple[int, int]:
        start = self._scroll_y
        end = min(start + self._view_h, self._total)
        return start, end

    @property
    def is_top(self) -> bool:
        return self._scroll_y <= 0

    @property
    def is_bottom(self) -> bool:
        return self._scroll_y >= self._total - self._view_h


class TUIRenderer:
    def __init__(
        self,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
    ) -> None:
        self._w = width
        self._h = height
        self._alert_glow = AlertGlowRenderer()
        self._role_glow = RoleGlowRenderer()
        self._dirty = DirtyTracker()
        self._prev_canvas: PixelCanvas | None = None
        self._viewport = VirtualViewport(0, height)
        self._full_render = True

    @property
    def width(self) -> int:
        return self._w

    @property
    def height(self) -> int:
        return self._h

    def scroll_up(self, lines: int = 3) -> None:
        self._viewport.scroll_by(-lines)
        self._full_render = True

    def scroll_down(self, lines: int = 3) -> None:
        self._viewport.scroll_by(lines)
        self._full_render = True

    def render_frame(self, state: dict[str, Any]) -> str:
        canvas = PixelCanvas(self._w, self._h)
        self._draw_layout(canvas, state)
        if self._full_render or self._prev_canvas is None:
            self._prev_canvas = canvas
            self._full_render = False
            return "\x1b[H\x1b[2J" + canvas.render()
        diff = self._compute_diff(self._prev_canvas, canvas)
        self._prev_canvas = canvas
        if not diff:
            return ""
        out_parts = []
        for y, line in diff:
            out_parts.append(f"\x1b[{y + 1};1H{line}")
        return "".join(out_parts)

    def render_frame_plain(self, state: dict[str, Any]) -> str:
        canvas = PixelCanvas(self._w, self._h)
        self._draw_layout(canvas, state)
        return canvas.render_plain()

    async def render_frame_async(self, state: dict[str, Any]) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.render_frame, state)

    def render_incremental(
        self,
        state: dict[str, Any],
        changed_regions: list[tuple[int, int, int, int]] | None = None,
    ) -> str:
        if not changed_regions:
            return self.render_frame(state)
        canvas = PixelCanvas(self._w, self._h)
        self._draw_layout(canvas, state)
        if self._prev_canvas is None:
            self._prev_canvas = canvas
            return "\x1b[H\x1b[2J" + canvas.render()
        out_parts = []
        for x, y, w, h in changed_regions:
            for row in range(y, min(y + h, self._h)):
                prev_line = (
                    self._prev_canvas._lines[row]
                    if hasattr(self._prev_canvas, "_lines")
                    and row < len(self._prev_canvas._lines)
                    else ""
                )
                cur_line = (
                    canvas._lines[row]
                    if hasattr(canvas, "_lines") and row < len(canvas._lines)
                    else ""
                )
                if prev_line != cur_line:
                    out_parts.append(f"\x1b[{row + 1};1H{cur_line}")
        self._prev_canvas = canvas
        self._full_render = False
        if not out_parts:
            return ""
        return "".join(out_parts)

    def mark_dirty(self, x: int, y: int, w: int, h: int) -> None:
        self._dirty.mark(x, y, w, h)

    def _compute_diff(
        self, prev: PixelCanvas, cur: PixelCanvas
    ) -> list[tuple[int, str]]:
        changed = []
        for y in range(self._h):
            prev_line = (
                prev._lines[y]
                if hasattr(prev, "_lines") and y < len(prev._lines)
                else ""
            )
            cur_line = (
                cur._lines[y] if hasattr(cur, "_lines") and y < len(cur._lines) else ""
            )
            if prev_line != cur_line:
                changed.append((y, cur_line))
        return changed

    def _draw_layout(self, canvas: PixelCanvas, state: dict[str, Any]) -> None:
        w, h = self._w, self._h
        global_frame = state.get("global_frame", 0)
        alert = state.get("alert", False)

        self._draw_title_bar(canvas, state, alert)

        has_extended = h >= LEGACY_HEIGHT + 4
        bottom_h = 4
        ext_h = 4 if has_extended else 0
        body_y = 3
        body_h = h - 3 - ext_h - bottom_h

        left_w = 22
        mid_x = left_w + 1
        mid_w = 30
        right_x = mid_x + mid_w + 1
        right_w = w - right_x - 1

        self._draw_avatar_wall(canvas, 0, body_y, left_w, body_h, state, global_frame)

        canvas.draw_border(mid_x, body_y, mid_w, body_h, color=Color.SLATE)
        canvas.draw_text(mid_x + 1, body_y, "\u256c任务看板", Color.AMBER)
        self._draw_task_board(
            canvas,
            mid_x + 1,
            body_y + 2,
            mid_w - 2,
            body_h - 3,
            state,
            global_frame,
        )

        canvas.draw_border(right_x, body_y, right_w, body_h, color=Color.SLATE)
        lb_idx = state.get("lb_index", DEFAULT_LB_INDEX)
        lb_name = (
            LEADERBOARD_DIMENSIONS[lb_idx][1]
            if lb_idx < len(LEADERBOARD_DIMENSIONS)
            else "综合"
        )
        canvas.draw_text(right_x + 1, body_y, f"\u256c排行榜[{lb_name}]", Color.AMBER)
        self._draw_leaderboard(
            canvas,
            right_x + 1,
            body_y + 2,
            right_w - 2,
            body_h - 3,
            state,
            lb_idx,
        )

        if has_extended:
            ext_y = body_y + body_h
            self._draw_extended_panels(canvas, 0, ext_y, w, ext_h, state, global_frame)

        bottom_y = h - bottom_h
        border_color = Color.SOFT_RED if alert else Color.INDIGO
        canvas.draw_border(0, bottom_y, w, bottom_h, color=border_color)
        canvas.draw_text(1, bottom_y, "\u256c成就墙", Color.AMBER)
        self._draw_achievements(canvas, 1, bottom_y + 1, w - 2, state)
        self._draw_token_bar(canvas, 1, bottom_y + 3, w - 2, state)

        self._draw_decorations(canvas, w, h, global_frame)

    def _draw_title_bar(
        self,
        canvas: PixelCanvas,
        state: dict[str, Any],
        alert: bool,
    ) -> None:
        w = self._w
        title = state.get("title", "BlueDeer \u68ee\u6797\u516c\u53f8")
        subtitle = state.get("subtitle", "")
        stats = state.get("stats", {})

        border_color = Color.SOFT_RED if alert else Color.FOREST
        canvas.draw_border(0, 0, w, 3, color=border_color)
        canvas.draw_text_centered(
            1, f"\u2554\u2550\u2550 {title} \u2550\u2550\u2557", Color.GOLD
        )
        info = (
            f"{subtitle} | \u4efb\u52a1:{stats.get('total', 0)} "
            f"\u6210\u529f:{stats.get('success', 0)} \u5931\u8d25:{stats.get('failed', 0)} "
            f"Token:{stats.get('tokens', 0)}"
        )
        canvas.draw_text(2, 2, info[: w - 4], Color.STEEL_BLUE)

    def _draw_avatar_wall(
        self,
        canvas: PixelCanvas,
        x: int,
        y: int,
        w: int,
        h: int,
        state: dict[str, Any],
        global_frame: int,
    ) -> None:
        canvas.draw_border(x, y, w, h, color=Color.SLATE)
        canvas.draw_text(x + 1, y, "\u256c\u5458\u5de5", Color.AMBER)

        agents = state.get("agents", [])
        avatars = all_avatars()
        agent_status: dict[str, dict[str, Any]] = {
            a.get("agent_id", ""): a for a in agents
        }

        col_w = 10
        row_h = 6
        cols = max(1, (w - 2) // col_w)
        frame_idx = anim_tick(global_frame)

        start_y, end_y = self._viewport.visible_range
        for idx, avatar in enumerate(avatars):
            col = idx % cols
            row = idx // cols
            ax = x + 1 + col * col_w
            ay = y + 2 + row * row_h
            if ay + row_h > y + h:
                break
            if ay + row_h < y + start_y or ay > y + end_y:
                continue

            ag = agent_status.get(avatar.agent_id, {})
            task_status = ag.get("status", "idle")
            anim_state = to_anim_state(task_status)

            sprite = avatar.get_frame(anim_state, frame_idx)
            cmap = avatar_color_map(avatar)
            canvas.draw_sprite(ax, ay, sprite, cmap)

            name = avatar.name[:col_w]
            canvas.draw_text(ax, ay + avatar.height, name, avatar.color)

            icon = STATUS_ICONS.get(anim_state, ["  "])[0]
            icon_color = STATUS_ICON_COLORS.get(anim_state, Color.GRAY)
            level = ag.get("level", 1)
            status_text = f"Lv{level} {icon}"
            canvas.draw_text(ax, ay + avatar.height + 1, status_text, icon_color)

    def _draw_task_board(
        self,
        canvas: PixelCanvas,
        x: int,
        y: int,
        w: int,
        h: int,
        state: dict[str, Any],
        global_frame: int,
    ) -> None:
        tasks = state.get("tasks", [])
        if not tasks:
            canvas.draw_text(x, y, "(\u6682\u65e0\u4efb\u52a1)", Color.GRAY)
            return

        header = f"{'任务ID':<10} {'状态':<8} {'员工':<8} {'Token':>6}"
        canvas.draw_text(x, y, header[:w], Color.STEEL_BLUE)

        status_color = {
            "success": Color.SAGE,
            "failed": Color.SOFT_RED,
            "pending": Color.AMBER,
            "running": Color.SAGE,
        }

        start_y, end_y = self._viewport.visible_range
        for i, task in enumerate(tasks[: h - 1]):
            row_y = y + 1 + i
            if row_y < y + start_y or row_y > y + end_y:
                continue
            tid = task.get("task_id", "")[:10]
            status = task.get("status", "")[:8]
            assignee = task.get("assignee", "")[:8]
            tokens = task.get("tokens", 0)
            line = f"{tid:<10} {status:<8} {assignee:<8} {tokens:>6}"
            sc = status_color.get(task.get("status", ""), Color.SILVER)
            canvas.draw_text(x, row_y, line[:w], sc)

        if h > len(tasks) + 2:
            flow_idx = global_frame % len(TASK_FLOW_FRAMES)
            flow = TASK_FLOW_FRAMES[flow_idx][0]
            flow_line = flow[:w]
            canvas.draw_text(x, y + h - 1, flow_line, TASK_FLOW_COLOR)

    def _draw_leaderboard(
        self,
        canvas: PixelCanvas,
        x: int,
        y: int,
        w: int,
        h: int,
        state: dict[str, Any],
        lb_idx: int,
    ) -> None:
        board = state.get("leaderboard", [])
        if not board:
            canvas.draw_text(x, y, "(\u6682\u65e0\u6570\u636e)", Color.GRAY)
            return

        dim_key = (
            LEADERBOARD_DIMENSIONS[lb_idx][0]
            if lb_idx < len(LEADERBOARD_DIMENSIONS)
            else "composite"
        )

        def sort_key(entry: dict[str, Any]) -> Any:
            if dim_key == "composite":
                return entry.get("level", 1) * 1000 + entry.get("coins", 0)
            if dim_key == "achievements":
                return len(entry.get("achievements", []))
            return entry.get(dim_key, 0)

        sorted_board = sorted(board, key=sort_key, reverse=True)

        dim_name = (
            LEADERBOARD_DIMENSIONS[lb_idx][1]
            if lb_idx < len(LEADERBOARD_DIMENSIONS)
            else "综合"
        )
        header = f"{'员工':<8} {'Lv':>3} {'金币':>5} {dim_name:>6}"
        canvas.draw_text(x, y, header[:w], Color.STEEL_BLUE)

        start_y, end_y = self._viewport.visible_range
        for i, entry in enumerate(sorted_board[: h - 1]):
            row_y = y + 1 + i
            if row_y < y + start_y or row_y > y + end_y:
                continue
            aid = entry.get("agent_id", "")[:8]
            level = entry.get("level", 1)
            coins = entry.get("coins", 0)
            dim_val = (
                sort_key(entry) if dim_key == "composite" else entry.get(dim_key, 0)
            )
            if dim_key == "achievements":
                dim_val = len(entry.get("achievements", []))
            medal = ["\u2460", "\u2461", "\u2462", " ", " "][min(i, 4)]
            line = f"{medal}{aid:<7} {level:>3} {coins:>5} {dim_val:>6}"
            color = [Color.GOLD, Color.SILVER, Color.BRONZE, Color.SLATE, Color.SLATE][
                min(i, 4)
            ]
            canvas.draw_text(x, row_y, line[:w], color)

    def _draw_extended_panels(
        self,
        canvas: PixelCanvas,
        x: int,
        y: int,
        w: int,
        h: int,
        state: dict[str, Any],
        global_frame: int,
    ) -> None:
        panel_w = (w - 3) // 4
        panels = [
            ("\u256c\u68a6\u5883", state.get("dream", {}), self._draw_dream_panel),
            (
                "\u256c\u5b89\u5168",
                state.get("security", {}),
                self._draw_security_panel,
            ),
            ("\u256cGitOps", state.get("gitops", {}), self._draw_gitops_panel),
            ("\u256c\u6a21\u578b", state.get("models", {}), self._draw_models_panel),
        ]
        for i, (title, data, drawer) in enumerate(panels):
            px = x + i * (panel_w + 1)
            canvas.draw_border(px, y, panel_w, h, color=Color.INDIGO)
            canvas.draw_text(px + 1, y, title, Color.AMBER)
            drawer(canvas, px + 1, y + 1, panel_w - 2, h - 2, data)

    def _draw_dream_panel(
        self,
        canvas: PixelCanvas,
        x: int,
        y: int,
        w: int,
        h: int,
        data: dict[str, Any],
    ) -> None:
        phase = data.get("phase", "-")
        memories = data.get("memories", 0)
        quality = data.get("quality", {})
        nightmares = data.get("nightmares", 0)
        line1 = f"\u9636\u6bb5:{phase}"
        line2 = f"\u8bb0\u5fc6:{memories} \u5669\u68a6:{nightmares}"
        line3 = f"\u666e{quality.get('normal', 0)}/\u9ad8{quality.get('high', 0)}/\u4f20{quality.get('legendary', 0)}"
        canvas.draw_text(x, y, line1[:w], Color.ROSE)
        canvas.draw_text(x, y + 1, line2[:w], Color.STEEL_BLUE)
        canvas.draw_text(x, y + 2, line3[:w], Color.SAGE)

    def _draw_security_panel(
        self,
        canvas: PixelCanvas,
        x: int,
        y: int,
        w: int,
        h: int,
        data: dict[str, Any],
    ) -> None:
        scans = data.get("scans", 0)
        blocks = data.get("blocks", 0)
        alerts = data.get("alerts", 0)
        line1 = f"\u626b\u63cf:{scans} \u62e6\u622a:{blocks}"
        line2 = f"\u544a\u8b66:{alerts}"
        canvas.draw_text(x, y, line1[:w], Color.SAGE)
        alert_color = Color.SOFT_RED if alerts > 0 else Color.SLATE
        canvas.draw_text(x, y + 1, line2[:w], alert_color)

    def _draw_gitops_panel(
        self,
        canvas: PixelCanvas,
        x: int,
        y: int,
        w: int,
        h: int,
        data: dict[str, Any],
    ) -> None:
        commits = data.get("commits", 0)
        branch = data.get("branch", "-")[:8]
        status = data.get("status", "clean")[:6]
        last_pr = data.get("last_pr", "-")[:10]
        line1 = f"\u5206\u652f:{branch}"
        line2 = f"\u63d0\u4ea4:{commits} \u72b6\u6001:{status}"
        line3 = f"PR:{last_pr}"
        canvas.draw_text(x, y, line1[:w], Color.BRONZE)
        canvas.draw_text(x, y + 1, line2[:w], Color.STEEL_BLUE)
        canvas.draw_text(x, y + 2, line3[:w], Color.SLATE)

    def _draw_models_panel(
        self,
        canvas: PixelCanvas,
        x: int,
        y: int,
        w: int,
        h: int,
        data: dict[str, Any],
    ) -> None:
        routes = data.get("routes", 0)
        fallbacks = data.get("fallbacks", 0)
        active = data.get("active", "-")[:10]
        line1 = f"\u8def\u7531:{routes} \u56de\u9000:{fallbacks}"
        line2 = f"\u5f53\u524d:{active}"
        canvas.draw_text(x, y, line1[:w], Color.STEEL_BLUE)
        canvas.draw_text(x, y + 1, line2[:w], Color.SAGE)

    def _draw_achievements(
        self,
        canvas: PixelCanvas,
        x: int,
        y: int,
        w: int,
        state: dict[str, Any],
    ) -> None:
        achievements = state.get("achievements", [])
        if not achievements:
            canvas.draw_text(x, y, "(\u5c1a\u672a\u89e3\u9501\u6210\u5c31)", Color.GRAY)
            return

        tier_color = {
            "bronze": Color.BRONZE,
            "silver": Color.SILVER,
            "gold": Color.GOLD,
        }
        cur_x = x
        for ach in achievements:
            name = ach.get("name", "")[:6]
            tier = ach.get("tier", "bronze")
            color = tier_color.get(tier, Color.WHITE)
            tag = f"[{name}]"
            if cur_x + len(tag) > x + w:
                break
            canvas.draw_text(cur_x, y, tag, color)
            cur_x += len(tag) + 1

    def _draw_token_bar(
        self,
        canvas: PixelCanvas,
        x: int,
        y: int,
        w: int,
        state: dict[str, Any],
    ) -> None:
        token_stats = state.get("token_stats", {})
        total = token_stats.get("total", 0)
        saved = token_stats.get("saved", 0)
        ratio = token_stats.get("lowcost_ratio", 0)

        label = f"Token:{total} \u8282\u7701:{saved} \u4f4e\u6210\u672c\u5360\u6bd4:{ratio}%"
        canvas.draw_text(x, y, label[:w], Color.SAGE)

        bar_w = min(20, w - len(label) - 2)
        if bar_w > 0:
            bar_x = x + len(label) + 1
            filled = int(bar_w * ratio / 100)
            canvas.draw_text(
                bar_x,
                y,
                "[" + "\u2588" * filled + "\u2591" * (bar_w - filled) + "]",
                Color.SAGE,
            )

    def _draw_decorations(
        self,
        canvas: PixelCanvas,
        w: int,
        h: int,
        global_frame: int,
    ) -> None:
        if w >= 20:
            canvas.draw_sprite(1, 1, TREE_SPRITE, {"#": TREE_COLOR, " ": None})
            canvas.draw_sprite(w - 6, 1, TREE_SPRITE, {"#": TREE_COLOR, " ": None})
        if w >= 40:
            canvas.draw_sprite(
                8,
                0,
                LANTERN_SPRITE,
                {
                    "\\": LANTERN_COLOR,
                    "/": LANTERN_COLOR,
                    "|": LANTERN_COLOR,
                    "-": LANTERN_COLOR,
                    "o": Color.ORANGE,
                },
            )
            canvas.draw_sprite(
                w - 11,
                0,
                LANTERN_SPRITE,
                {
                    "\\": LANTERN_COLOR,
                    "/": LANTERN_COLOR,
                    "|": LANTERN_COLOR,
                    "-": LANTERN_COLOR,
                    "o": Color.ORANGE,
                },
            )
