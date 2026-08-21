import logging
import socket
import threading
import time
import webbrowser

logger = logging.getLogger(__name__)
import uvicorn

from web_server.app import app


def _open_browser_when_ready(host: str, port: int, path: str = "") -> None:
    """后台等待端口就绪后，自动用本地浏览器打开 BlueDeer。"""

    def _wait() -> None:
        url = f"http://{host}:{port}{path}"
        deadline = time.time() + 15.0
        while time.time() < deadline:
            try:
                with socket.create_connection(
                    (host if host != "0.0.0.0" else "127.0.0.1", port), timeout=0.5
                ):
                    webbrowser.open(url)
                    print(f"✅ 已自动在浏览器打开 → {url}")
                    return
            except OSError:
                time.sleep(0.3)
        print(f"⚠️ 未能自动打开浏览器，请手动访问：{url}")

    threading.Thread(target=_wait, daemon=True).start()


if __name__ == "__main__":
    host, port = "127.0.0.1", 8080
    print(f"🦌 BlueDeer 本地服务 → http://{host}:{port}")
    _open_browser_when_ready(host, port)
    uvicorn.run(app, host=host, port=port)
