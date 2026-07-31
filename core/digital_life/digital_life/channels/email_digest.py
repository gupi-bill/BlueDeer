"""邮件渠道：日报摘要 + 即时紧急通知。

零基础读者可以这样理解：
- 用 Python 自带的 smtplib 发邮件，零外部依赖。
- 两种模式：
  1. 即时通知（high 优先级）：马上发一封简短邮件
  2. 日报摘要（digest）：把多条普通消息汇总成一封 HTML 邮件
- 邮件内容用 HTML 格式，包含表格、配色，比纯文本好看。
- SMTP 配置失败时静默跳过，不影响其他渠道。

设计要点：
1. make_sender(config) → send(message_dict) 函数（即时通知用）
2. send_digest(config, msgs) 函数（digest 发送用）
3. HTML 邮件模板，紧急邮件用红色顶栏，日报用蓝色顶栏
4. 异步发送（子线程），避免 SMTP 慢拖累主线程
"""
from __future__ import annotations

import datetime
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ====================================================================
# SMTP 发送核心
# ====================================================================

def _smtp_send(config: dict, subject: str, html_body: str) -> bool:
    """通过 SMTP 发送一封 HTML 邮件。

    Args:
        config: email 渠道配置（smtp_host/port/sender/password/recipient）
        subject: 邮件标题
        html_body: HTML 正文

    Returns:
        True 表示发送成功
    """
    host = config.get("smtp_host", "")
    port = int(config.get("smtp_port", 587))
    sender = config.get("sender", "")
    password = config.get("password", "")
    recipient = config.get("recipient", "")
    if not (host and sender and password and recipient):
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"BlueDeer <{sender}>"
    msg["To"] = recipient
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    try:
        # 用 TLS 加密连接（587 端口走 STARTTLS）
        with smtplib.SMTP(host, port, timeout=10) as srv:
            srv.starttls()
            srv.login(sender, password)
            srv.sendmail(sender, [recipient], msg.as_string())
        return True
    except Exception:
        return False


# ====================================================================
# HTML 模板
# ====================================================================

