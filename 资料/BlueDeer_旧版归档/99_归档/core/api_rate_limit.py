"""企业级 API 网关限流（复用 core.sliding_window）。

三层限流：用户 + IP + 接口（滑动窗口）。
规则可配置：data/rate_limits.json（缺省自动创建）。
超过阈值返回 429。
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

from core.sliding_window import SlidingWindowLimiter

logger = logging.getLogger("bluedeer.rate_limit")

_RULES_FILE = "data/rate_limits.json"

# 默认规则：60 秒窗口
_DEFAULT_RULES = {
    "default": {"window": 60, "max": 120},          # 每 IP 每分钟 120 次
    "per_user": {"window": 60, "max": 300},          # 每用户每分钟 300 次
    "per_endpoint": {"window": 60, "max": 60},       # 每接口每分钟 60 次
}


def _load_rules() -> dict[str, Any]:
    os.makedirs(os.path.dirname(_RULES_FILE) or ".", exist_ok=True)
    if not os.path.exists(_RULES_FILE):
        with open(_RULES_FILE, "w", encoding="utf-8") as f:
            json.dump(_DEFAULT_RULES, f, ensure_ascii=False, indent=2)
    try:
        with open(_RULES_FILE, "r", encoding="utf-8") as f:
            rules = json.load(f)
        if not isinstance(rules, dict):
            raise ValueError("rules 必须是对象")
        return rules
    except Exception as e:
        logger.warning("限流规则加载失败，使用默认规则: %s", e)
        return dict(_DEFAULT_RULES)


class ApiRateLimiter:
    """三层限流：user / ip / endpoint。"""

    def __init__(self, rules_file: str = _RULES_FILE) -> None:
        self._rules_file = rules_file
        self._rules: dict[str, Any] = _load_rules()
        self._limiters: dict[str, SlidingWindowLimiter] = {}
        self._lock = threading.RLock()
        self._refresh_rules()

    def _refresh_rules(self) -> None:
        try:
            with open(self._rules_file, "r", encoding="utf-8") as f:
                rules = json.load(f)
            if isinstance(rules, dict):
                self._rules = rules
        except Exception:
            pass
        self._reload_enabled = True

    def reload(self) -> None:
        """热重载限流规则（改配置即生效）。"""
        with self._lock:
            self._refresh_rules()

    def _get_limiter(self, key: str, window: float, max_req: float) -> SlidingWindowLimiter:
        limiter = self._limiters.get(key)
        if limiter is None:
            limiter = SlidingWindowLimiter(window=window, max_requests=max_req)
            self._limiters[key] = limiter
        # 规则变化时同步窗口/上限
        limiter._window = window
        limiter._max = max_req
        return limiter

    def allow(self, user: str, ip: str, endpoint: str) -> tuple[bool, dict[str, Any]]:
        """返回 (是否放行, 详情)。超限任一层都拒绝。"""
        with self._lock:
            self._refresh_rules()
            default = self._rules.get("default", _DEFAULT_RULES["default"])
            per_user = self._rules.get("per_user", _DEFAULT_RULES["per_user"])
            per_endpoint = self._rules.get("per_endpoint", _DEFAULT_RULES["per_endpoint"])

            checks = [
                ("ip:" + ip, default["window"], default["max"]),
            ]
            if user:
                checks.append(("user:" + user, per_user["window"], per_user["max"]))
            checks.append(("endpoint:" + endpoint, per_endpoint["window"], per_endpoint["max"]))

            for key, window, max_req in checks:
                limiter = self._get_limiter(key, window, max_req)
                if not limiter.try_acquire(key):
                    return False, {
                        "key": key,
                        "window": window,
                        "max": max_req,
                    }
            return True, {}

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "rules": self._rules,
                "active_keys": len(self._limiters),
            }


# 单例
_rate_limiter: ApiRateLimiter | None = None
_rate_lock = threading.Lock()


def get_rate_limiter() -> ApiRateLimiter:
    global _rate_limiter
    with _rate_lock:
        if _rate_limiter is None:
            _rate_limiter = ApiRateLimiter()
        return _rate_limiter
