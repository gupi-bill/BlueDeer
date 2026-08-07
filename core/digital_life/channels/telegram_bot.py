"""Telegram Bot 渠道：双向通信。

零基础读者可以这样理解：
- Telegram Bot 是一个"机器人账号"，你给它发消息，它转发给智能体；
  智能体产生消息，它代为发到你的 Telegram。
- 需要 `pip install python-telegram-bot` 才能用（不是标准库）。
- 没装这个包时，make_sender 会返回 None，MessageRouter 自动跳过。

设计要点：
1. make_sender(config) 返回 send(message_dict) 函数（推送用）
2. start_bot(config, on_user_message) 启动长轮询线程（接收用户消息）
3. 用户消息通过 on_user_message(text, chat_id) 回调传回业务层
4. 消息长度 > 4096 自动分段（Telegram 单条上限）
5. 紧急消息用 HTML <b> 加粗
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
# ruff: noqa: S110, S112

# ====================================================================
# 轻量 HTTP 调用（不依赖第三方包，直接用 Bot API HTTP 接口）
# ====================================================================


def _api_call(bot_token: str, method: str, payload: dict, timeout: float = 8.0) -> dict:
    """直接调 Telegram Bot API HTTP 接口。

    文档：https://core.telegram.org/bots/api
    """
    url = f"https://api.telegram.org/bot{bot_token}/{method}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)


# ====================================================================
# 发送消息
# ====================================================================


def _send_message(
    bot_token: str, chat_id: str, text: str, parse_mode: str = "HTML"
) -> bool:
    """发送一条消息到指定 chat_id。"""
    # Telegram 单条消息上限 4096 字符
    chunks = [text[i : i + 4000] for i in range(0, len(text), 4000)]
    ok = True
    for chunk in chunks:
        try:
            resp = _api_call(
                bot_token,
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": parse_mode,
                },
            )
            if not resp.get("ok"):
                ok = False
        except Exception:
            ok = False
    return ok


def _format_message(message: dict) -> str:
    """把标准消息 dict 格式化为 Telegram HTML 文本。"""
    sender = message.get("sender", "智能体")
    text = message.get("text", "")
    priority = (message.get("priority") or "low").lower()
    is_digest = message.get("is_digest", False)
    if is_digest:
        return f"<b>📋 BlueDeer 消息汇总</b>\n\n{text}"
    prefix = ""
    if priority == "high":
        prefix = "🚨 <b>【紧急】</b>"
    elif priority == "medium":
        prefix = "⭐ <b>【重要】</b>"
    return f"{prefix}<b>{sender}</b>\n{text}"


# ====================================================================
# 工厂：send 函数
# ====================================================================


def make_sender(config: dict):
    """工厂：返回 send(message_dict) 函数。

    Args:
        config: telegram 渠道配置 {bot_token, chat_id}
    """
    bot_token = config.get("bot_token", "")
    chat_id = str(config.get("chat_id", ""))
    if not (bot_token and chat_id):
        return None

    def _send(message: dict) -> bool:
        text = _format_message(message)

        # 异步发送
        def _worker():
            try:
                _send_message(bot_token, chat_id, text)
            except Exception:
                pass

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return True

    return _send


# ====================================================================
# 接收用户消息（长轮询线程）
# ====================================================================


class TelegramBotListener:
    """Telegram Bot 长轮询监听器。

    启动后会持续轮询 getUpdates 接口，收到用户消息时回调 on_message(text, chat_id)。
    """

    def __init__(
        self, bot_token: str, on_message: Callable[[str, str], None] | None = None
    ):
        self.bot_token = bot_token
        self.on_message = on_message
        self._offset = 0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """启动后台监听线程。"""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止监听。"""
        self._stop_event.set()

    def _run(self) -> None:
        """长轮询主循环。"""
        while not self._stop_event.is_set():
            try:
                resp = _api_call(
                    self.bot_token,
                    "getUpdates",
                    {
                        "offset": self._offset,
                        "timeout": 30,  # 长轮询 30 秒
                    },
                    timeout=35,
                )
                if not resp.get("ok"):
                    time.sleep(5)
                    continue
                for update in resp.get("result", []):
                    self._offset = update.get("update_id", 0) + 1
                    msg = update.get("message") or update.get("edited_message")
                    if not msg:
                        continue
                    text = msg.get("text", "")
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    if text and chat_id and self.on_message:
                        try:
                            self.on_message(text, chat_id)
                        except Exception:
                            pass
            except Exception:
                # 网络异常等，5 秒后重试
                time.sleep(5)


# ====================================================================
# 便捷启动函数
# ====================================================================

_listener_singleton: TelegramBotListener | None = None
_listener_lock = threading.Lock()


def start_listener(
    config: dict, on_message: Callable[[str, str], None] | None = None
) -> bool:
    """启动全局 Telegram Bot 监听器（单例）。

    Args:
        config: telegram 渠道配置 {bot_token, chat_id}
        on_message: 收到用户消息时的回调 (text, chat_id) → None

    Returns:
        True 表示已启动
    """
    global _listener_singleton
    bot_token = config.get("bot_token", "")
    if not bot_token:
        return False
    with _listener_lock:
        if _listener_singleton is not None:
            return True  # 已启动
        _listener_singleton = TelegramBotListener(bot_token, on_message)
        _listener_singleton.start()
        return True


def stop_listener() -> None:
    """停止全局监听器。"""
    global _listener_singleton
    with _listener_lock:
        if _listener_singleton is not None:
            _listener_singleton.stop()
            _listener_singleton = None
