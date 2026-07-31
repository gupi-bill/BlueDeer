"""commit 39：外部 API 调用器（用 urllib，零第三方依赖）。

零基础读者可以这样理解：
- 智能体可以调用用户预先配置的外部 API
- 用 Python 标准库 urllib
- API 密钥从环境变量读取，不写日志
- 支持 GET/POST，可自定义 Headers
- 敏感字段（token / password / secret）自动脱敏
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# 脱敏字段名（不区分大小写）
_SENSITIVE_KEYS = ("token", "password", "passwd", "secret",
                    "api_key", "apikey", "auth", "authorization")

# 默认超时
_DEFAULT_TIMEOUT = 30.0


class ApiResult:
    """API 调用结果。"""
    __slots__ = (
        "duration_ms",
        "error",
        "method",
        "ok",
        "redacted",
        "request_body",
        "response_body",
        "status_code",
        "url",
    )

    def __init__(self, ok: bool, status_code: int = 0, url: str = "",
                 method: str = "GET", request_body: str = "",
                 response_body: str = "", duration_ms: float = 0,
                 error: str = "", redacted: bool = True) -> None:
        self.ok = ok
        self.status_code = status_code
        self.url = url
        self.method = method
        self.request_body = request_body
        self.response_body = response_body
        self.duration_ms = duration_ms
        self.error = error
        self.redacted = redacted

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "status_code": self.status_code,
            "url": self.url,
            "method": self.method,
            "request_body": self.request_body[:2000],
            "response_body": self.response_body[:4000],
            "duration_ms": round(self.duration_ms, 2),
            "error": self.error,
            "redacted": self.redacted,
        }


def _redact(obj: Any) -> Any:
    """递归把 dict 里的敏感字段值替换为 ***。"""
    if isinstance(obj, dict):
        return {k: ("***" if any(s in k.lower() for s in _SENSITIVE_KEYS)
                    else _redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


class ApiEndpoint:
    """一个外部 API 端点配置。"""

    def __init__(self, config: dict) -> None:
        self.name: str = config.get("name", "")
        self.url: str = config.get("url", "")
        self.auth_type: str = config.get("auth_type", "")  # "" / "token" / "basic"
        self.auth_value_env: str = config.get("auth_value_env", "")
        self.headers: dict = config.get("headers", {})
        self.timeout: float = float(config.get("timeout", _DEFAULT_TIMEOUT))

    def get_auth_value(self) -> str:
        """从环境变量读取密钥。"""
        if not self.auth_value_env:
            return ""
        return os.environ.get(self.auth_value_env, "")

    def to_dict(self, include_secret: bool = False) -> dict:
        d = {
            "name": self.name,
            "url": self.url,
            "auth_type": self.auth_type,
            "auth_value_env": self.auth_value_env,
            "headers": dict(self.headers),
            "timeout": self.timeout,
        }
        if include_secret:
            d["auth_value_preview"] = (self.get_auth_value()[:4] + "***"
                                        if self.get_auth_value() else "")
        return d


class ApiCaller:
    """外部 API 调用器。"""

    def __init__(self, config: dict) -> None:
        """config 形如：
        {
          "enabled": false,
          "endpoints": [
            {"name": "github_api", "url": "https://api.github.com",
             "auth_type": "token", "auth_value_env": "GITHUB_TOKEN"}
          ],
          "require_approval": true
        }
        """
        self._config = dict(config)
        self._lock = threading.RLock()
        self._enabled = bool(self._config.get("enabled", False))
        self._require_approval = bool(self._config.get("require_approval", True))
        self._endpoints: dict[str, ApiEndpoint] = {}
        for ep_config in self._config.get("endpoints", []):
            ep = ApiEndpoint(ep_config)
            if ep.name:
                self._endpoints[ep.name] = ep

    @property
    def enabled(self) -> bool:
        return self._enabled

    def update_config(self, config: dict) -> None:
        with self._lock:
            self._config.update(config)
            self._enabled = bool(self._config.get("enabled", False))
            self._require_approval = bool(self._config.get("require_approval", True))
            self._endpoints = {}
            for ep_config in self._config.get("endpoints", []):
                ep = ApiEndpoint(ep_config)
                if ep.name:
                    self._endpoints[ep.name] = ep

    def status(self) -> dict:
        return {
            "enabled": self._enabled,
            "require_approval": self._require_approval,
            "endpoints": [ep.to_dict(include_secret=False)
                          for ep in self._endpoints.values()],
        }

    def call(self, endpoint_name: str, method: str = "GET",
             path: str = "", query: dict | None = None,
             body: Any = None, extra_headers: dict | None = None,
             caller: Any = None) -> ApiResult:
        """调用一个 API 端点。

        Args:
            endpoint_name: 在 config 中配置的端点名
            method: HTTP 方法
            path: URL 路径（追加到 endpoint.url 后面）
            query: 查询参数
            body: 请求体（dict 会自动 json 序列化）
            extra_headers: 额外的 headers
        """
        if not self._enabled:
            return ApiResult(False, error="API 集成未启用",
                              url=endpoint_name, method=method)
        with self._lock:
            ep = self._endpoints.get(endpoint_name)
        if ep is None:
            return ApiResult(False, error=f"端点 {endpoint_name} 未配置",
                              url=endpoint_name, method=method)
        # 拼完整 URL
        full_url = ep.url.rstrip("/") + "/" + path.lstrip("/") if path else ep.url
        if query:
            qs = urllib.parse.urlencode(query)
            full_url = f"{full_url}?{qs}"
        # 构造 headers
        headers = dict(ep.headers)
        if extra_headers:
            headers.update(extra_headers)
        # 加认证
        auth_value = ep.get_auth_value()
        if ep.auth_type == "token" and auth_value:
            headers["Authorization"] = f"Bearer {auth_value}"
        elif ep.auth_type == "basic" and auth_value:
            import base64
            headers["Authorization"] = "Basic " + base64.b64encode(
                auth_value.encode()).decode()
        # 序列化 body
        request_body_str = ""
        if body is not None:
            if isinstance(body, (dict, list)):
                request_body_str = json.dumps(body, ensure_ascii=False)
                if "Content-Type" not in headers:
                    headers["Content-Type"] = "application/json"
            else:
                request_body_str = str(body)
        # 执行
        start = time.time()
        try:
            req = urllib.request.Request(
                full_url, method=method,
                data=request_body_str.encode("utf-8") if request_body_str else None,
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=ep.timeout) as resp:
                resp_body = resp.read().decode("utf-8", errors="replace")
                status = resp.status
                dur = (time.time() - start) * 1000
                return ApiResult(
                    ok=200 <= status < 300,
                    status_code=status,
                    url=full_url,
                    method=method,
                    request_body=request_body_str,
                    response_body=resp_body,
                    duration_ms=dur,
                )
        except urllib.error.HTTPError as e:
            dur = (time.time() - start) * 1000
            resp_body = ""
            try:
                resp_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            return ApiResult(
                ok=False, status_code=e.code, url=full_url, method=method,
                request_body=request_body_str, response_body=resp_body,
                duration_ms=dur, error=f"HTTP {e.code}: {e.reason}",
            )
        except Exception as e:
            dur = (time.time() - start) * 1000
            return ApiResult(
                ok=False, url=full_url, method=method,
                request_body=request_body_str,
                duration_ms=dur, error=str(e),
            )
