"""BlueDeer 像素画布：纯标准库 ANSI + Unicode 块字符渲染。

用二维网格存 (char, color)，渲染时转成 ANSI 着色字符串。
支持画像素/矩形/文本/精灵，越界自动裁剪。
"""

from __future__ import annotations

# ============== ANSI 颜色工具 ==============

# ANSI 转义：256 色前景/背景
_FG = "\x1b[38;5;{n}m"
_BG = "\x1b[48;5;{n}m"
_RESET = "\x1b[0m"


def fg(n: int) -> str:
    """前景色转义。"""
    return _FG.format(n=n)


def bg(n: int) -> str:
    """背景色转义。"""
    return _BG.format(n=n)


# 常用颜色（256 色码）
class Color:
    """常用 ANSI 256 色码。

    P0 UI 高级化：新增低饱和企业级色板（融合项目32 lovart 跨端色彩降级）。
    企业仪表盘风格：低饱和、护眼、不刺眼，保持公司严肃感。
    原高饱和色保留兼容，新代码优先用低饱和色。
    """

    # 原高饱和色（保留兼容）
    BLACK = 0
    WHITE = 255
    RED = 196
    GREEN = 46
    YELLOW = 226
    BLUE = 21
    CYAN = 51
    MAGENTA = 201
    ORANGE = 208
    GRAY = 240
    DARK_GREEN = 22
    DARK_BLUE = 18
    BROWN = 130
    PURPLE = 90
    PINK = 218
    LIME = 154
    TEAL = 37

    # P0 UI 高级化：低饱和企业级色板（严肃仪表盘风格）
    STEEL_BLUE = 67  # 钢蓝（标题/信息）替代高饱和 CYAN
    SAGE = 108  # 灰绿（成功/正常）替代高饱和 LIME
    AMBER = 179  # 琥珀（标题/警告）替代高饱和 YELLOW
    FOREST = 28  # 深森绿（边框/背景装饰）替代高饱和 GREEN
    SOFT_RED = 167  # 柔红（错误/告警）替代高饱和 RED
    SLATE = 243  # 石板灰（次要文本）替代高饱和 GRAY
    INDIGO = 60  # 靛蓝（扩展面板边框）替代高饱和 DARK_BLUE
    ROSE = 95  # 暗玫瑰（柔和强调）替代高饱和 PINK
    BRONZE = 137  # 青铜（铜阶成就）
    SILVER = 250  # 银（银阶成就/正文）
    GOLD = 221  # 金（金阶成就/标题高亮）


# ============== PixelCanvas ==============


