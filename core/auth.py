"""用户认证 + 角色权限（RBAC）系统。

数据模型：
    - User：用户名、密码（加盐哈希）、角色、API Token、状态
    - Role：admin / operator / viewer 三级
    - SessionToken：登录会话管理
存储：users.jsonl + sessions.jsonl
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field, asdict
from typing import Any

logger = logging.getLogger("bluedeer.auth")

_USERS_FILE = "logs/users.jsonl"
_SESSIONS_FILE = "logs/sessions.jsonl"

ROLE_HIERARCHY = {"admin": 3, "operator": 2, "viewer": 1}
VALID_ROLES = ("admin", "operator", "viewer")


@dataclass
class User:
    username: str
    password_hash: str
    password_salt: str
    role: str = "viewer"
    display_name: str = ""
    email: str = ""
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    last_login: float = 0


@dataclass
class ApiToken:
    token: str
    name: str
    username: str
    created_at: float = field(default_factory=time.time)
    last_used: float = 0
    enabled: bool = True


@dataclass
class SessionToken:
    token: str
    username: str
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 86400)
    role: str = "viewer"


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return h.hex(), salt


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


class AuthSystem:
    def __init__(self, users_file: str = _USERS_FILE, sessions_file: str = _SESSIONS_FILE) -> None:
        self._users_file = users_file
        self._sessions_file = sessions_file
        self._users: dict[str, User] = {}
        self._sessions: dict[str, SessionToken] = {}
        self._api_tokens: dict[str, ApiToken] = {}
        self._grace_tokens: dict[str, float] = {}  # token -> grace_until_ts
        os.makedirs(os.path.dirname(self._users_file) or ".", exist_ok=True)
        os.makedirs(os.path.dirname(self._sessions_file) or ".", exist_ok=True)
        self._load()
        self._ensure_admin()

    def _ensure_admin(self) -> None:
        if "admin" not in self._users:
            h, s = _hash_password("bluedeer888")
            self._users["admin"] = User(
                username="admin", password_hash=h, password_salt=s,
                role="admin", display_name="管理员",
            )
            self._save_users()

    def authenticate(self, username: str, password: str) -> SessionToken | None:
        user = self._users.get(username)
        if not user or not user.enabled:
            return None
        h, _ = _hash_password(password, user.password_salt)
        if h != user.password_hash:
            return None
        token = SessionToken(token=_generate_token(), username=username, role=user.role)
        self._sessions[token.token] = token
        user.last_login = time.time()
        self._save_users()
        self._save_sessions()
        return token

    def authenticate_api(self, token_str: str) -> User | None:
        token = self._api_tokens.get(token_str)
        if not token:
            return None
        # 正常 enabled token
        if token.enabled:
            user = self._users.get(token.username)
            if not user or not user.enabled:
                return None
            token.last_used = time.time()
            self._save_users()
            return user
        # 已停用的 token：检查 grace 期
        grace_until = self._grace_tokens.get(token_str, 0)
        if time.time() < grace_until:
            user = self._users.get(token.username)
            if not user or not user.enabled:
                return None
            return user
        return None

    def get_session(self, token_str: str) -> SessionToken | None:
        s = self._sessions.get(token_str)
        if not s:
            return None
        if time.time() > s.expires_at:
            del self._sessions[token_str]
            self._save_sessions()
            return None
        return s

    def logout(self, token_str: str) -> None:
        self._sessions.pop(token_str, None)
        self._save_sessions()

    def create_user(self, username: str, password: str, role: str = "viewer",
                    display_name: str = "", email: str = "") -> User:
        if username in self._users:
            raise ValueError(f"用户 {username} 已存在")
        if role not in VALID_ROLES:
            raise ValueError(f"无效角色: {role}")
        h, s = _hash_password(password)
        user = User(username=username, password_hash=h, password_salt=s,
                     role=role, display_name=display_name or username, email=email)
        self._users[username] = user
        self._save_users()
        return user

    def update_user(self, username: str, *, role: str | None = None,
                    display_name: str | None = None, email: str | None = None,
                    enabled: bool | None = None, password: str | None = None) -> bool:
        user = self._users.get(username)
        if not user:
            return False
        if role is not None:
            if role not in VALID_ROLES:
                return False
            user.role = role
        if display_name is not None:
            user.display_name = display_name
        if email is not None:
            user.email = email
        if enabled is not None:
            user.enabled = enabled
        if password is not None:
            h, s = _hash_password(password)
            user.password_hash = h
            user.password_salt = s
        self._save_users()
        return True

    def delete_user(self, username: str) -> bool:
        if username == "admin":
            return False
        if username in self._users:
            del self._users[username]
            # 清理该用户的 API token
            self._api_tokens = {k: v for k, v in self._api_tokens.items() if v.username != username}
            self._save_users()
            self._save_sessions()
            return True
        return False

    def list_users(self) -> list[dict[str, Any]]:
        return [
            {"username": u.username, "role": u.role, "display_name": u.display_name,
             "email": u.email, "enabled": u.enabled, "created_at": u.created_at,
             "last_login": u.last_login}
            for u in self._users.values()
        ]

    def get_user(self, username: str) -> User | None:
        return self._users.get(username)

    def create_api_token(self, username: str, name: str) -> ApiToken:
        if username not in self._users:
            raise ValueError(f"用户 {username} 不存在")
        token_str = _generate_token()
        at = ApiToken(token=token_str, name=name, username=username)
        self._api_tokens[token_str] = at
        self._save_users()
        return at

    def list_api_tokens(self, username: str = "") -> list[dict[str, Any]]:
        tokens = self._api_tokens.values()
        if username:
            tokens = [t for t in tokens if t.username == username]
        return [
            {"token": t.token[:12] + "...", "name": t.name, "username": t.username,
             "created_at": t.created_at, "last_used": t.last_used, "enabled": t.enabled}
            for t in tokens
        ]

    # ---- JWT 刷新 + API Key 轮换 ----

    def refresh_token(self, expired_token: str) -> SessionToken | None:
        """JWT 风格 token 刷新：用过期但可识别的 token 换取新 token。

        校验旧 token 的 username/role 信息仍然有效，颁发新 SessionToken。
        旧 token 被删除。
        """
        s = self._sessions.get(expired_token)
        if not s:
            return None
        # 只要用户仍然存在且启用，就允许刷新
        user = self._users.get(s.username)
        if not user or not user.enabled:
            return None
        # 删除旧 token，颁发新 token
        del self._sessions[expired_token]
        new_token = SessionToken(
            token=_generate_token(),
            username=s.username,
            role=s.role,
        )
        self._sessions[new_token.token] = new_token
        self._save_sessions()
        return new_token

    def rotate_api_key(self, old_key: str, grace_sec: int = 86400) -> ApiToken | None:
        """轮换 API Key：生成新 key 并保留旧 key 在 grace 期内仍有效。

        将旧 key 标记 enabled=False 并注册 grace 期，
        grace 期内 authenticate_api 仍然放行旧 key。
        返回新 ApiToken（含新 token 串）。
        """
        old = self._api_tokens.get(old_key)
        if not old:
            # 前缀匹配
            for k, v in list(self._api_tokens.items()):
                if k.startswith(old_key):
                    old = v
                    old_key = k
                    break
        if not old:
            return None
        # 旧 key 停用 + 注册 grace 期
        old.enabled = False
        self._grace_tokens[old_key] = time.time() + grace_sec
        # 创建新 key
        new_token_str = _generate_token()
        new_at = ApiToken(
            token=new_token_str,
            name=old.name,
            username=old.username,
        )
        self._api_tokens[new_token_str] = new_at
        self._save_users()
        logger.info("API Key 轮换: %s -> %s (grace=%ds)", old_key[:12], new_token_str[:12], grace_sec)
        return new_at

    def revoke_api_token(self, token_str: str) -> bool:
        if token_str in self._api_tokens:
            del self._api_tokens[token_str]
            self._save_users()
            return True
        # 支持用前缀匹配
        for k in list(self._api_tokens.keys()):
            if k.startswith(token_str):
                del self._api_tokens[k]
                self._save_users()
                return True
        return False

    def check_permission(self, username: str, required_role: str) -> bool:
        user = self._users.get(username)
        if not user or not user.enabled:
            return False
        return ROLE_HIERARCHY.get(user.role, 0) >= ROLE_HIERARCHY.get(required_role, 0)

    def _load(self) -> None:
        self._load_users()
        self._load_sessions()

    def _load_users(self) -> None:
        try:
            if os.path.exists(self._users_file):
                with open(self._users_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                            u = User(**d)
                            self._users[u.username] = u
                            # 加载 API token
                            for t in d.get("api_tokens", []):
                                at = ApiToken(**t)
                                self._api_tokens[at.token] = at
                        except Exception:
                            continue
        except Exception as e:
            logger.warning("加载用户数据失败: %s", e)

    def _load_sessions(self) -> None:
        try:
            if os.path.exists(self._sessions_file):
                with open(self._sessions_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            s = SessionToken(**json.loads(line))
                            if time.time() < s.expires_at:
                                self._sessions[s.token] = s
                        except Exception:
                            continue
        except Exception as e:
            logger.warning("加载会话数据失败: %s", e)

    def _save_users(self) -> None:
        try:
            with open(self._users_file, "w", encoding="utf-8") as f:
                for u in self._users.values():
                    d = asdict(u)
                    d["api_tokens"] = [
                        {"token": at.token, "name": at.name, "username": at.username,
                         "created_at": at.created_at, "last_used": at.last_used, "enabled": at.enabled}
                        for at in self._api_tokens.values() if at.username == u.username
                    ]
                    f.write(json.dumps(d, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("保存用户数据失败: %s", e)

    def _save_sessions(self) -> None:
        try:
            with open(self._sessions_file, "w", encoding="utf-8") as f:
                for s in self._sessions.values():
                    f.write(json.dumps(asdict(s), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("保存会话数据失败: %s", e)


# 全局单例
_auth: AuthSystem | None = None


def get_auth() -> AuthSystem:
    global _auth
    if _auth is None:
        _auth = AuthSystem()
    return _auth


def role_required(required_role: str):
    """路由级权限装饰器（用法：装饰 API 路由函数）。
    要求 request.state 中已设置 user 和 role。
    """
    from functools import wraps

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 找 request 参数
            request = None
            for arg in args:
                if hasattr(arg, "state") and hasattr(arg.state, "user"):
                    request = arg
                    break
            if not request:
                for _, v in kwargs.items():
                    if hasattr(v, "state") and hasattr(v.state, "user"):
                        request = v
                        break
            if not request or not request.state.user:
                from fastapi.responses import JSONResponse
                return JSONResponse({"error": "未认证"}, status_code=401)
            if ROLE_HIERARCHY.get(request.state.role, 0) < ROLE_HIERARCHY.get(required_role, 0):
                from fastapi.responses import JSONResponse
                return JSONResponse({"error": "权限不足"}, status_code=403)
            return await func(*args, **kwargs)
        return wrapper
    return decorator
