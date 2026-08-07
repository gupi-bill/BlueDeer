"""消息路由层：所有主动消息的统一分发中心。

零基础读者可以这样理解：
- 智能体产生一条消息 → push 到 Environment 队列（前端 SSE 拉取）→ 同时交给 MessageRouter。
- MessageRouter 看消息优先级（low/medium/high）和用户在 integrations_config.json 里配的渠道，
  决定要不要再发到桌面通知、微信、邮件等外部渠道。
- 紧急消息（high）会"广撒网"，普通消息（low）只走管控台 + 每小时汇总。
- 免打扰时段（quiet_hours）内，除 high 优先级外都静默。

设计要点：
1. 单例（Borg 风格），全局共享配置 + digest 缓冲。
2. 渠道发送失败不影响其他渠道，全部 try/except 兜底。
3. 普通消息走"小时汇总"：digest 字典按渠道缓存，到点一次性发送。
4. 配置文件改动会被自动感知（每次发送前重读 mtime）。
"""

from __future__ import annotations

import datetime
import json
import os
import threading
import time
from typing import Any

from typing_extensions import Self

# ruff: noqa: S110, S112


# ====================================================================
# 优先级 → 路由 key 映射
# ====================================================================
# high  → urgent（警报、死亡）
# medium → important（健康危机、关系里程碑、退休愿望）
# low    → normal（工作完成、早安、分享等）
# 低于 low 的视为 social（仅管控台）
def _priority_to_route(priority: str) -> str:
    """把消息 priority（low/medium/high）映射到 message_routing 的 key。"""
    p = (priority or "low").lower()
    if p == "high":
        return "urgent"
    if p == "medium":
        return "important"
    return "normal"


# ====================================================================
# 配置加载（带热重载）
# ====================================================================

DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "integrations_config.json",
)


