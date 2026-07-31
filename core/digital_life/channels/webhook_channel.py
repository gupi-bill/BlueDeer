"""Webhook 渠道：企业微信 / 钉钉 / 飞书 群机器人。

零基础读者可以这样理解：
- 群机器人 Webhook 是一个 URL，往这个 URL POST JSON 就能在群里发消息。
- 三家格式不一样，但本质都是"组装 JSON → POST"。
- 每家都支持 Markdown 卡片，紧急消息用红色边框。

设计要点：
1. 用 Python 标准库 urllib，零外部依赖。
2. make_sender(key, config) 工厂：根据 key 返回对应渠道的 send 函数。
3. 钉钉有"加签"机制（防篡改），secret 不为空时自动签名。
4. send 函数接口：send(message_dict) → bool
5. 异步发送（子线程），避免 HTTP 卡住调用方。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import threading
import time
import urllib.error
import urllib.request

# ====================================================================
# HTTP POST 工具
# ====================================================================

def _http_post_json(url: str, payload: dict, timeout: float = 5.0) -> dict:
    """POST JSON 到 url，返回响应 dict。失败抛异常。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"_raw": body}


# ====================================================================
# 企业微信 Webhook
# ====================================================================

def _wechat_send(url: str, message: dict) -> bool:
    """企业微信群机器人发消息。

    格式：Markdown 卡片。紧急消息用红色警示。
    """
    sender = message.get("sender", "智能体")
    text = message.get("text", "")
    priority = (message.get("priority") or "low").lower()
    is_digest = message.get("is_digest", False)
    if is_digest:
        # 汇总消息直接用文本
        content = f"**BlueDeer 消息汇总**\n\n{text}"
    else:
        prefix = ""
        if priority == "high":
            prefix = '<font color="warning">【紧急】</font>'
        elif priority == "medium":
            prefix = '<font color="info">【重要】</font>'
        content = f"{prefix}**{sender}**：{text}"
    payload = {
        "msgtype": "markdown",
        "markdown": {"content": content},
    }
    resp = _http_post_json(url, payload)
    return resp.get("errcode", 0) == 0


# ====================================================================
# 钉钉 Webhook（支持加签）
# ====================================================================

def _dingtalk_sign(secret: str, timestamp: int) -> str:
    """钉钉加签：HmacSHA256(timestamp + "\n" + secret, secret) → base64。"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def _dingtalk_send(url: str, secret: str, message: dict) -> bool:
    """钉钉群机器人发消息。"""
    sender = message.get("sender", "智能体")
    text = message.get("text", "")
    priority = (message.get("priority") or "low").lower()
    is_digest = message.get("is_digest", False)
    # 钉钉 markdown 的 title 必填，content 是正文
    if is_digest:
        title = "BlueDeer 消息汇总"
        content = text.replace("\n", "\n\n")
    else:
        prefix = ""
        if priority == "high":
            prefix = "### 【紧急】\n\n"
        elif priority == "medium":
            prefix = "### 【重要】\n\n"
        title = f"{sender} 发来消息"
        content = f"{prefix}**{sender}**\n\n{text}"
    # 加签
    final_url = url
    if secret:
        ts = int(time.time() * 1000)
        sign = _dingtalk_sign(secret, ts)
        sep = "&" if "?" in url else "?"
        final_url = f"{url}{sep}timestamp={ts}&sign={sign}"
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": content},
    }
    resp = _http_post_json(final_url, payload)
    return resp.get("errcode", 0) == 0


# ====================================================================
# 飞书 Webhook
# ====================================================================

def _feishu_send(url: str, message: dict) -> bool:
    """飞书群机器人发消息。"""
    sender = message.get("sender", "智能体")
    text = message.get("text", "")
    priority = (message.get("priority") or "low").lower()
    is_digest = message.get("is_digest", False)
    if is_digest:
        content = f"**BlueDeer 消息汇总**\n{text}"
    else:
        prefix = ""
        if priority == "high":
            prefix = "**【紧急】** "
        elif priority == "medium":
            prefix = "**【重要】** "
        content = f"{prefix}**{sender}**：{text}"
    payload = {
        "msg_type": "text",
        "content": {"text": content},
    }
    # 飞书也支持 interactive 卡片，但 text 格式最稳定，先简单用
    resp = _http_post_json(url, payload)
    return resp.get("StatusCode", 0) == 0 or resp.get("code", -1) == 0


# ====================================================================
# 工厂：根据渠道名返回 send 函数
# ====================================================================

def make_sender(channel_key: str, config: dict):
    """工厂函数：根据 channel_key 返回对应的 send 函数。

    Args:
        channel_key: "wechat_webhook" / "dingtalk_webhook" / "feishu_webhook"
        config: 该渠道的配置 dict（含 url、可选 secret）

    Returns:
        send(message_dict) → bool 函数
    """
    url = config.get("url", "")
    if not url:
        return None

    if channel_key == "wechat_webhook":
        def _send(msg):
            return _async_call(_wechat_send, url, msg)
        return _send

    if channel_key == "dingtalk_webhook":
        secret = config.get("secret", "")
        def _send(msg):
            return _async_call(_dingtalk_send, url, secret, msg)
        return _send

    if channel_key == "feishu_webhook":
        def _send(msg):
            return _async_call(_feishu_send, url, msg)
        return _send

    return None


def _async_call(fn, *args) -> bool:
    """异步调用 HTTP，避免阻塞主线程。"""
    def _worker():
        try:
            fn(*args)
        except Exception:
            pass
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return True
