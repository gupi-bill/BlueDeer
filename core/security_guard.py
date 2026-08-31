"""BlueDeer 安全守卫：高危拦截 + 权限校验 + 日志脱敏 + CSRF 保护。"""

from __future__ import annotations

import logging
import secrets as _secrets
import threading
import time
from typing import Any

from core.security_scanner import RiskLevel, SecurityReport, SecurityScanner

logger = logging.getLogger("bluedeer.security_guard")

try:
    from tools.base_tool import ToolCategory
except ImportError:

    class ToolCategory:
        HAZARDOUS = "hazardous"


class SecurityGuard:
    """高危操作拦截器。"""

    def __init__(
        self,
        scanner: SecurityScanner | None = None,
        allowed_hazardous_tools: set[str] | None = None,
        agent_permissions: dict[str, set[str]] | None = None,
        require_confirm_for_high: bool = True,
        policy_engine: Any = None,
    ) -> None:
        self._scanner = scanner or SecurityScanner()
        self._allowed_hazardous = allowed_hazardous_tools or set()
        self._agent_permissions = agent_permissions or {}
        self._require_confirm = require_confirm_for_high
        self._confirm_tokens: set[str] = set()
        self._lock = threading.Lock()
        self._policy_engine = policy_engine

    def allow_hazardous(self, tool_name: str) -> None:
        with self._lock:
            self._allowed_hazardous.add(tool_name)

    @property
    def agent_permissions(self) -> dict[str, set[str]]:
        return self._agent_permissions

    def grant(self, agent_id: str, tool_name: str) -> None:
        with self._lock:
            self._agent_permissions.setdefault(agent_id, set()).add(tool_name)

    def issue_confirm_token(self, reason: str = "") -> str:
        token = _secrets.token_hex(8)
        with self._lock:
            self._confirm_tokens.add(token)
        logger.info("颁发二次确认 token（reason=%s）", reason)
        return token

    def revoke_confirm_token(self, token: str) -> bool:
        with self._lock:
            if token in self._confirm_tokens:
                self._confirm_tokens.discard(token)
                return True
            return False

    def has_pending_confirm_tokens(self) -> int:
        return len(self._confirm_tokens)

    def check_permission(self, agent_id: str, tool_name: str) -> tuple[bool, str]:
        if self._policy_engine is not None:
            return self._policy_engine.check_permission(agent_id, tool_name)
        if not self._agent_permissions:
            return True, "ok"
        perms = self._agent_permissions.get(agent_id)
        if perms is None:
            return False, f"agent '{agent_id}' 未配置任何权限"
        if tool_name in perms:
            return True, "ok"
        return False, f"agent '{agent_id}' 无权调用工具 '{tool_name}'"

    def check_operation(
        self,
        tool_name: str,
        params: dict[str, Any],
        category: ToolCategory,
        confirm_token: str | None = None,
    ) -> tuple[bool, SecurityReport | None, str]:
        if self._policy_engine is not None:
            return self._policy_engine.check_operation(
                tool_name, params, category, confirm_token
            )
        if category == ToolCategory.HAZARDOUS:
            if tool_name not in self._allowed_hazardous:
                return False, None, f"高危工具 '{tool_name}' 未在白名单，拒绝调用"

        report: SecurityReport | None = None
        for k, v in params.items():
            if not isinstance(v, str):
                continue
            r = self._scanner.scan_all(v, target=f"param:{k}")
            if r.threats:
                if report is None:
                    report = r
                else:
                    report.threats.extend(r.threats)

        if report is not None and not report.passed:
            if self._require_confirm:
                if confirm_token is None:
                    return (
                        False,
                        report,
                        (
                            f"参数扫描发现 HIGH 级威胁，需二次确认: "
                            f"{[t.threat_type for t in report.threats if t.risk == RiskLevel.HIGH]}"
                        ),
                    )
                if confirm_token not in self._confirm_tokens:
                    return False, report, f"二次确认 token 无效: {confirm_token[:8]}***"
                self._confirm_tokens.discard(confirm_token)
                logger.warning("HIGH 级威胁经二次确认放行: %s", tool_name)
                return True, report, "ok（经二次确认放行）"

            return (
                False,
                report,
                (
                    f"参数扫描发现 HIGH 级威胁: "
                    f"{[t.threat_type for t in report.threats if t.risk == RiskLevel.HIGH]}"
                ),
            )

        return True, report, "ok"


def _is_sensitive_key(key: str) -> bool:
    lower = key.lower()
    return any(
        w in lower
        for w in (
            "password",
            "passwd",
            "pwd",
            "secret",
            "token",
            "apikey",
            "api_key",
            "aksk",
            "access_key",
            "secret_key",
            "private_key",
            "credential",
        )
    )


def _sanitize_string(text: str) -> str:
    from core.security_scanner import _SECRET_PATTERNS

    for _, pat in _SECRET_PATTERNS:

        def _mask(m: Any) -> str:
            raw = m.group()
            return raw[:8] + "***" if len(raw) > 8 else raw[:4] + "***"

        text = pat.sub(_mask, text)
    return text


def sanitize_log(data: Any) -> Any:
    """递归脱敏日志数据。"""
    if isinstance(data, dict):
        sanitized: dict[str, Any] = {}
        for k, v in data.items():
            if _is_sensitive_key(str(k)):
                sanitized[k] = "***"
            else:
                sanitized[k] = sanitize_log(v)
        return sanitized
    if isinstance(data, list):
        return [sanitize_log(x) for x in data]
    if isinstance(data, str):
        return _sanitize_string(data)
    return data


_CSRF_SECRET: str | None = None
_csrf_lock = threading.Lock()


def _get_csrf_secret() -> str:
    global _CSRF_SECRET
    if _CSRF_SECRET is None:
        with _csrf_lock:
            if _CSRF_SECRET is None:
                _CSRF_SECRET = _secrets.token_hex(32)
    return _CSRF_SECRET


def csrf_token() -> str:
    import hmac as _hmac

    secret = _get_csrf_secret()
    t = str(int(time.time()))
    sig = _hmac.new(secret.encode(), t.encode(), "sha256").hexdigest()[:12]
    return f"{t}.{sig}"


def validate_csrf_token(token: str, max_age: int = 3600) -> bool:
    import hmac as _hmac

    try:
        t_part, sig_part = token.split(".", 1)
        secret = _get_csrf_secret()
        expected = _hmac.new(secret.encode(), t_part.encode(), "sha256").hexdigest()[
            :12
        ]
        if not _hmac.compare_digest(sig_part, expected):
            return False
        ts = int(t_part)
        return (time.time() - ts) <= max_age
    except (ValueError, OSError):
        return False


def validate_request(headers: dict[str, str], body: str) -> tuple[bool, str]:
    token = headers.get("X-CSRF-Token") or headers.get("x-csrf-token") or ""
    if not token:
        method = (
            headers.get("X-HTTP-Method") or headers.get("x-http-method") or "GET"
        ).upper()
        if method in ("GET", "HEAD", "OPTIONS", "TRACE"):
            return True, "ok（安全方法免检）"
        return False, "缺少 X-CSRF-Token"

    if not validate_csrf_token(token):
        return False, "X-CSRF-Token 无效或已过期"

    scanner = SecurityScanner()
    report = scanner.scan_all(body, target="request_body")
    if not report.passed:
        threats = [t.threat_type for t in report.threats if t.risk == RiskLevel.HIGH]
        if threats:
            return False, f"请求 body 发现高危威胁: {threats}"

    return True, "ok"
