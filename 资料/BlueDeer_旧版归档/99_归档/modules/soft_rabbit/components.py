"""UI 板块五：标准化交互弹窗 & 面板通用组件库。

三大组件（全平台复用，可批量新增）：
1. 统一气泡弹窗渲染组件：8 类细分弹窗（对话/通知/告警/成就/梦境/安全/Git/Token），
   每类独立边框、图标、配色，跨端共用一套规范。
2. 通用模块化面板容器：8 基础 → 32 类细分功能面板（含监控/测试/美术/安全/运维/数据），
   一套容器代码跨端渲染，可无限新增面板类型。
3. 跨端快捷键交互美化套件：统一快捷键提示面板、选中高亮、光标像素渲染。

纯 Python 标准库，无第三方依赖，无 TRAe 绑定。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ============== 边框字符集 ==============
# 5 种边框样式对应字符（用于跨端统一渲染）
BORDER_CHARS: dict[str, dict[str, str]] = {
    "single": {"tl": "┌", "tr": "┐", "bl": "└", "br": "┘", "h": "─", "v": "│"},
    "double": {"tl": "╔", "tr": "╗", "bl": "╚", "br": "╝", "h": "═", "v": "║"},
    "rounded": {"tl": "╭", "tr": "╮", "bl": "╰", "br": "╯", "h": "─", "v": "│"},
    "ascii": {"tl": "+", "tr": "+", "bl": "+", "br": "+", "h": "-", "v": "|"},
    "pixel": {"tl": "▛", "tr": "▜", "bl": "▙", "br": "▟", "h": "▀", "v": "▌"},
}


# ============== 气泡弹窗 ==============

# 8 类弹窗类型
BUBBLE_TYPES = (
    "dialog",  # 普通对话
    "notice",  # 任务通知
    "alert",  # 高危告警
    "achievement",  # 成就解锁
    "dream_report",  # 梦境报告
    "security_audit",  # 安全审计
    "git_push",  # Git 推送反馈
    "token_report",  # Token 成本报表
)


@dataclass
class BubbleSpec:
    """气泡弹窗规格。"""

    type: str  # BUBBLE_TYPES 之一
    title: str  # 默认标题
    color_key: str  # 主题色板键（决定边框/标题色）
    border_style: str  # 边框样式（BORDER_CHARS 键）
    icon: str  # 像素图标字符


# 8 类弹窗预设（每类独立边框 + 图标 + 配色键）
_BUBBLE_PRESETS: dict[str, BubbleSpec] = {
    "dialog": BubbleSpec("dialog", "对话", "text", "single", "💬"),
    "notice": BubbleSpec("notice", "通知", "info", "single", "📋"),
    "alert": BubbleSpec("alert", "高危告警", "error", "double", "⚠"),
    "achievement": BubbleSpec("achievement", "成就解锁", "title", "double", "🎖"),
    "dream_report": BubbleSpec("dream_report", "梦境报告", "accent", "rounded", "💭"),
    "security_audit": BubbleSpec(
        "security_audit", "安全审计", "security", "pixel", "🛡"
    ),
    "git_push": BubbleSpec("git_push", "Git 推送", "success", "single", "📦"),
    "token_report": BubbleSpec("token_report", "Token 报表", "warning", "ascii", "🪙"),
}


class BubbleRenderer:
    """统一气泡弹窗渲染器。

    跨端共用一套像素气泡规范：自动适配宽度、独立边框、图标配色。
    """

    def __init__(self) -> None:
        self._presets: dict[str, BubbleSpec] = dict(_BUBBLE_PRESETS)

    def get_preset(self, bubble_type: str) -> BubbleSpec:
        """取弹窗预设。"""
        if bubble_type not in self._presets:
            raise ValueError(
                f"未知弹窗类型: {bubble_type}（可选: {list(self._presets.keys())}）"
            )
        return self._presets[bubble_type]

    def register(self, spec: BubbleSpec) -> None:
        """注册自定义弹窗类型。"""
        self._presets[spec.type] = spec

    def list_types(self) -> list[str]:
        return list(self._presets.keys())

    def render(
        self,
        bubble_type: str,
        title: str | None = None,
        body: str = "",
        width: int = 40,
    ) -> list[str]:
        """渲染弹窗为多行字符串列表。

        Args:
            bubble_type: 弹窗类型。
            title: 标题（None 用预设标题）。
            body: 正文（多行用 \\n 分隔）。
            width: 弹窗宽度。
        """
        spec = self.get_preset(bubble_type)
        chars = BORDER_CHARS.get(spec.border_style, BORDER_CHARS["single"])
        actual_title = title if title is not None else spec.title

        # 标题行：图标 + 标题
        header_text = f"{spec.icon} {actual_title}"
        inner_w = width - 2  # 去掉左右边框
        header_inner = header_text[:inner_w].ljust(inner_w)

        lines: list[str] = []
        # 顶边
        lines.append(f"{chars['tl']}{chars['h'] * inner_w}{chars['tr']}")
        # 标题行
        lines.append(f"{chars['v']}{header_inner}{chars['v']}")
        # 分隔线
        lines.append(f"{chars['v']}{'─' * inner_w}{chars['v']}")
        # 正文行
        body_lines = body.split("\n") if body else [""]
        for bl in body_lines:
            # 超长截断，不足补空格
            seg = bl[:inner_w].ljust(inner_w)
            lines.append(f"{chars['v']}{seg}{chars['v']}")
        # 底边
        lines.append(f"{chars['bl']}{chars['h'] * inner_w}{chars['br']}")
        return lines

    def render_plain(
        self,
        bubble_type: str,
        title: str | None = None,
        body: str = "",
        width: int = 40,
    ) -> str:
        """渲染弹窗为单字符串（用换行连接）。"""
        return "\n".join(self.render(bubble_type, title, body, width))


# ============== 面板容器 ==============

# 面板分类
PANEL_CATEGORIES = (
    "core",  # 核心：调度/任务/排行榜/成就
    "monitor",  # 监控：梦境/安全/Git/模型路由
    "test",  # 测试：单元/集成/规范
    "art",  # 美术：素材预览
    "security",  # 安全：审计/密钥
    "ops",  # 运维：部署/告警
    "data",  # 数据：向量库/统计
)


@dataclass
class PanelSpec:
    """面板规格。"""

    type: str  # 唯一类型名
    title: str  # 默认标题
    category: str  # PANEL_CATEGORIES 之一
    icon: str  # 像素图标


# 32 类细分功能面板预设（8 基础 + 24 拓展）
_PANEL_PRESETS: list[PanelSpec] = [
    # ---- core 核心（8）----
    PanelSpec("schedule_board", "调度看板", "core", "📋"),
    PanelSpec("task_list", "任务列表", "core", "📝"),
    PanelSpec("leaderboard", "排行榜", "core", "🏆"),
    PanelSpec("achievement_wall", "成就墙", "core", "🎖"),
    PanelSpec("reward_summary", "奖惩汇总", "core", "🪙"),
    PanelSpec("agent_status", "员工状态", "core", "🐾"),
    PanelSpec("token_stats", "Token 统计", "core", "📊"),
    PanelSpec("cost_report", "成本报表", "core", "💰"),
    # ---- monitor 监控（6）----
    PanelSpec("dream_view", "梦境推演", "monitor", "💭"),
    PanelSpec("security_log", "安全日志", "monitor", "🛡"),
    PanelSpec("gitops_panel", "GitOps 操作", "monitor", "📦"),
    PanelSpec("model_route", "模型路由监控", "monitor", "🤖"),
    PanelSpec("event_bus", "事件总线", "monitor", "📡"),
    PanelSpec("alert_center", "告警中心", "monitor", "🚨"),
    # ---- test 测试（4）----
    PanelSpec("unit_test_report", "单元测试报表", "test", "✓"),
    PanelSpec("integration_test", "集成测试", "test", "🔗"),
    PanelSpec("art_spec_check", "美术规范校验", "test", "🎨"),
    PanelSpec("commit_lint", "提交规范校验", "test", "📏"),
    # ---- art 美术（3）----
    PanelSpec("asset_preview", "美术素材预览", "art", "🖼"),
    PanelSpec("sprite_browser", "精灵图浏览", "art", "👽"),
    PanelSpec("palette_picker", "色板选择器", "art", "🌈"),
    # ---- security 安全（3）----
    PanelSpec("audit_log", "审计日志", "security", "📜"),
    PanelSpec("secret_manager", "密钥管理", "security", "🔑"),
    PanelSpec("vuln_scan", "漏洞扫描", "security", "🐛"),
    # ---- ops 运维（4）----
    PanelSpec("deploy_snapshot", "部署快照", "ops", "📸"),
    PanelSpec("service_health", "服务健康", "ops", "❤"),
    PanelSpec("log_stream", "日志流", "ops", "📃"),
    PanelSpec("metrics_dashboard", "指标面板", "ops", "📈"),
    # ---- data 数据（4）----
    PanelSpec("vector_search", "向量库检索", "data", "🔎"),
    PanelSpec("rag_browser", "RAG 浏览", "data", "📚"),
    PanelSpec("file_diff", "文件修改 Diff", "data", "📝"),
    PanelSpec("kpi_detail", "岗位 KPI 明细", "data", "🎯"),
]


class PanelRegistry:
    """面板类型注册表。

    预置 32 类面板，支持自定义注册。对标成就系统批量扩展逻辑。
    """

    def __init__(self) -> None:
        self._panels: dict[str, PanelSpec] = {p.type: p for p in _PANEL_PRESETS}

    def get(self, panel_type: str) -> PanelSpec:
        if panel_type not in self._panels:
            raise ValueError(
                f"未知面板类型: {panel_type}（可选: {self.list_types()[:5]}...）"
            )
        return self._panels[panel_type]

    def list_types(self) -> list[str]:
        return sorted(self._panels.keys())

    def list_by_category(self, category: str) -> list[str]:
        return sorted(t for t, p in self._panels.items() if p.category == category)

    def register(self, spec: PanelSpec) -> None:
        self._panels[spec.type] = spec

    def count(self) -> int:
        return len(self._panels)


class PanelContainer:
    """通用模块化面板容器。

    一套容器代码跨端渲染：标题栏 + 边框 + 内容区。
    用法：
        container = PanelContainer(panel_spec, width=50, height=10)
        lines = container.render(["行1", "行2"])
    """

    def __init__(
        self,
        spec: PanelSpec,
        width: int = 50,
        height: int = 10,
        border_style: str = "single",
    ) -> None:
        self.spec = spec
        self.width = max(10, width)
        self.height = max(5, height)
        self.border_style = border_style

    def _chars(self) -> dict[str, str]:
        return BORDER_CHARS.get(self.border_style, BORDER_CHARS["single"])

    def render_header(self) -> str:
        """渲染标题行（不含边框）。"""
        return f"{self.spec.icon} {self.spec.title}"

    def render(self, content_lines: list[str]) -> list[str]:
        """渲染完整面板。"""
        chars = self._chars()
        inner_w = self.width - 2
        lines: list[str] = []

        # 顶边
        lines.append(f"{chars['tl']}{chars['h'] * inner_w}{chars['tr']}")
        # 标题行
        header = self.render_header()[:inner_w].ljust(inner_w)
        lines.append(f"{chars['v']}{header}{chars['v']}")
        # 分隔线
        lines.append(f"{chars['v']}{'─' * inner_w}{chars['v']}")

        # 内容区（高度 - 4：顶边+标题+分隔+底边）
        content_h = self.height - 4
        for i in range(content_h):
            text = content_lines[i] if i < len(content_lines) else ""
            seg = text[:inner_w].ljust(inner_w)
            lines.append(f"{chars['v']}{seg}{chars['v']}")

        # 底边
        lines.append(f"{chars['bl']}{chars['h'] * inner_w}{chars['br']}")
        return lines


# ============== 快捷键交互 ==============


@dataclass
class KeyBinding:
    """快捷键绑定。"""

    key: str  # 按键（如 "q"）
    action: str  # 动作描述
    group: str  # 功能分组


# 默认快捷键绑定（按功能分组）
_DEFAULT_BINDINGS: list[KeyBinding] = [
    # 全局
    KeyBinding("q", "退出", "global"),
    KeyBinding("r", "刷新", "global"),
    KeyBinding("h", "帮助", "global"),
    KeyBinding("?", "快捷键面板", "global"),
    # 排行榜
    KeyBinding("1", "综合排序", "leaderboard"),
    KeyBinding("2", "金币排序", "leaderboard"),
    KeyBinding("3", "成就排序", "leaderboard"),
    # 任务
    KeyBinding("t", "触发测试任务", "task"),
    KeyBinding("n", "新建任务", "task"),
    KeyBinding("c", "取消任务", "task"),
    # 导航
    KeyBinding("Tab", "切换面板", "navigation"),
    KeyBinding("↑", "上移", "navigation"),
    KeyBinding("↓", "下移", "navigation"),
    KeyBinding("←", "左移", "navigation"),
    KeyBinding("→", "右移", "navigation"),
    # 主题
    KeyBinding("T", "切换主题", "theme"),
    KeyBinding("B", "亮度自适应", "theme"),
]


class KeyBindingRegistry:
    """快捷键绑定注册表。"""

    def __init__(self) -> None:
        self._bindings: list[KeyBinding] = list(_DEFAULT_BINDINGS)

    def list_groups(self) -> list[str]:
        """所有分组。"""
        seen: list[str] = []
        for b in self._bindings:
            if b.group not in seen:
                seen.append(b.group)
        return seen

    def list_by_group(self, group: str) -> list[KeyBinding]:
        return [b for b in self._bindings if b.group == group]

    def get(self, key: str) -> KeyBinding | None:
        """按键查绑定（大小写敏感）。"""
        for b in self._bindings:
            if b.key == key:
                return b
        return None

    def register(self, binding: KeyBinding) -> None:
        """注册绑定（同 key 覆盖）。"""
        self._bindings = [b for b in self._bindings if b.key != binding.key]
        self._bindings.append(binding)

    def all(self) -> list[KeyBinding]:
        return list(self._bindings)


class ShortcutHintPanel:
    """快捷键提示像素面板。

    渲染分组快捷键提示，支持选中高亮。
    """

    # 高亮包裹字符
    HIGHLIGHT_PREFIX = "【"
    HIGHLIGHT_SUFFIX = "】"

    def __init__(self, registry: KeyBindingRegistry | None = None) -> None:
        self._registry = registry or KeyBindingRegistry()

    def render(self, group: str | None = None, width: int = 40) -> list[str]:
        """渲染快捷键提示面板。

        Args:
            group: 指定分组（None 渲染全部）。
            width: 面板宽度。
        """
        chars = BORDER_CHARS["single"]
        inner_w = width - 2
        lines: list[str] = []
        lines.append(f"{chars['tl']}{chars['h'] * inner_w}{chars['tr']}")

        title = "快捷键"
        if group:
            title += f"[{group}]"
        lines.append(f"{chars['v']}{title[:inner_w].ljust(inner_w)}{chars['v']}")
        lines.append(f"{chars['v']}{'─' * inner_w}{chars['v']}")

        groups = [group] if group else self._registry.list_groups()
        for g in groups:
            # 分组标题行
            gheader = f" [{g}] ".center(inner_w, " ")
            lines.append(f"{chars['v']}{gheader}{chars['v']}")
            for b in self._registry.list_by_group(g):
                line = f"  {b.key:<6} {b.action}"
                lines.append(f"{chars['v']}{line[:inner_w].ljust(inner_w)}{chars['v']}")

        lines.append(f"{chars['bl']}{chars['h'] * inner_w}{chars['br']}")
        return lines

    def render_highlight(self, key: str) -> str:
        """渲染选中按键的高亮文本。"""
        return f"{self.HIGHLIGHT_PREFIX}{key}{self.HIGHLIGHT_SUFFIX}"


# ============== 组件生命周期基类 ==============


class Component:
    """UI 组件基类，提供 render / on_click / on_hover 生命周期。

    所有自定义组件继承此类并实现抽象方法。
    """

    def __init__(
        self,
        component_id: str,
        x: int = 0,
        y: int = 0,
        width: int = 10,
        height: int = 3,
    ) -> None:
        self.id = component_id
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self._visible = True
        self._enabled = True
        self._hovered = False
        self._parent: Component | None = None
        self._children: list[Component] = []

    def render(self) -> list[str]:
        """渲染组件内容，子类覆盖。"""
        return []

    def on_click(self, x: int, y: int) -> bool:
        """点击事件，返回 True 表示已消费。"""
        return False

    def on_hover(self, x: int, y: int) -> None:
        """悬停事件。"""
        self._hovered = True

    def on_leave(self) -> None:
        """离开事件。"""
        self._hovered = False

    def add_child(self, child: Component) -> None:
        child._parent = self
        self._children.append(child)

    def remove_child(self, child_id: str) -> bool:
        for i, c in enumerate(self._children):
            if c.id == child_id:
                self._children.pop(i)
                return True
        return False

    def find_child(self, child_id: str) -> Any | None:
        for c in self._children:
            if c.id == child_id:
                return c
        return None

    @property
    def children(self) -> list[Any]:
        return list(self._children)

    @property
    def visible(self) -> bool:
        return self._visible

    @visible.setter
    def visible(self, v: bool) -> None:
        self._visible = v

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, v: bool) -> None:
        self._enabled = v

    @property
    def hovered(self) -> bool:
        return self._hovered


class ComponentRegistry:
    """全局组件注册表，管理组件生命周期。"""

    def __init__(self) -> None:
        self._components: dict[str, Component] = {}

    def register(self, component: Component) -> None:
        self._components[component.id] = component

    def unregister(self, component_id: str) -> bool:
        return self._components.pop(component_id, None) is not None

    def get(self, component_id: str) -> Component | None:
        return self._components.get(component_id)

    def list_ids(self) -> list[str]:
        return list(self._components.keys())

    def all(self) -> list[Component]:
        return list(self._components.values())

    def render_all(self) -> list[str]:
        lines: list[str] = []
        for c in self._components.values():
            if c.visible:
                lines.extend(c.render())
        return lines

    def clear(self) -> None:
        self._components.clear()

    @property
    def count(self) -> int:
        return len(self._components)

    def render_with_highlight(
        self,
        highlight_key: str | None = None,
        group: str | None = None,
        width: int = 40,
    ) -> list[str]:
        """渲染带高亮选中项的快捷键面板。"""
        chars = BORDER_CHARS["single"]
        inner_w = width - 2
        lines: list[str] = []
        lines.append(f"{chars['tl']}{chars['h'] * inner_w}{chars['tr']}")
        title = "快捷键"
        if group:
            title += f"[{group}]"
        lines.append(f"{chars['v']}{title[:inner_w].ljust(inner_w)}{chars['v']}")
        lines.append(f"{chars['v']}{'─' * inner_w}{chars['v']}")

        groups = [group] if group else self._registry.list_groups()
        for g in groups:
            gheader = f" [{g}] ".center(inner_w, " ")
            lines.append(f"{chars['v']}{gheader}{chars['v']}")
            for b in self._registry.list_by_group(g):
                key_display = (
                    self.render_highlight(b.key)
                    if highlight_key and b.key == highlight_key
                    else b.key
                )
                line = f"  {key_display:<8} {b.action}"
                lines.append(f"{chars['v']}{line[:inner_w].ljust(inner_w)}{chars['v']}")

        lines.append(f"{chars['bl']}{chars['h'] * inner_w}{chars['br']}")
        return lines