def load_config(path: str = DEFAULT_CONFIG_PATH) -> dict:
    """加载 integrations_config.json。文件不存在返回最小默认配置。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "channels": {"desktop_notify": {"enabled": True}},
            "quiet_hours": {"enabled": False, "start": "22:00", "end": "08:00"},
            "message_routing": {
                "urgent": ["desktop_notify"],
                "important": ["desktop_notify"],
                "normal": ["desktop_notify"],
                "social": [],
            },
            "digest": {"enabled": True, "interval_hours": 1},
        }


# ====================================================================
# MessageRouter 单例
# ====================================================================


class MessageRouter:
    """消息路由器（单例）。

    使用方式：
        router = MessageRouter()  # 任意位置拿到同一个实例
        router.dispatch({
            "sender": "忧郁鹿", "sender_species": "deer",
            "text": "...", "category": "work_done", "priority": "low",
        })
    """

    _instance: MessageRouter | None = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs) -> Self:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._init_once()
                    cls._instance = obj
        return cls._instance

    def _init_once(self) -> None:
        """单例首次创建时初始化。"""
        self._config_path = DEFAULT_CONFIG_PATH
        self._config: dict = load_config(self._config_path)
        self._config_mtime: float = 0.0
        self._lock = threading.RLock()
        # digest 缓冲：{渠道名: [{"sender","text","time","category"}, ...]}
        # 每个渠道独立缓冲，到点（默认 1 小时）一次性发送。
        self._digest_buffer: dict[str, list[dict]] = {}
        # 上次 digest 发送时间戳
        self._last_digest_ts: float = 0.0
        # 已启用的渠道 send 函数（懒加载，避免 import 时报错）
        self._channel_senders: dict[str, Any] = {}
        self._channels_loaded = False

    # ---------------- 配置热重载 ----------------

    def _maybe_reload_config(self) -> None:
        """如果配置文件 mtime 变了，重新加载。"""
        try:
            mtime = os.path.getmtime(self._config_path)
        except OSError:
            return
        if mtime != self._config_mtime:
            self._config = load_config(self._config_path)
            self._config_mtime = mtime

    # ---------------- 渠道懒加载 ----------------

    def _ensure_channels_loaded(self) -> None:
        """懒加载渠道发送函数（仅启用时才 import，避免无谓依赖）。"""
        if self._channels_loaded:
            return
        self._channels_loaded = True
        channels_cfg = self._config.get("channels", {})
        senders: dict[str, Any] = {}
        # 桌面通知（默认启用，零依赖）
        if channels_cfg.get("desktop_notify", {}).get("enabled", False):
            try:
                from core.digital_life.channels.desktop_notify import send as _send

                senders["desktop_notify"] = _send
            except Exception:
                pass
        # Webhook 类（企微/钉钉/飞书）
        for key in ("wechat_webhook", "dingtalk_webhook", "feishu_webhook"):
            ch = channels_cfg.get(key, {})
            if ch.get("enabled") and ch.get("url"):
                try:
                    from core.digital_life.channels.webhook_channel import make_sender

                    senders[key] = make_sender(key, ch)
                except Exception:
                    pass
        # Telegram Bot
        tg = channels_cfg.get("telegram", {})
        if tg.get("enabled") and tg.get("bot_token") and tg.get("chat_id"):
            try:
                from core.digital_life.channels.telegram_bot import make_sender

                senders["telegram"] = make_sender(tg)
            except Exception:
                pass
        # 邮件
        em = channels_cfg.get("email", {})
        if em.get("enabled") and em.get("smtp_host") and em.get("recipient"):
            try:
                from core.digital_life.channels.email_digest import make_sender

                senders["email"] = make_sender(em)
            except Exception:
                pass
        self._channel_senders = senders

    # ---------------- 免打扰判定 ----------------

    def _in_quiet_hours(self) -> bool:
        """当前是否在免打扰时段。"""
        qh = self._config.get("quiet_hours", {})
        if not qh.get("enabled", False):
            return False
        try:
            start = qh.get("start", "22:00")
            end = qh.get("end", "08:00")
            sh, sm = map(int, start.split(":"))
            eh, em = map(int, end.split(":"))
            now = datetime.datetime.now()
            cur_min = now.hour * 60 + now.minute
            s_min, e_min = sh * 60 + sm, eh * 60 + em
            if s_min <= e_min:
                return s_min <= cur_min < e_min
            else:
                # 跨夜（如 22:00 → 08:00）
                return cur_min >= s_min or cur_min < e_min
        except Exception:
            return False

    # ---------------- 对外主接口 ----------------

    def dispatch(self, message: dict) -> dict:
        """分发一条消息到外部渠道。

        Args:
            message: 标准消息 dict
                {
                  "sender": str, "sender_species": str,
                  "text": str, "category": str, "priority": "low"|"medium"|"high",
                  "time": float,
                }

        Returns:
            {"dispatched": [渠道名], "buffered": [渠道名], "skipped": [原因]}
        """
        self._maybe_reload_config()
        self._ensure_channels_loaded()

        priority = (message.get("priority") or "low").lower()
        route_key = _priority_to_route(priority)
        routing = self._config.get("message_routing", {})
        target_channels = routing.get(route_key, [])
        # social 类消息不外部推送
        if route_key == "social":
            return {"dispatched": [], "buffered": [], "skipped": ["social"]}

        # 免打扰时段：high 优先级穿透，其他暂存到 digest
        in_quiet = self._in_quiet_hours()
        if in_quiet and priority != "high":
            # 静默期间只入管控台（已由 Environment 队列处理），不外部推送
            return {"dispatched": [], "buffered": [], "skipped": ["quiet_hours"]}

        dispatched: list[str] = []
        buffered: list[str] = []
        digest_cfg = self._config.get("digest", {})
        digest_enabled = digest_cfg.get("enabled", True)
        # 普通/社交类消息走汇总，紧急/重要立即发
        use_digest = digest_enabled and route_key == "normal"

        for ch_name in target_channels:
            sender = self._channel_senders.get(ch_name)
            if sender is None:
                # 渠道未启用或加载失败
                continue
            if use_digest and ch_name in (
                "email",
                "wechat_webhook",
                "dingtalk_webhook",
                "feishu_webhook",
            ):
                # Webhook/邮件做汇总，避免消息轰炸
                self._digest_buffer.setdefault(ch_name, []).append(
                    {
                        "sender": message.get("sender", ""),
                        "sender_species": message.get("sender_species", ""),
                        "text": message.get("text", ""),
                        "category": message.get("category", ""),
                        "time": message.get("time", time.time()),
                    }
                )
                buffered.append(ch_name)
            else:
                # 立即发送（desktop_notify / telegram / 所有 urgent）
                try:
                    sender(
                        {
                            "sender": message.get("sender", ""),
                            "sender_species": message.get("sender_species", ""),
                            "text": message.get("text", ""),
                            "category": message.get("category", ""),
                            "priority": priority,
                            "time": message.get("time", time.time()),
                        }
                    )
                    dispatched.append(ch_name)
                except Exception:
                    pass

        return {"dispatched": dispatched, "buffered": buffered, "skipped": []}

    # ---------------- 汇总发送 ----------------

    def flush_digest(self, force: bool = False) -> dict:
        """触发 digest 缓冲发送。

        正常按 digest.interval_hours 间隔发送；force=True 时立即发送所有缓冲。

        Returns:
            {"flushed": [渠道名], "total_messages": int}
        """
        self._maybe_reload_config()
        self._ensure_channels_loaded()
        now = time.time()
        interval = self._config.get("digest", {}).get("interval_hours", 1) * 3600
        if not force and (now - self._last_digest_ts) < interval:
            return {"flushed": [], "total_messages": 0}

        with self._lock:
            buffer_snapshot = dict(self._digest_buffer)
            self._digest_buffer = {}
            self._last_digest_ts = now

        flushed: list[str] = []
        total = 0
        for ch_name, msgs in buffer_snapshot.items():
            if not msgs:
                continue
            sender = self._channel_senders.get(ch_name)
            if sender is None:
                continue
            # 邮件渠道有专门的 digest 模板；其他渠道简单拼接
            try:
                if ch_name == "email":
                    # 邮件走 daily_report 模板
                    from core.digital_life.channels.email_digest import send_digest

                    send_digest(self._config["channels"]["email"], msgs)
                else:
                    # Webhook 类：合并为一条卡片
                    summary = self._format_webhook_digest(msgs)
                    sender(
                        {
                            "sender": "BlueDeer 汇总",
                            "sender_species": "system",
                            "text": summary,
                            "category": "digest",
                            "priority": "low",
                            "time": now,
                            "is_digest": True,
                            "digest_count": len(msgs),
                        }
                    )
                flushed.append(ch_name)
                total += len(msgs)
            except Exception:
                pass
        return {"flushed": flushed, "total_messages": total}

    @staticmethod
    def _format_webhook_digest(msgs: list[dict]) -> str:
        """把多条消息合并成一条文本（用于 webhook 渠道）。"""
        if not msgs:
            return ""
        if len(msgs) == 1:
            m = msgs[0]
            return f"【{m['sender']}】{m['text']}"
        lines = [f"📋 你有 {len(msgs)} 条未读消息："]
        for m in msgs[:10]:  # 最多列 10 条
            lines.append(f"· {m['sender']}：{m['text']}")
        if len(msgs) > 10:
            lines.append(f"...（还有 {len(msgs) - 10} 条）")
        return "\n".join(lines)

    # ---------------- 测试辅助 ----------------

    def get_status(self) -> dict:
        """返回当前路由状态（供 /api/integrations 端点查询）。"""
        self._maybe_reload_config()
        self._ensure_channels_loaded()
        return {
            "enabled_channels": list(self._channel_senders.keys()),
            "quiet_hours_active": self._in_quiet_hours(),
            "digest_buffer_count": sum(len(v) for v in self._digest_buffer.values()),
            "last_digest_ts": self._last_digest_ts,
            "routing": self._config.get("message_routing", {}),
        }


# ====================================================================
# 模块级便捷函数
# ====================================================================

_router_singleton: MessageRouter | None = None


def get_router() -> MessageRouter:
    """获取全局 MessageRouter 单例。"""
    global _router_singleton
    if _router_singleton is None:
        _router_singleton = MessageRouter()
    return _router_singleton


def dispatch_active_message(message: dict) -> dict:
    """便捷接口：把消息交给 MessageRouter 分发。

    任何失败都不抛异常，仅返回状态。
    """
    try:
        return get_router().dispatch(message)
    except Exception as e:
        return {"dispatched": [], "buffered": [], "skipped": [f"error:{e}"]}
