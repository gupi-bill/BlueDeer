"""任务链路发光图谱：TraceID 串联 + 报错脉冲 + 负载亮度。

融合项目：#4 GLOW、#12 ruflo、#14 opencode、#18 agent-glow-map、#48 flow-glow/branch

能力：
1. 任务节点发光：在岗绿光、运行中流动光、报错红光脉冲、完成淡出
2. 链路连线流光：TraceID 串联节点，耗时越长光晕越亮
3. 负载亮度映射：CPU/Token 占用越高光晕越强，过载红光预警
4. 多分支条件工作流：分支判断三色光晕、循环节点循环光、超时橙光
5. 链路图谱导出 MD 报表
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from modules.glow.color_downgrade import (
    RGB,
    ColorDowngradeRenderer,
    GlowLayer,
)

# ============== 任务节点状态 ==============


class NodeGlowState(Enum):
    """任务节点 6 状态。"""

    PENDING = "pending"  # 待执行：灰光
    RUNNING = "running"  # 运行中：流动绿光
    SUCCESS = "success"  # 成功：淡出绿光
    FAILED = "failed"  # 失败：红光脉冲
    TIMEOUT = "timeout"  # 超时：橙光闪烁
    BLOCKED = "blocked"  # 阻塞：紫光常亮


# 节点状态 → 发光参数
_NODE_STATE_CONFIG: dict[NodeGlowState, NodeGlowParams] = {}


@dataclass
class NodeGlowParams:
    """节点发光参数。"""

    color: RGB
    layer: GlowLayer
    blink: bool = False
    pulse_frames: int = 1
    brightness: float = 1.0
    icon: str = "○"


_NODE_STATE_CONFIG = {
    NodeGlowState.PENDING: NodeGlowParams(
        color=RGB(120, 120, 120),
        layer=GlowLayer.BACKGROUND,
        brightness=0.6,
        icon="○",
    ),
    NodeGlowState.RUNNING: NodeGlowParams(
        color=RGB(80, 200, 100),
        layer=GlowLayer.MIDGROUND,
        brightness=1.0,
        pulse_frames=3,
        icon="◐",
    ),
    NodeGlowState.SUCCESS: NodeGlowParams(
        color=RGB(100, 220, 120),
        layer=GlowLayer.MIDGROUND,
        brightness=0.7,
        icon="●",
    ),
    NodeGlowState.FAILED: NodeGlowParams(
        color=RGB(255, 60, 60),
        layer=GlowLayer.FOREGROUND,
        brightness=1.4,
        blink=True,
        pulse_frames=4,
        icon="✗",
    ),
    NodeGlowState.TIMEOUT: NodeGlowParams(
        color=RGB(255, 160, 40),
        layer=GlowLayer.FOREGROUND,
        brightness=1.2,
        blink=True,
        pulse_frames=3,
        icon="⏱",
    ),
    NodeGlowState.BLOCKED: NodeGlowParams(
        color=RGB(180, 80, 200),
        layer=GlowLayer.MIDGROUND,
        brightness=1.0,
        icon="⛔",
    ),
}


# ============== 分支节点 ==============


class BranchGlowType(Enum):
    """分支节点 4 类型。"""

    DECISION = "decision"  # 判断：三色光晕区分路径
    LOOP = "loop"  # 循环：循环流动光
    MERGE = "merge"  # 合并：渐变融合光
    PARALLEL = "parallel"  # 并行：多光同步


_BRANCH_COLOR: dict[BranchGlowType, RGB] = {
    BranchGlowType.DECISION: RGB(255, 200, 80),  # 黄
    BranchGlowType.LOOP: RGB(80, 180, 240),  # 蓝
    BranchGlowType.MERGE: RGB(180, 240, 100),  # 绿黄
    BranchGlowType.PARALLEL: RGB(240, 180, 220),  # 粉
}


# ============== 任务节点 ==============


@dataclass
class TaskNode:
    """任务链路节点。"""

    node_id: str  # 节点 ID（通常含 TraceID）
    trace_id: str = ""  # 所属 TraceID
    agent_id: str = ""  # 执行 Agent
    label: str = ""  # 节点标签
    state: NodeGlowState = NodeGlowState.PENDING
    duration_ms: int = 0  # 耗时（毫秒）
    load: float = 0.0  # 负载 0-1（CPU/Token 占用）
    branch_type: BranchGlowType | None = None  # 分支类型（None 普通节点）
    error: str = ""  # 错误信息


@dataclass
class TaskEdge:
    """任务链路连线。"""

    from_node: str
    to_node: str
    trace_id: str = ""
    weight: float = 1.0  # 权重（耗时越长权重越高）
    active: bool = False  # 是否活跃流转中


@dataclass
class TaskGraph:
    """任务链路图谱。"""

    nodes: list[TaskNode] = field(default_factory=list)
    edges: list[TaskEdge] = field(default_factory=list)

    def add_node(self, node: TaskNode) -> None:
        self.nodes.append(node)

    def add_edge(self, edge: TaskEdge) -> None:
        self.edges.append(edge)

    def find_node(self, node_id: str) -> TaskNode | None:
        for n in self.nodes:
            if n.node_id == node_id:
                return n
        return None

    def nodes_by_trace(self, trace_id: str) -> list[TaskNode]:
        """按 TraceID 串联节点。"""
        return [n for n in self.nodes if n.trace_id == trace_id]

    def edges_by_trace(self, trace_id: str) -> list[TaskEdge]:
        return [e for e in self.edges if e.trace_id == trace_id]


# ============== 负载亮度映射 ==============


def load_to_brightness(load: float) -> float:
    """负载 → 亮度系数。

    - 0.0-0.5：0.6-1.0 线性
    - 0.5-0.8：1.0-1.3 线性
    - 0.8-1.0：1.3-1.5 线性 + 红光预警
    """
    if load <= 0.5:
        return 0.6 + 0.8 * load
    if load <= 0.8:
        return 1.0 + (load - 0.5) * 1.0
    return 1.3 + (load - 0.8) * 1.0


def load_to_color(load: float, base_color: RGB) -> RGB:
    """负载越高颜色越偏红（过载预警）。"""
    if load < 0.8:
        return base_color
    # 过载混合红色
    mix = (load - 0.8) / 0.2  # 0-1
    return RGB(
        r=min(255, int(base_color.r + (255 - base_color.r) * mix)),
        g=int(base_color.g * (1 - mix * 0.5)),
        b=int(base_color.b * (1 - mix * 0.5)),
    )


# ============== 任务链路光图渲染器 ==============


class TaskGraphGlowRenderer:
    """任务链路发光图谱渲染器。

    职责：
    1. 渲染单节点发光（按状态 + 负载）
    2. 渲染连线流光（按 TraceID 串联）
    3. 渲染整图 MD 报表
    4. 输出报错节点脉冲动画
    """

    def __init__(self, renderer: ColorDowngradeRenderer | None = None) -> None:
        self._renderer = renderer or ColorDowngradeRenderer()

    def render_node(self, node: TaskNode) -> str:
        """渲染单节点发光文本。"""
        params = _NODE_STATE_CONFIG.get(
            node.state,
            _NODE_STATE_CONFIG[NodeGlowState.PENDING],
        )
        # 分支节点用分支色
        if node.branch_type is not None:
            color = _BRANCH_COLOR[node.branch_type]
        else:
            color = params.color
        # 应用负载亮度 + 过载混色
        brightness = load_to_brightness(node.load) * params.brightness
        color = load_to_color(node.load, color)
        adjusted = color.adjust_brightness(min(1.5, brightness))
        icon = params.icon
        label = node.label or node.node_id
        return f"{icon} {self._renderer.render_glow(label, adjusted, params.layer, params.blink)}"

    def render_node_with_meta(self, node: TaskNode) -> str:
        """渲染节点 + 元信息（Agent/耗时/负载）。"""
        base = self.render_node(node)
        meta_parts = []
        if node.agent_id:
            meta_parts.append(f"agent={node.agent_id}")
        if node.duration_ms > 0:
            meta_parts.append(f"{node.duration_ms}ms")
        if node.load > 0:
            meta_parts.append(f"load={node.load:.0%}")
        meta = " ".join(meta_parts)
        return f"{base} [{meta}]" if meta else base

    def render_edge(self, edge: TaskEdge, graph: TaskGraph) -> str:
        """渲染连线（含权重亮度）。"""
        from_n = graph.find_node(edge.from_node)
        to_n = graph.find_node(edge.to_node)
        from_label = from_n.label if from_n else edge.from_node
        to_label = to_n.label if to_n else edge.to_node
        # 权重越高连线越亮
        color = RGB(120, 180, 240).adjust_brightness(min(1.5, 0.5 + edge.weight))
        if edge.active:
            arrow = self._renderer.render_glow("→", color, GlowLayer.FOREGROUND)
        else:
            arrow = self._renderer.render_glow("·", color, GlowLayer.BACKGROUND)
        return f"{from_label} {arrow} {to_label}"

    def render_trace_chain(self, graph: TaskGraph, trace_id: str) -> list[str]:
        """按 TraceID 串联渲染整条链路。"""
        nodes = graph.nodes_by_trace(trace_id)
        if not nodes:
            return [f"(TraceID {trace_id} 无节点)"]
        lines = [
            self._renderer.render_glow(
                f"🔗 TraceID: {trace_id}",
                RGB(120, 200, 240),
                GlowLayer.FOREGROUND,
            ),
        ]
        for n in nodes:
            lines.append(f"  {self.render_node_with_meta(n)}")
        return lines

    def render_failed_pulse(self, node: TaskNode) -> list[str]:
        """渲染失败节点脉冲动画帧。"""
        if node.state != NodeGlowState.FAILED:
            return [self.render_node(node)]
        params = _NODE_STATE_CONFIG[NodeGlowState.FAILED]
        frames_count = max(1, params.pulse_frames)
        result = []
        label = node.label or node.node_id
        for i in range(frames_count):
            factor = 0.6 + 0.4 * (i / max(1, frames_count - 1))
            adjusted = params.color.adjust_brightness(factor * params.brightness)
            result.append(
                self._renderer.render_glow(
                    f"{params.icon} {label}",
                    adjusted,
                    params.layer,
                    blink=(i == 0 and params.blink),
                )
            )
        return result

    def render_graph_md(self, graph: TaskGraph) -> str:
        """渲染整图 Markdown 报表。"""
        lines = ["# 任务链路发光图谱", ""]
        # 按 TraceID 分组
        trace_ids: list[str] = []
        for n in graph.nodes:
            if n.trace_id and n.trace_id not in trace_ids:
                trace_ids.append(n.trace_id)
        if not trace_ids:
            lines.append("(无任务节点)")
            return "\n".join(lines)
        for tid in trace_ids:
            lines.append(f"## TraceID: {tid}")
            lines.append("")
            lines.append("| 节点 | 状态 | Agent | 耗时 | 负载 | 分支 |")
            lines.append("|---|---|---|---|---|---|")
            for n in graph.nodes_by_trace(tid):
                branch = n.branch_type.value if n.branch_type else "-"
                lines.append(
                    f"| {n.label or n.node_id} | {n.state.value} | "
                    f"{n.agent_id or '-'} | {n.duration_ms}ms | "
                    f"{n.load:.0%} | {branch} |"
                )
            lines.append("")
            # 连线
            edges = graph.edges_by_trace(tid)
            if edges:
                lines.append("### 流转连线")
                lines.append("")
                for e in edges:
                    from_n = graph.find_node(e.from_node)
                    to_n = graph.find_node(e.to_node)
                    from_label = from_n.label if from_n else e.from_node
                    to_label = to_n.label if to_n else e.to_node
                    active = "▶" if e.active else "·"
                    lines.append(
                        f"- {from_label} {active}→ {to_label} (权重 {e.weight:.1f})"
                    )
                lines.append("")
        # 失败节点统计
        failed = [n for n in graph.nodes if n.state == NodeGlowState.FAILED]
        if failed:
            lines.append("## ❗ 失败节点")
            lines.append("")
            for n in failed:
                lines.append(f"- {n.label or n.node_id}: {n.error or '(无错误信息)'}")
            lines.append("")
        return "\n".join(lines)

    def list_node_states(self) -> list[NodeGlowState]:
        """列出 6 个节点状态。"""
        return list(NodeGlowState)

    def list_branch_types(self) -> list[BranchGlowType]:
        """列出 4 个分支类型。"""
        return list(BranchGlowType)

    def render_edge_colored(
        self,
        edge: TaskEdge,
        graph: TaskGraph,
        edge_colors: dict[str, RGB] | None = None,
    ) -> str:
        """渲染带颜色的连线（按 TraceID 或自定义着色）。"""
        color = (
            edge_colors.get(edge.trace_id, RGB(120, 180, 240))
            if edge_colors
            else RGB(120, 180, 240)
        )
        from_n = graph.find_node(edge.from_node)
        to_n = graph.find_node(edge.to_node)
        from_label = from_n.label if from_n else edge.from_node
        to_label = to_n.label if to_n else edge.to_node
        brightness = min(1.5, 0.5 + edge.weight)
        color = color.adjust_brightness(brightness)
        arrow = "→" if edge.active else "·"
        return f"{from_label} {self._renderer.render_glow(arrow, color, GlowLayer.FOREGROUND)} {to_label}"


def trace_progress(nodes: list[TaskNode]) -> dict[str, Any]:
    """统计链路节点完成进度。"""
    total = len(nodes)
    done = sum(
        1
        for n in nodes
        if n.state
        in (NodeGlowState.SUCCESS, NodeGlowState.FAILED, NodeGlowState.TIMEOUT)
    )
    running = sum(1 for n in nodes if n.state == NodeGlowState.RUNNING)
    failed = sum(1 for n in nodes if n.state == NodeGlowState.FAILED)
    return {
        "total": total,
        "completed": done,
        "running": running,
        "failed": failed,
        "progress": done / total if total else 1.0,
    }
