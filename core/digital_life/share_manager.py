"""commit 40：对外分享与导出 - 参观模式。

零基础读者可以这样理解：
- 你想给朋友看看你的数字森林公司，但又不希望他们乱操作
- 生成一个"参观链接"（带临时 token），朋友打开就能看到只读版的公司
- token 24 小时有效，你可以随时撤销
- 参观者可以走动、看员工状态、看资料库，但不能下任务、改设置

token 持久化：data/share_tokens.json
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from typing import Any

_TOKENS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "share_tokens.json",
)

# token 有效期：24 小时
TOKEN_TTL = 24 * 3600

# 参观者能访问的 API 路径白名单（只读）
VISITOR_ALLOWED_PATHS = {
    "/visit", "/index", "/login",
    "/api/status", "/api/story", "/api/report",
    "/api/zones", "/api/eco", "/api/emotions",
    "/api/relationships", "/api/relics", "/api/messages",
    "/api/memory", "/api/recruit_status", "/api/diary",
    "/api/autobiography", "/api/artifacts",
    "/api/projects", "/api/standups", "/api/risks",
    "/api/roles", "/api/role_definitions", "/api/role_history",
    "/events",  # SSE 事件流（只读）
    "/sprites/",  # 静态资源
}

# 参观者禁止访问的路径前缀
VISITOR_FORBIDDEN_PREFIXES = (
    "/api/inject", "/api/interact", "/api/recruit", "/api/narrate",
    "/api/immersive_settings", "/api/fragment/collect", "/api/desktop_pet",
    "/api/disease", "/api/persistent_memory", "/api/chat",
    "/api/agent_command", "/api/pipeline", "/api/approvals",
    "/api/agent_tools", "/api/suggestions", "/api/retrospects",
    "/api/experiences", "/api/negotiations", "/api/projects/milestone",
    "/api/projects/archive", "/api/standups/run", "/api/risks/scan",
    "/api/roles/evaluate", "/api/external", "/api/theme",
    "/snap", "/logout",  # 不能让参观者登出监工
)


class ShareToken:
    """一个参观 token。"""
    __slots__ = (
        "access_count",
        "created_ts",
        "expires_ts",
        "last_access_ts",
        "name",
        "revoked",
        "token",
    )

    def __init__(self, name: str = "") -> None:
        self.token: str = secrets.token_urlsafe(24)
        self.created_ts: float = time.time()
        self.expires_ts: float = time.time() + TOKEN_TTL
        self.name: str = name
        self.revoked: bool = False
        self.last_access_ts: float = 0.0
        self.access_count: int = 0

    def is_valid(self) -> bool:
        """是否有效（未撤销、未过期）。"""
        if self.revoked:
            return False
        if time.time() > self.expires_ts:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "token": self.token,
            "created_ts": self.created_ts,
            "expires_ts": self.expires_ts,
            "name": self.name,
            "revoked": self.revoked,
            "last_access_ts": self.last_access_ts,
            "access_count": self.access_count,
            "is_valid": self.is_valid(),
            "remaining_seconds": max(0, self.expires_ts - time.time()) if self.is_valid() else 0,
        }


class ShareManager:
    """参观模式 token 管理器（单例）。"""
    _instance: ShareManager | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tokens: dict[str, ShareToken] = {}
        self._biosphere_ref: Any = None
        self._load()

    @classmethod
    def get_instance(cls) -> ShareManager:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def set_biosphere(self, bio: Any) -> None:
        self._biosphere_ref = bio

    # ---------------- 持久化 ----------------

    def _load(self) -> None:
        try:
            if os.path.exists(_TOKENS_PATH):
                with open(_TOKENS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for td in data.get("tokens", []):
                    t = ShareToken(td.get("name", ""))
                    t.token = td.get("token", t.token)
                    t.created_ts = float(td.get("created_ts", 0))
                    t.expires_ts = float(td.get("expires_ts", 0))
                    t.revoked = bool(td.get("revoked", False))
                    t.last_access_ts = float(td.get("last_access_ts", 0))
                    t.access_count = int(td.get("access_count", 0))
                    self._tokens[t.token] = t
        except Exception:
            pass

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(_TOKENS_PATH), exist_ok=True)
            with self._lock:
                data = {"tokens": [t.to_dict() for t in self._tokens.values()]}
            with open(_TOKENS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------------- token 管理 ----------------

    def create_token(self, name: str = "") -> dict:
        """创建一个参观 token。"""
        with self._lock:
            t = ShareToken(name)
            self._tokens[t.token] = t
        self._save()
        return t.to_dict()

    def list_tokens(self) -> list[dict]:
        """列出所有 token。"""
        with self._lock:
            return [t.to_dict() for t in self._tokens.values()]

    def revoke_token(self, token: str) -> bool:
        """撤销一个 token。"""
        with self._lock:
            t = self._tokens.get(token)
            if t is None:
                return False
            t.revoked = True
        self._save()
        return True

    def delete_token(self, token: str) -> bool:
        """彻底删除一个 token。"""
        with self._lock:
            if token in self._tokens:
                del self._tokens[token]
                self._save()
                return True
            return False

    def validate_token(self, token: str) -> bool:
        """校验 token 是否有效，并记录访问。"""
        with self._lock:
            t = self._tokens.get(token)
            if t is None or not t.is_valid():
                return False
            t.last_access_ts = time.time()
            t.access_count += 1
        self._save()
        return True

    def get_token_info(self, token: str) -> dict | None:
        """获取 token 详情。"""
        with self._lock:
            t = self._tokens.get(token)
            return t.to_dict() if t else None

    # ---------------- 路径权限 ----------------

    @staticmethod
    def is_path_allowed_for_visitor(path: str) -> bool:
        """参观者能否访问该路径。"""
        # 去掉 query string
        if "?" in path:
            path = path.split("?", 1)[0]
        # 禁止前缀
        for prefix in VISITOR_FORBIDDEN_PREFIXES:
            if path.startswith(prefix):
                return False
        # 完全匹配白名单
        if path in VISITOR_ALLOWED_PATHS:
            return True
        # 静态资源
        if path.startswith("/sprites/"):
            return True
        # /api/memory?xxx 这种带参数的 GET 允许
        if path.startswith("/api/memory"):
            return True
        return False


def get_share_manager() -> ShareManager:
    """获取 ShareManager 单例。"""
    return ShareManager.get_instance()