_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
         background: #f5f5f7; color: #1d1d1f; margin: 0; padding: 20px; }}
  .container {{ max-width: 640px; margin: 0 auto; background: #fff;
                border-radius: 12px; overflow: hidden; box-shadow: 0 2px 16px rgba(0,0,0,0.08); }}
  .header {{ padding: 24px 32px; color: #fff; }}
  .header.urgent {{ background: linear-gradient(135deg, #ff4757, #ff6b81); }}
  .header.digest   {{ background: linear-gradient(135deg, #5e72e4, #825ee4); }}
  .header h1 {{ margin: 0; font-size: 22px; font-weight: 600; }}
  .header .meta {{ margin-top: 8px; font-size: 13px; opacity: 0.9; }}
  .body {{ padding: 24px 32px; }}
  .msg-list {{ list-style: none; padding: 0; margin: 0; }}
  .msg-item {{ padding: 12px 0; border-bottom: 1px solid #f0f0f0; }}
  .msg-item:last-child {{ border-bottom: none; }}
  .msg-sender {{ font-weight: 600; color: #5e72e4; margin-right: 8px; }}
  .msg-text {{ color: #1d1d1f; }}
  .msg-time {{ font-size: 12px; color: #86868b; margin-left: 8px; }}
  .priority-tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px;
                   font-size: 11px; font-weight: 600; margin-right: 6px; }}
  .priority-tag.high {{ background: #ffe0e6; color: #ff4757; }}
  .priority-tag.medium {{ background: #fff4e0; color: #ff9500; }}
  .priority-tag.low {{ background: #e0f7fa; color: #00acc1; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
  th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #f0f0f0; font-size: 14px; }}
  th {{ background: #fafafa; font-weight: 600; color: #5e72e4; }}
  .footer {{ padding: 16px 32px; background: #fafafa; font-size: 12px;
             color: #86868b; text-align: center; }}
</style>
</head>
<body>
<div class="container">
  <div class="header {header_class}">
    <h1>{title}</h1>
    <div class="meta">{meta}</div>
  </div>
  <div class="body">
    {body}
  </div>
  <div class="footer">
    本邮件由 BlueDeer 智能体系统自动发送 · <a href="{dashboard_url}">前往管控台</a>
  </div>
</div>
</body>
</html>
"""


def _format_priority_tag(priority: str) -> str:
    """生成优先级标签 HTML。"""
    p = (priority or "low").lower()
    label = {"high": "紧急", "medium": "重要", "low": "普通"}.get(p, "普通")
    return f'<span class="priority-tag {p}">{label}</span>'


# ====================================================================
# 即时通知（high 优先级）
# ====================================================================

def _send_instant(config: dict, message: dict) -> bool:
    """发送一封即时通知邮件（紧急消息）。"""
    sender = message.get("sender", "智能体")
    text = message.get("text", "")
    priority = message.get("priority", "low")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body_html = f"""
    <p>{_format_priority_tag(priority)}<strong>{sender}</strong> 发来一条消息：</p>
    <p style="padding: 16px; background: #f9f9f9; border-radius: 8px; font-size: 15px;">{text}</p>
    <p style="font-size: 13px; color: #86868b; margin-top: 16px;">发送时间：{now}</p>
    """
    html = _HTML_TEMPLATE.format(
        header_class="urgent",
        title=f"BlueDeer 紧急通知 · {sender}",
        meta=now,
        body=body_html,
        dashboard_url="http://127.0.0.1:8080/",
    )
    return _smtp_send(config, f"【BlueDeer 紧急】{sender}：{text[:30]}", html)


# ====================================================================
# 日报 / 摘要
# ====================================================================

def send_digest(config: dict, messages: list[dict]) -> bool:
    """发送一封摘要邮件（多条普通消息汇总）。

    Args:
        config: email 渠道配置
        messages: 消息列表 [{sender, text, category, time, ...}]

    Returns:
        True 表示发送成功
    """
    if not messages:
        return False
    now = datetime.datetime.now()
    date_str = now.strftime("%Y年%m月%d日 %H:%M")
    # 构造消息列表 HTML
    items_html = []
    for m in messages:
        sender = m.get("sender", "?")
        text = m.get("text", "")
        ts = m.get("time", 0)
        try:
            t_str = datetime.datetime.fromtimestamp(float(ts)).strftime("%H:%M")
        except Exception:
            t_str = ""
        items_html.append(
            f'<li class="msg-item">'
            f'<span class="msg-sender">{sender}</span>'
            f'<span class="msg-text">{text}</span>'
            f'<span class="msg-time">{t_str}</span>'
            f'</li>'
        )
    body_html = f"""
    <p>你有 <strong>{len(messages)}</strong> 条未读消息：</p>
    <ul class="msg-list">
        {''.join(items_html)}
    </ul>
    """
    html = _HTML_TEMPLATE.format(
        header_class="digest",
        title=f"BlueDeer 消息摘要 · {date_str}",
        meta=f"共 {len(messages)} 条消息",
        body=body_html,
        dashboard_url="http://127.0.0.1:8080/",
    )
    return _smtp_send(config, f"BlueDeer 摘要 | {now.strftime('%Y-%m-%d %H:%M')}", html)


def send_daily_report(config: dict, report_data: dict) -> bool:
    """发送每日工作摘要报告。

    Args:
        config: email 渠道配置
        report_data: 日报数据 {
            "date": str,
            "tasks_done": [str],
            "employees": [{name, species, energy, health, mood, ...}],
            "events": [{type, desc, time}],
            "warnings": [str],
            "funny_logs": [str],
        }

    Returns:
        True 表示发送成功
    """
    date_str = report_data.get("date", datetime.datetime.now().strftime("%Y年%m月%d日"))
    # 任务列表
    tasks = report_data.get("tasks_done", [])
    tasks_html = "<p>今日无完成任务记录。</p>"
    if tasks:
        tasks_html = "<ul>" + "".join(f"<li>{t}</li>" for t in tasks) + "</ul>"
    # 员工状态表
    employees = report_data.get("employees", [])
    emp_rows = ""
    for e in employees:
        emp_rows += (
            f"<tr>"
            f"<td>{e.get('name', '?')}</td>"
            f"<td>{e.get('species', '?')}</td>"
            f"<td>{e.get('energy', 0):.0f}</td>"
            f"<td>{e.get('health', 0):.0f}</td>"
            f"<td>{e.get('mood', '?')}</td>"
            f"</tr>"
        )
    emp_table = (
        "<table><thead><tr>"
        "<th>姓名</th><th>物种</th><th>能量</th><th>健康</th><th>心情</th>"
        "</tr></thead><tbody>" + emp_rows + "</tbody></table>"
        if emp_rows else "<p>暂无员工数据。</p>"
    )
    # 重要事件
    events = report_data.get("events", [])
    events_html = "<p>今日无重要事件。</p>"
    if events:
        events_html = "<ul>" + "".join(
            f"<li><strong>{e.get('type', '')}</strong>：{e.get('desc', '')} "
            f"<span class='msg-time'>({e.get('time', '')})</span></li>"
            for e in events
        ) + "</ul>"
    # 预警
    warnings = report_data.get("warnings", [])
    warnings_html = "<p>暂无预警。</p>" if not warnings else (
        "<ul style='color: #ff4757;'>" + "".join(f"<li>{w}</li>" for w in warnings) + "</ul>"
    )
    # 趣事
    funny = report_data.get("funny_logs", [])
    funny_html = "<p>今日无趣事。</p>" if not funny else (
        "<ul style='color: #825ee4;'>" + "".join(f"<li>{f}</li>" for f in funny) + "</ul>"
    )

    body_html = f"""
    <h3>今日完成的任务</h3>
    {tasks_html}
    <h3>员工状态概览</h3>
    {emp_table}
    <h3>重要事件</h3>
    {events_html}
    <h3>明日预警</h3>
    {warnings_html}
    <h3>员工趣事精选</h3>
    {funny_html}
    """
    html = _HTML_TEMPLATE.format(
        header_class="digest",
        title=f"BlueDeer 日报 | {date_str}",
        meta=f"生成时间 {datetime.datetime.now().strftime('%H:%M:%S')}",
        body=body_html,
        dashboard_url="http://127.0.0.1:8080/",
    )
    return _smtp_send(config, f"BlueDeer 日报 | {date_str}", html)


# ====================================================================
# 工厂：make_sender 返回即时通知用的 send 函数
# ====================================================================

def make_sender(config: dict):
    """工厂：返回一个 send(message_dict) 函数，用于即时发送紧急邮件。

    Args:
        config: email 渠道配置

    Returns:
        send(message_dict) → bool 函数
    """
    def _send(message: dict) -> bool:
        # 异步发送，避免 SMTP 慢拖累主线程
        def _worker():
            try:
                _send_instant(config, message)
            except Exception:
                pass
        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return True
    return _send
