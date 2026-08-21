"""BlueDeer 交互式 CLI TUI：键盘控制全景看板。

用 termios + sys.stdin 单字符读取（纯标准库，无 curses）。
无 tty 环境（CI）自动降级为单帧渲染模式。

按键：
  q     退出
  r     刷新
  1/2/3 切换排行榜排序（综合/金币/成就）
  t     触发测试任务（显示测试结果）
  h     显示帮助
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from typing import Any, ClassVar

from core.tui_renderer import TUIRenderer

logger = logging.getLogger("bluedeer.cli_tui")

# sort_mode → 12 维榜单索引映射（由渲染器统一排序，避免双重排序冲突）
_SORT_MODE_TO_LB_INDEX: ClassVar[ClassVar[dict[str, int]]] = {
    "composite": 0,  # 综合
    "coins": 1,  # 金币
    "achievements": 5,  # 成就
}

# 尝试导入 termios（仅 Unix 可用）
try:
    import termios
    import tty

    _HAS_TTY = True
except ImportError:
    _HAS_TTY = False


class CLITUI:
    """交互式 CLI TUI。

    复用 TUIRenderer 渲染帧，键盘控制状态切换。
    无 tty 时降级为单帧渲染。

    用法：
        tui = CLITUI(renderer)
        tui.run(state_provider)
    """

    _THEMES: ClassVar[dict[str, dict[str, str]]] = {
        "default": {"fg": "", "bg": "", "accent": "\x1b[36m", "border": "\x1b[37m"},
        "dark": {
            "fg": "\x1b[37m",
            "bg": "\x1b[40m",
            "accent": "\x1b[33m",
            "border": "\x1b[90m",
        },
        "light": {
            "fg": "\x1b[30m",
            "bg": "\x1b[47m",
            "accent": "\x1b[34m",
            "border": "\x1b[90m",
        },
        "neon": {
            "fg": "\x1b[92m",
            "bg": "\x1b[40m",
            "accent": "\x1b[95m",
            "border": "\x1b[92m",
        },
        "monokai": {
            "fg": "\x1b[37m",
            "bg": "\x1b[40m",
            "accent": "\x1b[33m",
            "border": "\x1b[31m",
        },
    }

    def __init__(self, renderer: TUIRenderer) -> None:
        self._renderer = renderer
        self._running = False
        self._sort_mode = "composite"
        self._last_key = ""
        self._message = ""
        self._bindings: dict[str, Callable] = {}
        self._theme = "default"
        self._theme_data: dict = dict(self._THEMES["default"])

    @property
    def sort_mode(self) -> str:
        return self._sort_mode

    @property
    def last_key(self) -> str:
        return self._last_key

    @property
    def themes(self) -> dict:
        """获取所有可用主题。"""
        return dict(self._THEMES)

    def bind(self, key: str, handler: Callable) -> None:
        """注册按键绑定。"""
        self._bindings[key] = handler

    def set_theme(self, name: str) -> None:
        """设置配色主题。"""
        if name in self._THEMES:
            self._theme = name
            self._theme_data = dict(self._THEMES[name])
            self._message = f"主题: {name}"
        else:
            self._message = f"未知主题: {name}"

    def render_single_frame(self, state: dict[str, Any]) -> str:
        """渲染单帧（无交互，用于 CI 或 demo）。

        Returns:
            渲染后的字符串。
        """
        # 把 sort_mode 映射为榜单维度索引，由渲染器统一排序
        state = dict(state)
        if "leaderboard" in state:
            state["lb_index"] = _SORT_MODE_TO_LB_INDEX.get(self._sort_mode, 0)

        return self._renderer.render_frame_plain(state)

    def run(
        self,
        state_provider: Callable[[], dict[str, Any]],
        max_frames: int = 0,
    ) -> None:
        """运行交互式主循环。

        Args:
            state_provider: 返回当前状态字典的可调用对象。
            max_frames: 最大帧数（0=无限，用于测试时提前退出）。
        """
        if not _HAS_TTY or not sys.stdin.isatty():
            logger.info("无 tty 环境，降级为单帧渲染模式")
            state = state_provider()
            logger.info("\n%s", self.render_single_frame(state))
            return

        self._running = True
        frame_count = 0

        # 保存终端设置
        old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setraw(sys.stdin.fileno())
            # 开启光标复位（不清屏）
            sys.stdout.write("\x1b[H\x1b[2J")  # 首次清屏
            sys.stdout.flush()

            while self._running:
                state = state_provider()
                frame = self._render_interactive_frame(state)
                sys.stdout.write("\x1b[H" + frame)
                sys.stdout.flush()

                # 读取按键
                key = self._read_key()
                self._last_key = key
                self._handle_key(key)

                frame_count += 1
                if max_frames > 0 and frame_count >= max_frames:
                    break

        finally:
            # 恢复终端设置
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
            sys.stdout.write("\x1b[0m\n")  # 重置颜色 + 换行
            sys.stdout.flush()

    def _render_interactive_frame(self, state: dict[str, Any]) -> str:
        """渲染交互帧（含状态栏）。"""
        # 把 sort_mode 映射为榜单维度索引，由渲染器统一排序
        state = dict(state)
        if "leaderboard" in state:
            state["lb_index"] = _SORT_MODE_TO_LB_INDEX.get(self._sort_mode, 0)

        frame = self._renderer.render_frame_plain(state)

        # 追加状态栏
        status_line = (
            f"\n排序: {self._sort_mode} | "
            f"按键: q退出 r刷新 1综合 2金币 3成就 t测试 h帮助"
            f" | 最后: {self._last_key or '无'}"
        )
        if self._message:
            status_line += f" | {self._message}"
            self._message = ""

        return frame + status_line

    def _read_key(self) -> str:
        """读取单字符按键。"""
        try:
            ch = sys.stdin.read(1)
            return ch.lower() if ch else ""
        except OSError:
            return ""

    def _handle_key(self, key: str) -> None:
        """处理按键。"""
        if key in self._bindings:
            self._bindings[key]()
            return
        if key == "q":
            self._running = False
            self._message = "退出中..."
        elif key == "r":
            self._message = "已刷新"
        elif key == "1":
            self._sort_mode = "composite"
            self._message = "排序: 综合分"
        elif key == "2":
            self._sort_mode = "coins"
            self._message = "排序: 金币"
        elif key == "3":
            self._sort_mode = "achievements"
            self._message = "排序: 成就数"
        elif key == "t":
            self._message = "测试任务已触发（需外部接入）"
        elif key == "h":
            self._message = "q退出 r刷新 1/2/3排序 t测试"
        elif key:
            self._message = f"未知按键: {key}"


# ============== 状态栏辅助 ==============


def make_default_state_provider(
    harness: Any,
    reward: Any,
    token_auditor: Any,
    phase: str = "P8",
) -> Callable[[], dict[str, Any]]:
    """创建默认状态提供者（复用 demo_p6 的 build_state 逻辑）。

    Args:
        harness: Harness 实例。
        reward: RewardSystem 实例。
        token_auditor: TokenAuditor 实例。
        phase: 阶段标签。

    Returns:
        状态字典生成函数。
    """
    from modules.avatars import all_avatars

    def provider() -> dict[str, Any]:
        board = harness.aggregate()

        agents_state = []
        for avatar in all_avatars():
            profile = reward.get_profile(avatar.agent_id)
            agents_state.append(
                {
                    "agent_id": avatar.agent_id,
                    "name": avatar.name,
                    "role": avatar.role,
                    "status": "idle",
                    "level": profile.level,
                    "coins": profile.coins,
                }
            )

        tasks_state = []
        for tid, info in board.get("tasks", {}).items():
            tasks_state.append(
                {
                    "task_id": tid,
                    "status": info["status"],
                    "tokens": info["tokens"],
                    "assignee": "squirrel",
                }
            )

        leaderboard = board.get("rewards", [])

        achievements = []
        for avatar in all_avatars():
            for a in reward.get_achievements_detail(avatar.agent_id):
                achievements.append({"name": a["name"], "tier": a["tier"]})
        seen = set()
        unique_ach = []
        for a in achievements:
            if a["name"] not in seen:
                seen.add(a["name"])
                unique_ach.append(a)
        achievements = unique_ach[:20]

        savings = token_auditor.get_savings()
        token_stats = {
            "total": board.get("total_tokens", 0),
            "saved": savings["total_saved"],
            "lowcost_ratio": token_auditor.get_lowcost_ratio(),
        }

        return {
            "title": "BlueDeer 森林公司",
            "subtitle": f"P8 CLI TUI | {phase}",
            "stats": {
                "total": board["total"],
                "success": board["success"],
                "failed": board["failed"],
                "tokens": board["total_tokens"],
            },
            "agents": agents_state,
            "tasks": tasks_state,
            "leaderboard": leaderboard,
            "achievements": achievements,
            "token_stats": token_stats,
        }

    return provider
