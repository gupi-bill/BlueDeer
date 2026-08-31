"""BlueDeer 本地一键启动器。

双击本文件即可：自动用项目 .venv 启动本地 Web 服务，并自动打开浏览器访问
http://127.0.0.1:8080 。

本质就是把「bluedeer web」封装成「双击即用」，纯本地（127.0.0.1）部署，
不暴露到局域网，且不再依赖任何在线资源（字体已本地化）。
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
HOST, PORT = "127.0.0.1", 8080


def _open_browser_when_ready(path: str = "") -> None:
    """后台等待端口就绪后自动打开本地浏览器。"""

    def _wait() -> None:
        url = f"http://{HOST}:{PORT}{path}"
        deadline = time.time() + 20.0
        while time.time() < deadline:
            try:
                with socket.create_connection((HOST, PORT), timeout=0.5):
                    webbrowser.open(url)
                    print(f"✅ 已自动在浏览器打开 → {url}")
                    return
            except OSError:
                time.sleep(0.3)
        print(f"⚠️ 未能自动打开浏览器，请手动访问：{url}")

    threading.Thread(target=_wait, daemon=True).start()


def _pick_python() -> str:
    if sys.platform == "win32":
        cand = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    else:
        cand = os.path.join(ROOT, ".venv", "bin", "python")
    return cand if os.path.exists(cand) else sys.executable


# ---- OpenClaw 网关联动：若 18789 未监听则自动拉起 ----
OPENCLAW_STATE_DIR = os.getenv("OPENCLAW_STATE_DIR", r"<WORKSPACE_DIR>\OpenClaw\data")
_OPENCLAW_NODE_DIR = os.getenv("BLUEDEER_NODE_DIR", r"<WORKSPACE_DIR>\.workbuddy\binaries\node\versions\22.22.2")
OPENCLAW_NODE = os.path.join(_OPENCLAW_NODE_DIR, "node.exe")
OPENCLAW_CLI = os.path.join(_OPENCLAW_NODE_DIR, "node_modules", "openclaw", "dist", "index.js")
GW_PORT = 18789


def _ensure_openclaw_gateway() -> None:
    """OpenClaw 网关没在跑就后台拉起它（BlueDeer 控制台依赖它拉真实数据）。"""
    try:
        with socket.create_connection(("127.0.0.1", GW_PORT), timeout=0.5):
            print(f"🔗 OpenClaw 网关已在运行 (127.0.0.1:{GW_PORT})")
            return
    except OSError:
        pass
    if not os.path.exists(OPENCLAW_CLI):
        print("⚠️ 未找到 openclaw CLI，跳过网关拉起")
        return
    env = dict(os.environ)
    env["OPENCLAW_STATE_DIR"] = OPENCLAW_STATE_DIR
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(
            [OPENCLAW_NODE, OPENCLAW_CLI, "gateway", "--port", str(GW_PORT)],
            env=env, creationflags=flags,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        print(f"🚀 正在拉起 OpenClaw 网关 (127.0.0.1:{GW_PORT})…")
    except Exception as e:
        print(f"⚠️ 拉起 OpenClaw 网关失败：{e}")


def main() -> None:
    os.chdir(ROOT)
    python = _pick_python()
    _ensure_openclaw_gateway()
    print(f"🦌 BlueDeer 本地服务启动中 → http://{HOST}:{PORT}")
    print(f"   ├─ 主控制台: http://{HOST}:{PORT}/")
    print(f"   ├─ Agent 调度台: http://{HOST}:{PORT}/console/")
    print(f"   └─ Agent API: http://{HOST}:{PORT}/agent/")
    _open_browser_when_ready()
    try:
        subprocess.run(
            [python, "-m", "uvicorn", "web_server:app",
             "--host", HOST, "--port", str(PORT)],
            check=True,
        )
    except KeyboardInterrupt:
        print("\n🛑 已停止 BlueDeer 本地服务")


if __name__ == "__main__":
    main()
