"""BlueDeer JARVIS 智能助手：森林公司统一交互入口。

类似钢铁侠的 JARVIS，提供：
- 自然语言交互
- 智能路由到 Agent/场景
- 全场景状态查询
- 任务创建与跟踪
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from core.scene import CEOOffice
from core.task import Task, TaskStatus

logger = logging.getLogger("bluedeer.jarvis")


class IntentType(Enum):
    """用户意图类型。"""
    QUERY_STATUS = "query_status"        # 查询状态
    CREATE_TASK = "create_task"          # 创建任务
    SEARCH_KNOWLEDGE = "search_knowledge"  # 搜索知识
    HOLD_MEETING = "hold_meeting"        # 召开会议
    SEND_MESSAGE = "send_message"        # 发送消息
    START_REST = "start_rest"            # 开始休息
    UNKNOWN = "unknown"                  # 未知


@dataclass
class JARVISResponse:
    """JARVIS 响应。"""
    text: str
    intent: IntentType
    data: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    processing_time: float = 0.0


class JARVIS:
    """JARVIS 智能助手。

    森林公司统一交互入口，理解自然语言，智能路由到对应场景。
    """

    def __init__(self, scene: CEOOffice | None = None) -> None:
        self._scene = scene or CEOOffice()
        self._conversation_history: list[dict[str, str]] = []
        self._max_history = 50

    # ---- 交互入口 ----

    def process(self, text: str) -> JARVISResponse:
        """处理用户输入。"""
        start = time.time()
        intent = self._classify_intent(text)
        response = self._route(intent, text)
        response.processing_time = time.time() - start
        response.intent = intent

        # 记录对话历史
        self._conversation_history.append({"role": "user", "text": text})
        self._conversation_history.append({"role": "jarvis", "text": response.text})
        if len(self._conversation_history) > self._max_history * 2:
            self._conversation_history = self._conversation_history[-self._max_history * 2:]

        return response

    # ---- 意图分类 ----

    def _classify_intent(self, text: str) -> IntentType:
        """基于关键词的意图分类。"""
        text_lower = text.lower()

        # 查询状态
        if any(kw in text_lower for kw in ["状态", "情况", "status", "怎么样了", "当前"]):
            return IntentType.QUERY_STATUS

        # 创建任务
        if any(kw in text_lower for kw in ["创建任务", "新建", "写代码", "generate", "做个"]):
            return IntentType.CREATE_TASK

        # 搜索知识
        if any(kw in text_lower for kw in ["搜索", "查找", "资料", "search", "find", "知识"]):
            return IntentType.SEARCH_KNOWLEDGE

        # 召开会议
        if any(kw in text_lower for kw in ["开会", "会议", "meeting", "讨论"]):
            return IntentType.HOLD_MEETING

        # 发送消息
        if any(kw in text_lower for kw in ["发消息", "告诉", "通知", "say", "tell", "announce"]):
            return IntentType.SEND_MESSAGE

        # 休息
        if any(kw in text_lower for kw in ["休息", "放松", "休息一下", "rest", "break"]):
            return IntentType.START_REST

        return IntentType.UNKNOWN

    # ---- 路由 ----

    def _route(self, intent: IntentType, text: str) -> JARVISResponse:
        """路由到对应处理逻辑。"""
        if intent == IntentType.QUERY_STATUS:
            return self._handle_status_query()
        elif intent == IntentType.CREATE_TASK:
            return self._handle_create_task(text)
        elif intent == IntentType.SEARCH_KNOWLEDGE:
            return self._handle_search(text)
        elif intent == IntentType.HOLD_MEETING:
            return self._handle_meeting(text)
        elif intent == IntentType.SEND_MESSAGE:
            return self._handle_message(text)
        elif intent == IntentType.START_REST:
            return self._handle_rest(text)
        else:
            return JARVISResponse(
                text="你好，我是 BlueDeer 森林公司的 JARVIS 助手。"
                     "我可以帮你：\n"
                     "1. 查询全场景状态\n"
                     "2. 创建任务\n"
                     "3. 搜索知识库\n"
                     "4. 召开会议\n"
                     "5. 发送公告消息\n"
                     "6. 开始休息\n"
                     "请告诉我你需要什么帮助？",
                intent=intent,
                success=True,
            )

    # ---- 处理逻辑 ----

    def _handle_status_query(self) -> JARVISResponse:
        """处理状态查询。"""
        status = self._scene.status()
        return JARVISResponse(
            text=(
                f"🏢 全场景状态概览：\n"
                f"📚 资料库: {status['library']['total_entries']} 条目\n"
                f"💬 茶水间: {status['breakroom']['total_messages']} 条消息\n"
                f"🏢 办公室: {status['offices']['total_offices']} 间在线\n"
                f"    - 忙碌: {status['offices']['busy']} 间\n"
                f"    - 空闲: {status['offices']['idle']} 间\n"
                f"🧘 休息区: {status['rest_area']['unique_visitors']} 名访客"
            ),
            intent=IntentType.QUERY_STATUS,
            data=status,
        )

    def _handle_create_task(self, text: str) -> JARVISResponse:
        """处理任务创建。"""
        # 简易任务创建：提取任务类型
        task_type = "general"
        if any(kw in text for kw in ["代码", "code", "编程", "写"]):
            task_type = "code"
        elif any(kw in text for kw in ["架构", "设计", "architecture"]):
            task_type = "architecture"
        elif any(kw in text for kw in ["语音", "voice", "音频"]):
            task_type = "voice"

        return JARVISResponse(
            text=f"📋 已识别任务类型: {task_type}。"
                 f"已提交到调度队列，等待分配合适的员工处理。",
            intent=IntentType.CREATE_TASK,
            data={"task_type": task_type, "raw_text": text},
        )

    def _handle_search(self, text: str) -> JARVISResponse:
        """处理知识搜索。"""
        # 提取关键词
        keywords = text
        for kw in ["搜索", "查找", "资料", "search", "find", "知识", "关于"]:
            keywords = keywords.replace(kw, "").strip()
        if not keywords:
            keywords = text

        results = self._scene.library.search(keywords, top_k=3)
        result_text = "\n".join(
            f"- {r.title}" for r in results
        ) if results else "未找到相关结果"

        return JARVISResponse(
            text=f"🔍 搜索 \"{keywords}\" 结果：\n{result_text}",
            intent=IntentType.SEARCH_KNOWLEDGE,
            data={"query": keywords, "results": len(results)},
        )

    def _handle_meeting(self, text: str) -> JARVISResponse:
        """处理会议召开。"""
        # 提取会议主题
        topic = text
        for kw in ["开会", "会议", "meeting", "讨论", "召开"]:
            topic = topic.replace(kw, "").strip()
        if not topic:
            topic = "团队同步"

        participants = ["所有员工"]
        result = self._scene.hold_meeting(topic, participants)
        return JARVISResponse(
            text=f"📅 会议已创建: {topic}\n参会: {', '.join(participants)}\n公告已发布到茶水间",
            intent=IntentType.HOLD_MEETING,
            data=result,
        )

    def _handle_message(self, text: str) -> JARVISResponse:
        """处理消息发送。"""
        content = text
        for kw in ["发消息", "告诉", "通知", "say", "tell", "announce", "发布"]:
            content = content.replace(kw, "").strip()
        if not content:
            content = "请查收通知"

        msg_id = self._scene.breakroom.announce(content)
        return JARVISResponse(
            text=f"📢 公告已发布到茶水间",
            intent=IntentType.SEND_MESSAGE,
            data={"message_id": msg_id, "content": content},
        )

    def _handle_rest(self, text: str) -> JARVISResponse:
        """处理休息请求。"""
        session = self._scene.rest_area.start_rest("employee", duration=300.0)
        return JARVISResponse(
            text=f"🧘 休息模式已开启。你可以回顾最近的梦境记忆，放松一下。",
            intent=IntentType.START_REST,
            data={"session_id": session.session_id},
        )

    # ---- 对话历史 ----

    @property
    def history(self) -> list[dict[str, str]]:
        return list(self._conversation_history)

    def add_message(self, role: str, content: str) -> None:
        """手动添加一条消息到对话历史。"""
        self._conversation_history.append({"role": role, "text": content})
        if len(self._conversation_history) > self._max_history * 2:
            self._conversation_history = self._conversation_history[-self._max_history * 2:]

    def get_context(self, window: int = 10) -> list[dict[str, str]]:
        """获取最近 N 轮对话（每轮 user + jarvis = 2 条）。"""
        return self._conversation_history[-(window * 2):]

    def clear_history(self) -> None:
        """清空对话历史。"""
        self._conversation_history.clear()