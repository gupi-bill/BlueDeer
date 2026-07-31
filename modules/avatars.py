"""BlueDeer 12 动物员工像素头像 + 4 帧动画系统。

每个头像 6×4 像素矩阵，字符表示明暗：
- '#' 实心主体
- 'o' 中间调（眼睛/细节）
- '.' 浅色（高光）
- ' ' 空（透明）

P6 扩容新增：
- 4 套状态动画帧（idle/working/sleeping/error），每套 2 帧循环
- 专属气泡弹窗文本（每个状态配套提示）
- 每帧独立精灵矩阵，render_frame 按帧号取用
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.pixel_canvas import Color


# ============== 动画状态枚举 ==============

class AnimState(Enum):
    """员工动画状态。每状态配套 2 帧循环动画。"""
    IDLE = "idle"          # 空闲：轻微呼吸
    WORKING = "working"    # 工作：敲击动作
    SLEEPING = "sleeping"  # 休眠：闭眼波浪
    ERROR = "error"        # 报错：抖动感叹


# 每状态动画帧数
_FRAMES_PER_STATE = 2


@dataclass
class Avatar:
    """员工头像定义（含 4 状态动画帧）。"""
    agent_id: str          # 员工 ID
    name: str              # 中文名
    role: str              # 岗位
    sprite: list[str]      # 静态主像素矩阵（向后兼容，等同 idle 帧 0）
    color: int             # 主题色（ANSI 256）
    glyph: str             # 单字标识（用于紧凑显示）
    # P6 扩容：4 状态 × 2 帧动画。缺省回退到 sprite。
    frames: dict[str, list[list[str]]] = field(default_factory=dict)
    # 各状态配套气泡文本
    bubbles: dict[str, str] = field(default_factory=dict)

    @property
    def width(self) -> int:
        return max(len(row) for row in self.sprite) if self.sprite else 0

    @property
    def height(self) -> int:
        return len(self.sprite)

    def get_frame(self, state: AnimState | str, frame_idx: int = 0) -> list[str]:
        """取指定状态的某帧精灵。

        无动画帧时回退到静态 sprite。
        """
        state_key = state.value if isinstance(state, AnimState) else str(state)
        state_frames = self.frames.get(state_key)
        if not state_frames:
            return self.sprite
        idx = frame_idx % len(state_frames)
        return state_frames[idx]

    def get_bubble(self, state: AnimState | str) -> str:
        """取指定状态的气泡文本。"""
        state_key = state.value if isinstance(state, AnimState) else str(state)
        return self.bubbles.get(state_key, "")


# ============== 动画帧生成器 ==============
# 按"基础精灵 + 状态变形规则"自动派生 4 状态 × 2 帧，避免手写 88 块矩阵。
#
# 变形规则（针对 6×4 矩阵）：
# - idle 帧0：原样；帧1：整体下移 1 行（呼吸感）
# - working 帧0：眼睛 'o'→'.'（专注）；帧1：底行加 '-'（敲击）
# - sleeping 帧0：眼睛 'o'→'~'（闭眼）；帧1：顶行加 'z'（打鼾）
# - error 帧0：眼睛 'o'→'!'；帧1：整体左偏 1（抖动）+ 顶行 'x'

def _shift_rows(sprite: list[str], dx: int = 0, dy: int = 0) -> list[str]:
    """整体平移精灵，空位补空格。"""
    if not sprite:
        return sprite
    w = max(len(r) for r in sprite)
    h = len(sprite)
    # 先做 dy（行方向）
    rows = list(sprite)
    if dy > 0:
        rows = [" " * w] * dy + rows[:h - dy]
    elif dy < 0:
        rows = rows[-dy:] + [" " * w] * (-dy)
    # 再做 dx（列方向）
    out = []
    for r in rows:
        r = (r + " " * w)[:w]  # 补齐
        if dx > 0:
            r = " " * dx + r[:w - dx]
        elif dx < 0:
            r = r[-dx:] + " " * (-dx)
        out.append(r)
    return out


def _replace_char(sprite: list[str], old: str, new: str) -> list[str]:
    """替换精灵中所有 old 字符为 new。"""
    return [r.replace(old, new) for r in sprite]


def _set_row_char(sprite: list[str], row: int, char: str, positions: list[int]) -> list[str]:
    """在指定行的指定列设置字符（越界忽略）。"""
    out = list(sprite)
    if 0 <= row < len(out):
        r = list(out[row])
        for p in positions:
            if 0 <= p < len(r):
                r[p] = char
        out[row] = "".join(r)
    return out


def _gen_frames(base: list[str]) -> dict[str, list[list[str]]]:
    """从基础精灵派生 4 状态 × 2 帧动画。"""
    w = max(len(r) for r in base) if base else 6
    return {
        "idle": [
            base,
            _shift_rows(base, dy=1),
        ],
        "working": [
            _replace_char(base, "o", "."),
            _set_row_char(_replace_char(base, "o", "."), len(base) - 1, "-", [0, w - 1]),
        ],
        "sleeping": [
            _replace_char(base, "o", "~"),
            _set_row_char(_replace_char(base, "o", "~"), 0, "z", [0]),
        ],
        "error": [
            _replace_char(base, "o", "!"),
            _set_row_char(_shift_rows(base, dx=-1), 0, "x", [w - 1]),
        ],
    }


# 各状态通用气泡文本（可被单个 avatar 覆盖）
_DEFAULT_BUBBLES: dict[str, str] = {
    "idle": "待命中...",
    "working": "工作中...",
    "sleeping": "梦境中~",
    "error": "出错了!",
}


def _mk_avatar(
    agent_id: str, name: str, role: str, glyph: str,
    color: int, sprite: list[str],
    bubbles: dict[str, str] | None = None,
) -> Avatar:
    """构造带动画帧的头像。"""
    return Avatar(
        agent_id=agent_id,
        name=name,
        role=role,
        glyph=glyph,
        color=color,
        sprite=sprite,
        frames=_gen_frames(sprite),
        bubbles={**_DEFAULT_BUBBLES, **(bubbles or {})},
    )


# ============== 12 个员工头像 ==============
# 像素矩阵 6 宽 × 4 高，紧凑可辨识；动画帧由 _gen_frames 自动派生
# 子岗位头像基于父角色精灵做颜色变体

_AVATARS: list[Avatar] = [
    _mk_avatar(
        "squirrel", "较真松鼠", "全栈开发", "鼠", Color.ORANGE,
        [".o##o.", "#####o", "######", ".o##o."],
        {"working": "敲代码中", "error": "语法报错!"},
    ),
    _mk_avatar(
        "fox", "狡黠狐狸", "测试质量", "狐", Color.ORANGE,
        ["o##.o.", "#####o", "######", ".o##o."],
        {"working": "跑测试中", "error": "用例失败!"},
    ),
    _mk_avatar(
        "hedgehog", "戒备猬", "安全审计", "猬", Color.DARK_GREEN,
        ["#.#.#.", "######", "##oo##", "#....#"],
        {"working": "扫描漏洞中", "error": "高危拦截!"},
    ),
    _mk_avatar(
        "beaver", "勤恳海狸", "构建部署", "狸", Color.BROWN,
        [".o##o.", "######", "######", "#o##o#"],
        {"working": "提交代码中", "error": "构建失败!"},
    ),
    _mk_avatar(
        "owl", "夜枭猫头鹰", "架构设计", "鸮", Color.PURPLE,
        [".####.", "#o##o#", "######", ".####."],
        {"working": "推演架构中", "sleeping": "睁眼睡觉"},
    ),
    _mk_avatar(
        "soft_rabbit", "软耳兔", "像素美术", "兔", Color.PINK,
        ["o.##.o", ".####.", "######", ".o##o."],
        {"working": "绘制像素中", "error": "素材越界!"},
    ),
    _mk_avatar(
        "fox_security", "安全测试狐", "安全测试", "狐", Color.RED,
        ["o##.o.", "#####o", "######", ".o##o."],
        {"working": "安全扫描中", "error": "漏洞命中!"},
    ),
    _mk_avatar(
        "fox_art", "美术规范狐", "美术规范测试", "狐", Color.PURPLE,
        ["o##.o.", "#####o", "######", ".o##o."],
        {"working": "校验规范中", "error": "素材违规!"},
    ),
    _mk_avatar(
        "hedgehog_static", "静态扫描猬", "静态扫描", "猬", Color.DARK_GREEN,
        ["#.#.#.", "######", "##oo##", "#....#"],
        {"working": "静态扫描中", "error": "规则命中!"},
    ),
    _mk_avatar(
        "hedgehog_runtime", "运行时审计猬", "运行时审计", "猬", Color.TEAL,
        ["#.#.#.", "######", "##oo##", "#....#"],
        {"working": "运行时审计中", "error": "拦截告警!"},
    ),
    _mk_avatar(
        "hedgehog_keymgmt", "密钥管理猬", "密钥管理", "猬", Color.PURPLE,
        ["#.#.#.", "######", "##oo##", "#....#"],
        {"working": "密钥检测中", "error": "密钥泄露!"},
    ),
    _mk_avatar(
        "sparrow", "灵音雀", "状态播报", "雀", Color.LIME,
        ["..o#..", ".o##o.", "o####o", "..o#.."],
        {"working": "播报状态中", "error": "播报中断!"},
    ),
]


# ID → Avatar 映射
_AVATAR_MAP: dict[str, Avatar] = {a.agent_id: a for a in _AVATARS}


def get_avatar(agent_id: str) -> Avatar | None:
    """获取员工头像。"""
    return _AVATAR_MAP.get(agent_id)


def all_avatars() -> list[Avatar]:
    """获取全部头像。"""
    return list(_AVATARS)


def avatar_color_map(avatar: Avatar) -> dict[str, int]:
    """生成头像的颜色映射：主体用主题色，眼睛用黄色，高光用白色。

    P6 扩容：动画帧引入了 ~ ! - z x 等新字符，统一映射到状态色。
    """
    return {
        "#": avatar.color,
        "o": Color.YELLOW,
        ".": Color.WHITE,
        "~": Color.PURPLE,    # 闭眼
        "!": Color.RED,       # 报错感叹
        "-": Color.CYAN,      # 敲击
        "z": Color.LIME,      # 打鼾
        "x": Color.RED,       # 抖动
    }


# 状态色（用于头像旁的状态标识）
STATUS_COLORS: dict[str, int] = {
    "idle": Color.GRAY,        # 空闲
    "working": Color.GREEN,    # 工作中
    "success": Color.CYAN,     # 成功
    "failed": Color.RED,       # 失败
    "sleeping": Color.PURPLE,  # 梦境中
    "error": Color.RED,        # 报错（failed 的动画别名）
}


# ============== 任务状态 → 动画状态映射 ==============
# 业务状态（pending/running/success/failed）→ 动画状态
_TASK_TO_ANIM: dict[str, str] = {
    "pending": "idle",
    "running": "working",
    "success": "idle",
    "failed": "error",
    "idle": "idle",
    "working": "working",
    "sleeping": "sleeping",
}


def to_anim_state(task_status: str) -> str:
    """业务状态转动画状态。"""
    return _TASK_TO_ANIM.get(task_status, "idle")


# ============== 全局动画帧计数器 ==============
# 用于驱动所有头像同步循环动画。render 时传入当前帧号即可。

def anim_tick(global_frame: int) -> int:
    """取当前应显示的帧号（0/1 循环）。"""
    return global_frame % _FRAMES_PER_STATE


# ============== Avatar LRU 缓存 ==============

class AvatarCache:
    """LRU 缓存生成的 avatar，避免重复计算动画帧。"""

    def __init__(self, max_size: int = 100) -> None:
        self._max = max_size
        self._cache: dict[str, Avatar] = {}
        self._order: list[str] = []

    def get(self, name: str) -> Avatar | None:
        if name not in self._cache:
            return None
        self._order.remove(name)
        self._order.append(name)
        return self._cache[name]

    def put(self, name: str, avatar: Avatar) -> None:
        if name in self._cache:
            self._order.remove(name)
        elif len(self._cache) >= self._max:
            oldest = self._order.pop(0)
            del self._cache[oldest]
        self._cache[name] = avatar
        self._order.append(name)

    def generate(self, name: str, style: str = "default") -> Avatar:
        existing = self.get(name)
        if existing:
            return existing
        if style == "minimal":
            sprite = ["o##o.", "#####", "#####", ".o##o"]
        elif style == "blocky":
            sprite = [" ####", " ####", " ####", " ####"]
        else:
            sprite = [".o##o.", "#####o", "######", ".o##o."]
        avatar = Avatar(
            agent_id=name, name=name, role=style, sprite=sprite,
            color=Color.LIME, glyph=name[0] if name else "?",
            frames=_gen_frames(sprite),
            bubbles=dict(_DEFAULT_BUBBLES),
        )
        self.put(name, avatar)
        return avatar

    def delete_avatar(self, name: str) -> bool:
        if name not in self._cache:
            return False
        del self._cache[name]
        self._order.remove(name)
        return True

    def clear(self) -> None:
        self._cache.clear()
        self._order.clear()

    @property
    def size(self) -> int:
        return len(self._cache)

    @property
    def max_size(self) -> int:
        return self._max
