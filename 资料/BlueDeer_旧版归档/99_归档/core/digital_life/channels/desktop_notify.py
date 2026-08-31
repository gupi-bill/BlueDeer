"""桌面通知渠道：调用系统原生通知。

零基础读者可以这样理解：
- Linux：调 `notify-send` 命令（libnotify 自带，GNOME/KDE 都有）
- macOS：调 `osascript -e 'display notification ...'`（系统自带）
- Windows：调 PowerShell 的 BurntToast 或 MessageBox（不依赖第三方包）
- 三个都没：静默失败，不影响其他渠道

设计要点：
1. 全部 subprocess 调用，零 Python 依赖。
2. 异步 fire-and-forget：通知脚本卡住不阻塞主线程。
3. 通知标题格式：`[BlueDeer] 智能体名`，正文是消息内容。
4. 点击通知无法直接打开浏览器（系统限制），但可以提示用户去管控台。
"""

from __future__ import annotations

import platform
import subprocess
import threading


def _detect_platform() -> str:
    """检测当前系统类型。返回 'linux' / 'macos' / 'windows' / 'unknown'。"""
    sys_name = platform.system().lower()
    if sys_name == "linux":
        return "linux"
    if sys_name == "darwin":
        return "macos"
    if sys_name == "windows":
        return "windows"
    return "unknown"


_PLATFORM = _detect_platform()


def _linux_notify(title: str, body: str, urgent: bool = False) -> None:
    """Linux 调 notify-send。"""
    args = ["notify-send", title, body]
    if urgent:
        args.append("--urgency=critical")
    args.append("--app-name=BlueDeer")
    args.append("--expire-time=8000")
    subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


def _macos_notify(title: str, body: str, urgent: bool = False) -> None:
    """macOS 调 osascript。"""
    # 转义双引号
    title_esc = title.replace('"', '\\"')
    body_esc = body.replace('"', '\\"')
    sound = "default" if urgent else "'Populating a list by clicking on text [3]'"
    script = f'display notification "{body_esc}" with title "{title_esc}" sound name "{sound}"'
    subprocess.Popen(
        ["osascript", "-e", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


def _windows_notify(title: str, body: str, urgent: bool = False) -> None:
    """Windows 调 PowerShell 的 MessageBox（无依赖兜底）。

    BurntToast 模块如果装了会更漂亮，但不强制要求。
    """
    title_esc = title.replace("'", "''")
    body_esc = body.replace("'", "''")
    # 用 MessageBox 弹窗（系统自带，不依赖第三方）
    ps_script = (
        f"[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null;"
        f"$notify = New-Object System.Windows.Forms.NotifyIcon;"
        f"$notify.Icon = [System.Drawing.SystemIcons]::Information;"
        f"$notify.BalloonTipTitle = '{title_esc}';"
        f"$notify.BalloonTipText = '{body_esc}';"
        f"$notify.Visible = $True;"
        f"$notify.ShowBalloonTip(8000);"
        f"Start-Sleep -Seconds 9;"
        f"$notify.Dispose()"
    )
    subprocess.Popen(
        ["powershell", "-NoProfile", "-Command", ps_script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        shell=False,
    )


def _send_sync(message: dict) -> bool:
    """同步发送桌面通知。返回是否尝试调用了系统命令。"""
    title = f"[BlueDeer] {message.get('sender', '智能体')}"
    body = message.get("text", "")
    priority = (message.get("priority") or "low").lower()
    urgent = priority == "high"
    # 截断过长内容
    if len(body) > 200:
        body = body[:200] + "..."
    try:
        if _PLATFORM == "linux":
            _linux_notify(title, body, urgent)
        elif _PLATFORM == "macos":
            _macos_notify(title, body, urgent)
        elif _PLATFORM == "windows":
            _windows_notify(title, body, urgent)
        else:
            return False
        return True
    except (FileNotFoundError, OSError):
        # 命令不存在（如精简版 Linux 无 notify-send）
        return False
    except Exception:
        return False


def send(message: dict) -> bool:
    """异步发送桌面通知（fire-and-forget）。

    Args:
        message: 标准消息 dict（含 sender/text/priority 等字段）

    Returns:
        True 表示已派发到子线程
    """
    # 异步执行，避免子进程阻塞调用方
    t = threading.Thread(target=_send_sync, args=(message,), daemon=True)
    t.start()
    return True


def is_supported() -> bool:
    """检测当前平台是否支持桌面通知。"""
    if _PLATFORM == "linux":
        try:
            subprocess.run(
                ["which", "notify-send"],
                capture_output=True,
                timeout=2,
                check=True,
            )
            return True
        except Exception:
            return False
    return _PLATFORM in ("macos", "windows")
