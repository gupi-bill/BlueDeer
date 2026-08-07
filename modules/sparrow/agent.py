"""灵音雀 VoiceSparrowAgent：双形态全局状态播报员。

双形态（互不冲突，可同时启用）：
- 形态1 UI 内嵌：常驻 P6 像素沙盘，64×64 飞鸟精灵，点击弹气泡面板查询 7 大类状态
- 形态2 后台值守：纯后台进程，无 UI 也能工作，支持语音/日志/通知/终端四渠道输出

归属独立 Skill 技能包，与像素 UI、调度核心、梦境记忆完全解耦，可一键启停。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.base_agent import BaseAgent
from core.context import ContextManager
from core.event_bus import EventBus
from core.rag import RagCapable, RAGSystem
from core.task import Task, TaskResult, TaskStatus, TokenUsage
from core.tracer import Tracer
from models.router import Router
from modules.sparrow.status_center import StatusCenter, SystemSnapshot
from tools.registry import ToolRegistry
# ruff: noqa: F821

logger = logging.getLogger("bluedeer.sparrow.agent")


# ============== 双形态枚举 ==============


class SparrowMode(Enum):
    """灵音雀运行形态。"""

    UI_EMBEDDED = "ui_embedded"  # 形态1：界面内嵌
    BACKGROUND = "background"  # 形态2：后台值守
    DUAL = "dual"  # 双形态同时启用


# ============== 输出渠道 ==============


class OutputChannel(Enum):
    """灵音雀信息输出渠道（后台形态用）。"""

    VOICE = "voice"  # 语音播报
    LOG_FILE = "log_file"  # 文本日志输出
    NOTIFICATION = "notification"  # 本地通知弹窗
    TERMINAL = "terminal"  # 终端实时打印


# ============== UI 内嵌精灵 ==============


@dataclass
class SparrowSprite:
    """P6 像素沙盘内嵌精灵状态。"""

    # 64×64 飞鸟像素帧（3 帧微动效）
    frames: list[str] = field(default_factory=lambda: ["🐦", "🕊", "🦅"])
    # 当前帧索引
    current_frame: int = 0
    # 沙盘位置（坐标，由 UI 层解析）
    position_x: int = 0
    position_y: int = 0
    # 是否悬浮固定
    pinned: bool = True
    # 气泡面板是否展开
    bubble_open: bool = False
    # 当前展开的标签页（task/agents/system/security/alerts/git/router）
    active_tab: str = "task"

    def next_frame(self) -> str:
        """切换到下一帧并返回当前帧符号。"""
        self.current_frame = (self.current_frame + 1) % len(self.frames)
        return self.frames[self.current_frame]

    def current_symbol(self) -> str:
        """返回当前帧符号。"""
        return self.frames[self.current_frame]

    def open_bubble(self, tab: str = "task") -> None:
        """展开气泡面板到指定标签页。"""
        self.bubble_open = True
        self.active_tab = tab

    def close_bubble(self) -> None:
        """收起气泡面板。"""
        self.bubble_open = False

    def move(self, x: int, y: int) -> None:
        """移动精灵位置（拖拽时调用）。"""
        self.position_x = x
        self.position_y = y
        self.pinned = False


# ============== 灵音雀 Agent ==============


class VoiceSparrowAgent(BaseAgent, RagCapable):
    """灵音雀：全局状态播报员。

    双形态：
    - UI_EMBEDDED：常驻 P6 沙盘，点击弹气泡查询状态
    - BACKGROUND：纯后台，订阅全系统事件，四渠道输出
    - DUAL：同时启用两种形态

    职责：
    1. 接收查询任务（type=voice）→ 调 StatusCenter 采集 → 格式化返回
    2. 订阅 task_progress / agent_status / security_alert 等事件
    3. 后台形态下，事件触发时通过配置的输出渠道播报
    4. UI 形态下，更新精灵帧与气泡面板数据

    解耦设计：
    - 不修改任何其他 Agent 状态
    - StatusCenter 通过注入引用被动读取
    - 可通过 enabled=False 一键禁用，不影响其他员工
    """

    def __init__(
        self,
        event_bus: EventBus,
        router: Router,
        tool_registry: ToolRegistry,
        context: ContextManager,
        status_center: StatusCenter | None = None,
        mode: SparrowMode = SparrowMode.DUAL,
        output_channels: list[OutputChannel] | None = None,
        silent_mode: bool = False,
        tracer: Tracer | None = None,
        rag: RAGSystem | None = None,
        response_style: str = "default",
    ) -> None:
        super().__init__(
            agent_id="sparrow",
            role="状态播报",
            event_bus=event_bus,
            router=router,
            tool_registry=tool_registry,
            context=context,
            tracer=tracer,
            response_style=response_style,
        )
        self.bind_rag(rag)
        self._status_center = status_center or StatusCenter(
            event_bus=event_bus,
            router=router,
            tool_registry=tool_registry,
            context=context,
        )
        self._mode = mode
        self._channels = output_channels or [
            OutputChannel.LOG_FILE,
            OutputChannel.TERMINAL,
        ]
        self._silent = silent_mode  # 静默模式：仅异常推送
        self._enabled = True  # 启停开关
        self._sprite = SparrowSprite()  # UI 内嵌精灵
        self._recent_broadcasts: list[str] = []  # 最近播报记录

        # 订阅全系统事件（后台形态）
        self._subscribe_events()

    # ============== 启停控制 ==============

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        """启用灵音雀。"""
        self._enabled = True
        logger.info("灵音雀已启用")

    def disable(self) -> None:
        """禁用灵音雀（不影响其他 Agent）。"""
        self._enabled = False
        logger.info("灵音雀已禁用")

    @property
    def mode(self) -> SparrowMode:
        return self._mode

    def set_mode(self, mode: SparrowMode) -> None:
        """切换运行形态。"""
        self._mode = mode
        logger.info("灵音雀形态切换为 %s", mode.value)

    @property
    def silent_mode(self) -> bool:
        return self._silent

    def set_silent(self, silent: bool) -> None:
        """设置静默模式。"""
        self._silent = silent

    # ============== UI 形态接口 ==============

    @property
    def sprite(self) -> SparrowSprite:
        """暴露精灵对象供 UI 层渲染。"""
        return self._sprite

    def click_sprite(self, tab: str = "task") -> dict[str, Any]:
        """UI 形态：点击精灵，展开气泡面板查询指定标签页。

        Args:
            tab: task / agents / system / security / alerts / git / router
                 （task 是 task_progress 的简写，system 是 system_runtime 的简写）

        Returns:
            对应标签页的状态数据字典。
        """
        # 简写映射到 StatusCenter 类别名
        tab_alias = {
            "task": "task_progress",
            "system": "system_runtime",
        }
        category = tab_alias.get(tab, tab)
        self._sprite.open_bubble(tab)
        if not self._enabled:
            return {"disabled": True, "message": "灵音雀已禁用"}
        data = self._status_center.collect_category(category)
        # dataclass 转 dict
        if hasattr(data, "__dataclass_fields__"):
            return {k: getattr(data, k) for k in data.__dataclass_fields__}
        if isinstance(data, list):
            return {
                "items": [
                    (
                        {k: getattr(item, k) for k in item.__dataclass_fields__}
                        if hasattr(item, "__dataclass_fields__")
                        else item
                    )
                    for item in data
                ]
            }
        return {"data": data}

    def close_bubble(self) -> None:
        """UI 形态：收起气泡面板。"""
        self._sprite.close_bubble()

    def tick_animation(self) -> str:
        """UI 形态：每帧动画推进（由 UI 渲染循环调用）。"""
        return self._sprite.next_frame()

    # ============== 后台形态接口 ==============

    def get_output_channels(self) -> list[OutputChannel]:
        return list(self._channels)

    def add_channel(self, channel: OutputChannel) -> None:
        """新增输出渠道。"""
        if channel not in self._channels:
            self._channels.append(channel)

    def remove_channel(self, channel: OutputChannel) -> None:
        """移除输出渠道。"""
        if channel in self._channels:
            self._channels.remove(channel)

    @property
    def recent_broadcasts(self) -> list[str]:
        """最近播报记录（最多 100 条）。"""
        return list(self._recent_broadcasts[-100:])

    def _record_broadcast(self, message: str) -> None:
        """记录播报到历史。"""
        self._recent_broadcasts.append(message)
        if len(self._recent_broadcasts) > 100:
            self._recent_broadcasts = self._recent_broadcasts[-100:]

    def broadcast(self, message: str, force: bool = False) -> None:
        """后台形态：通过配置的渠道播报消息。

        Args:
            message: 播报内容。
            force: 是否强制播报（静默模式下也输出）。
        """
        if not self._enabled:
            return
        if self._silent and not force:
            return
        self._record_broadcast(message)
        for channel in self._channels:
            self._emit_to_channel(channel, message)

    def _emit_to_channel(self, channel: OutputChannel, message: str) -> None:
        """向单个渠道输出消息。"""
        if channel == OutputChannel.TERMINAL:
            print(f"[灵音雀] {message}")
        elif channel == OutputChannel.LOG_FILE:
            logger.info("播报: %s", message)
        elif channel == OutputChannel.VOICE:
            # 语音播报 stub（实际接 TTS 服务）
            logger.debug("语音播报（stub）: %s", message)
        elif channel == OutputChannel.NOTIFICATION:
            # 本地通知 stub
            logger.debug("本地通知（stub）: %s", message)

    # ============== 事件订阅 ==============

    def _subscribe_events(self) -> None:
        """订阅全系统事件 topic。"""
        # 任务结果
        self._bus.subscribe("harness.result", self._on_task_result)
        # 安全告警
        self._bus.subscribe("security.alert", self._on_security_alert)
        # 任务节点
        self._bus.subscribe("task.node", self._on_task_node)

    async def _on_task_result(self, message: Any) -> None:
        """任务结果事件回调。"""
        if not self._enabled:
            return
        if hasattr(message, "status"):
            status = (
                message.status.value
                if hasattr(message.status, "value")
                else str(message.status)
            )
            task_id = getattr(message, "task_id", "unknown")
            if status == "failed":
                self.broadcast(f"任务 {task_id} 失败", force=True)
            elif not self._silent:
                self.broadcast(f"任务 {task_id} 完成")

    async def _on_security_alert(self, message: Any) -> None:
        """安全告警事件回调（静默模式下也强制推送）。"""
        if not self._enabled:
            return
        content = str(message)
        self.broadcast(f"安全告警: {content}", force=True)

    async def _on_task_node(self, message: Any) -> None:
        """任务节点事件回调。"""
        if not self._enabled or self._silent:
            return
        content = str(message)
        self.broadcast(f"任务节点: {content}")

    # ============== Agent handle ==============

    async def handle(self, task: Task) -> TaskResult:
        """处理查询/播报任务。

        支持的 payload.action：
        - query：查询指定类别状态（category 字段）
        - snapshot：采集全系统快照
        - broadcast：主动播报消息（message 字段）
        - report：生成简报文本
        """
        if not self._enabled:
            return TaskResult(
                trace_id=task.trace_id,
                task_id=task.id,
                status=TaskStatus.FAILED,
                error="灵音雀已禁用",
                token_usage=TokenUsage(),
            )

        if self._tracer:
            self._tracer.span(
                task.trace_id,
                component="VoiceSparrowAgent",
                action="handle_start",
                task_id=task.id,
                mode=self._mode.value,
            )

        total_tokens = TokenUsage()

        try:
            action = task.payload.get("action", "snapshot")

            if action == "query":
                category = task.payload.get("category", "task_progress")
                data = self._status_center.collect_category(category)
                output = {
                    "action": "query",
                    "category": category,
                    "data": self._snapshot_to_dict(data),
                }
            elif action == "broadcast":
                message = task.payload.get("message", "")
                force = task.payload.get("force", False)
                self.broadcast(message, force=force)
                output = {
                    "action": "broadcast",
                    "message": message,
                    "channels": [c.value for c in self._channels],
                }
            elif action == "report":
                snapshot = self._status_center.collect()
                report = self._format_brief(snapshot)
                self.broadcast(report)
                output = {
                    "action": "report",
                    "report": report,
                    "snapshot": snapshot.to_dict(),
                }
            else:  # snapshot
                snapshot = self._status_center.collect()
                output = {
                    "action": "snapshot",
                    "snapshot": snapshot.to_dict(),
                }

            self._self_check(task, output)

            if self._tracer:
                self._tracer.span(
                    task.trace_id,
                    component="VoiceSparrowAgent",
                    action="handle_success",
                    task_id=task.id,
                )

            return TaskResult(
                trace_id=task.trace_id,
                task_id=task.id,
                status=TaskStatus.SUCCESS,
                output=output,
                token_usage=total_tokens,
            )

        except Exception as e:
            logger.exception("灵音雀处理任务 %s 失败", task.id)
            return TaskResult(
                trace_id=task.trace_id,
                task_id=task.id,
                status=TaskStatus.FAILED,
                error=str(e),
                token_usage=total_tokens,
            )

    def _snapshot_to_dict(self, data: Any) -> Any:
        """快照对象转字典。"""
        if hasattr(data, "__dataclass_fields__"):
            return {k: getattr(data, k) for k in data.__dataclass_fields__}
        if isinstance(data, list):
            return [self._snapshot_to_dict(item) for item in data]
        return data

    def _format_brief(self, snapshot: SystemSnapshot) -> str:
        """格式化轻量简报文本。"""
        lines = [
            f"【灵音雀巡检简报 @ {snapshot.collected_at:.0f}】",
            (f"任务进度: {snapshot.task_progress.completed_steps}/"
            f"{snapshot.task_progress.total_steps}"),
            f"在岗员工: {len(snapshot.agents)} 名",
            f"高危拦截: {snapshot.system_runtime.hazardous_blocked_count} 次",
        ]
        # 预警
        alerts = snapshot.alerts
        alert_msgs = []
        if alerts.token_overrun:
            alert_msgs.append("Token超限")
        if alerts.memory_high:
            alert_msgs.append("内存过高")
        if alerts.agent_stuck:
            alert_msgs.append(f"员工卡死:{','.join(alerts.agent_stuck)}")
        if alerts.nightmare_dream:
            alert_msgs.append("噩梦梦境")
        if alerts.secret_plaintext_risk:
            alert_msgs.append("密钥明文")
        if alerts.dependency_conflict:
            alert_msgs.append("依赖冲突")
        if alert_msgs:
            lines.append(f"预警: {' | '.join(alert_msgs)}")
        else:
            lines.append("预警: 无")
        return "\n".join(lines)

    def _build_prompt(self, task: Task) -> str:
        """构建提示词（灵音雀以状态查询为主，LLM 仅辅助总结）。"""
        action = task.payload.get("action", "snapshot")
        ctx = self._context.get_context(self.agent_id, task)
        ctx_str = ", ".join(f"{k}={v}" for k, v in ctx.items()) if ctx else "无"
        few_shot = self.build_rag_fewshot(f"灵音雀 {action}")
        return (
            f"你是灵音雀，BlueDeer 森林公司的全局状态播报员。\n"
            f"请处理 {action} 请求：\n\n"
            f"任务负载: {task.payload}\n"
            f"项目上下文: {ctx_str}\n"
            f"{few_shot}\n"
            f"要求：\n"
            f"1. 调用 StatusCenter 采集对应类别状态\n"
            f"2. 格式化为易读文本\n"
            f"3. 通过配置的输出渠道播报"
        )

    def _self_check(self, task: Task, output: dict[str, Any]) -> None:
        """校验输出完整性。"""
        if not output:
            raise ValueError("自检失败：输出为空")
        if "action" not in output:
            raise ValueError("自检失败：缺少 action 字段")
        action = output["action"]
        if action == "query" and "data" not in output:
            raise ValueError("自检失败：query 动作缺少 data 字段")
        if action == "snapshot" and "snapshot" not in output:
            raise ValueError("自检失败：snapshot 动作缺少 snapshot 字段")
        if action == "broadcast" and "message" not in output:
            raise ValueError("自检失败：broadcast 动作缺少 message 字段")
        if action == "report" and "report" not in output:
            raise ValueError("自检失败：report 动作缺少 report 字段")


# ============== 消息队列 ==============


@dataclass
class QueuedMessage:
    """排队待播报的消息。"""

    content: str
    priority: int = 0  # 0=normal, 1=high, 2=urgent
    timestamp: float = 0.0
    channel: OutputChannel = OutputChannel.TERMINAL


class MessageQueue:
    """带优先级排序的消息队列。"""

    def __init__(self) -> None:
        self._messages: list[QueuedMessage] = []

    def enqueue(self, msg: QueuedMessage) -> None:
        self._messages.append(msg)
        self._messages.sort(key=lambda m: (-m.priority, m.timestamp))

    def dequeue(self) -> QueuedMessage | None:
        if not self._messages:
            return None
        return self._messages.pop(0)

    def peek(self) -> QueuedMessage | None:
        if not self._messages:
            return None
        return self._messages[0]

    def clear(self) -> None:
        self._messages.clear()

    @property
    def count(self) -> int:
        return len(self._messages)

    def drain_to(self, handler: Any) -> int:
        count = 0
        while self._messages:
            msg = self.dequeue()
            if msg:
                handler(msg)
                count += 1
        return count


# ============== 状态追踪 ==============


@dataclass
class AgentStatusRecord:
    agent_id: str
    status: str
    last_seen: float = 0.0
    task_count: int = 0
    error_count: int = 0


class StatusTracker:
    """追踪员工状态变更与心跳。"""

    def __init__(self) -> None:
        self._agents: dict[str, AgentStatusRecord] = {}
        self._history: list[dict[str, Any]] = []

    def update(self, agent_id: str, status: str) -> None:
        now = time.time()
        if agent_id in self._agents:
            record = self._agents[agent_id]
            if record.status != status:
                self._history.append(
                    {
                        "agent_id": agent_id,
                        "from": record.status,
                        "to": status,
                        "at": now,
                    }
                )
            record.status = status
            record.last_seen = now
            record.task_count += 1
        else:
            self._agents[agent_id] = AgentStatusRecord(
                agent_id=agent_id,
                status=status,
                last_seen=now,
            )

    def get(self, agent_id: str) -> AgentStatusRecord | None:
        return self._agents.get(agent_id)

    def record_error(self, agent_id: str) -> None:
        if agent_id in self._agents:
            self._agents[agent_id].error_count += 1

    @property
    def all_statuses(self) -> dict[str, str]:
        return {aid: r.status for aid, r in self._agents.items()}

    @property
    def recent_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self._history[-limit:])

    def agents_by_status(self, status: str) -> list[str]:
        return [aid for aid, r in self._agents.items() if r.status == status]