class PixelCanvas:
    """像素画布：二维字符网格 + 颜色。

    每格存 (char, color)，渲染时按行拼成 ANSI 着色字符串。
    越界坐标自动忽略（裁剪）。
    """

    def __init__(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("画布尺寸必须 > 0")
        self._w = width
        self._h = height
        self._layers: dict[str, list[list[tuple[str, int]]]] = {}
        self._default_layer = "base"
        self._layers[self._default_layer] = self._make_grid()
        self._undo_histories: dict[str, list[list[list[tuple[str, int]]]]] = {}
        self._undo_histories[self._default_layer] = []

    def _make_grid(self) -> list[list[tuple[str, int]]]:
        return [[(" ", Color.WHITE) for _ in range(self._w)] for _ in range(self._h)]

    def _snapshot_layer(self, name: str) -> None:
        hist = self._undo_histories.setdefault(name, [])
        grid = self._layers.get(name)
        if grid:
            snap = [[c for c in row] for row in grid]
            hist.append(snap)
            if len(hist) > 50:
                hist.pop(0)

    # ---- 图层 ----

    def add_layer(self, name: str) -> None:
        """新增图层，初始为空。"""
        if name not in self._layers:
            self._layers[name] = self._make_grid()
            self._undo_histories[name] = []

    def get_layer(self, name: str) -> list[list[tuple[str, int]]] | None:
        """获取图层数据（只读副本）。"""
        grid = self._layers.get(name)
        return [[c for c in row] for row in grid] if grid else None

    def set_pixel(
        self,
        x: int,
        y: int,
        char: str,
        color: int = Color.WHITE,
        layer: str | None = None,
    ) -> None:
        """画像素到指定图层（默认 base）。"""
        l = layer or self._default_layer
        grid = self._layers.get(l)
        if grid is None:
            return
        if not (0 <= x < self._w and 0 <= y < self._h):
            return
        if not char:
            return
        self._snapshot_layer(l)
        grid[y][x] = (char[0], color)

    @property
    def width(self) -> int:
        return self._w

    @property
    def height(self) -> int:
        return self._h

    def clear(self) -> None:
        """清空画布（所有图层）。"""
        for grid in self._layers.values():
            for y in range(self._h):
                for x in range(self._w):
                    grid[y][x] = (" ", Color.WHITE)

    def _in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self._w and 0 <= y < self._h

    def set_pixel(
        self,
        x: int,
        y: int,
        char: str,
        color: int = Color.WHITE,
        layer: str | None = None,
    ) -> None:
        """画单个像素。越界忽略。layer 指定图层。"""
        l = layer or self._default_layer
        grid = self._layers.get(l)
        if grid is None:
            return
        if not self._in_bounds(x, y):
            return
        if not char:
            return
        self._snapshot_layer(l)
        grid[y][x] = (char[0], color)

    def get_pixel(self, x: int, y: int) -> tuple[str, int] | None:
        """获取像素（扫描所有图层，上层优先），越界返回 None。"""
        if not self._in_bounds(x, y):
            return None
        result: tuple[str, int] | None = None
        for grid in self._layers.values():
            ch, color = grid[y][x]
            if ch != " ":
                result = (ch, color)
        return result

    def undo_layer(self, name: str) -> bool:
        """撤销指定图层的上一步操作。"""
        hist = self._undo_histories.get(name)
        if not hist:
            return False
        prev = hist.pop()
        self._layers[name] = prev
        return True

    def draw_rect(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        char: str = "#",
        color: int = Color.WHITE,
        fill: bool = True,
    ) -> None:
        """画矩形。fill=True 填充，否则只画边框。"""
        if w <= 0 or h <= 0:
            return
        x2, y2 = x + w - 1, y + h - 1
        for yy in range(y, y2 + 1):
            for xx in range(x, x2 + 1):
                if not fill:
                    # 仅边框
                    is_border = xx == x or xx == x2 or yy == y or yy == y2
                    if not is_border:
                        continue
                self.set_pixel(xx, yy, char, color)

    def draw_text(
        self,
        x: int,
        y: int,
        text: str,
        color: int = Color.WHITE,
    ) -> None:
        """写文本（单行，左对齐）。越界部分裁剪。"""
        for i, ch in enumerate(text):
            self.set_pixel(x + i, y, ch, color)

    def draw_text_centered(
        self,
        y: int,
        text: str,
        color: int = Color.WHITE,
    ) -> None:
        """居中写文本。"""
        x = (self._w - len(text)) // 2
        self.draw_text(x, y, text, color)

    def draw_sprite(
        self,
        x: int,
        y: int,
        sprite: list[str],
        color_map: dict[str, int] | None = None,
    ) -> None:
        """画精灵（多行字符串列表）。

        Args:
            x, y: 左上角坐标。
            sprite: 每行一个字符串，每个字符是一个像素。
            color_map: 字符 → 颜色映射；未映射的字符用 Color.WHITE。
        """
        color_map = color_map or {}
        for row_idx, row in enumerate(sprite):
            for col_idx, ch in enumerate(row):
                if ch == " ":
                    continue  # 空格不覆盖
                c = color_map.get(ch, Color.WHITE)
                self.set_pixel(x + col_idx, y + row_idx, ch, c)

    def draw_border(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        color: int = Color.GRAY,
    ) -> None:
        """画边框（用 Unicode 制表符）。"""
        if w < 2 or h < 2:
            return
        x2, y2 = x + w - 1, y + h - 1
        # 四角
        self.set_pixel(x, y, "┌", color)
        self.set_pixel(x2, y, "┐", color)
        self.set_pixel(x, y2, "└", color)
        self.set_pixel(x2, y2, "┘", color)
        # 横线
        for xx in range(x + 1, x2):
            self.set_pixel(xx, y, "─", color)
            self.set_pixel(xx, y2, "─", color)
        # 竖线
        for yy in range(y + 1, y2):
            self.set_pixel(x, yy, "│", color)
            self.set_pixel(x2, yy, "│", color)

    def _composite_grid(self) -> list[list[tuple[str, int]]]:
        """将各图层从上到下合成到 base。"""
        base = self._layers.get(self._default_layer, self._make_grid())
        base_copy = [[c for c in row] for row in base]
        for lname, grid in self._layers.items():
            if lname == self._default_layer:
                continue
            for y in range(self._h):
                for x in range(self._w):
                    ch, color = grid[y][x]
                    if ch != " ":
                        base_copy[y][x] = (ch, color)
        return base_copy

    def render(self) -> str:
        """渲染成 ANSI 着色字符串（合成所有图层）。"""
        composite = self._composite_grid()
        lines: list[str] = []
        for y in range(self._h):
            buf: list[str] = []
            cur_color: int | None = None
            for x in range(self._w):
                ch, color = composite[y][x]
                if color != cur_color:
                    buf.append(fg(color))
                    cur_color = color
                buf.append(ch)
            buf.append(_RESET)
            lines.append("".join(buf))
        return "\n".join(lines)

    def render_plain(self) -> str:
        """渲染成纯文本（无 ANSI 颜色），用于截图导出。"""
        composite = self._composite_grid()
        lines: list[str] = []
        for y in range(self._h):
            line = "".join(composite[y][x][0] for x in range(self._w))
            lines.append(line)
        return "\n".join(lines)
