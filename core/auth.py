"""用户认证 + 角色权限（RBAC）系统（企业版）。

数据模型：
    - User：用户名、bcrypt 密码哈希、五级角色、状态、强制改密标记
    - Role：superadmin(5) / admin(4) / operator(3) / viewer(2) / guest(1)
    - SessionToken：登录会话管理（SQLite 持久化，断点续用）
存储：data/iam.db（SQLite），首次启动自动从 logs/users.jsonl 迁移（旧密码失效，强制改密）
兼容说明：保留 AuthSystem / get_auth / role_required / ROLE_HIERARCHY /
VALID_ROLES / User / ApiToken / SessionToken 公共接口。
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger("bluedeer.auth")

_DB_FILE = "data/iam.db"
_LEGACY_USERS_FILE = "logs/users.jsonl"

ROLE_HIERARCHY = {
    "superadmin": 5,
    "admin": 4,
    "operator": 3,
    "viewer": 2,
    "guest": 1,
}
VALID_ROLES = tuple(ROLE_HIERARCHY.keys())

_LOGIN_MAX_FAILURES = 5
_LOGIN_LOCK_SECONDS = 15 * 60
_SESSION_TTL = 24 * 60 * 60
_SESSION_REFRESH_THRESHOLD = 6 * 60 * 60
_WEAK_PASSWORD_MIN = 8

try:
    import bcrypt as _bcrypt
    _HAS_BCRYPT = True
except Exception:
    _bcrypt = None
    _HAS_BCRYPT = False


@dataclass
class User:
    username: str
    password_hash: str
    role: str = "viewer"
    display_name: str = ""
    email: str = ""
    enabled: bool = True
    must_change_password: bool = False
    created_at: float = field(default_factory=time.time)
    last_login: float = 0.0

    def to_dict(self):
        return {
            "username": self.username, "role": self.role,
            "display_name": self.display_name, "email": self.email,
            "enabled": self.enabled,
            "must_change_password": self.must_change_password,
            "created_at": self.created_at, "last_login": self.last_login,
        }


@dataclass
class ApiToken:
    token: str
    name: str
    username: str
    created_at: float = field(default_factory=time.time)
    last_used: float = 0.0
    enabled: bool = True


@dataclass
class SessionToken:
    token: str
    username: str
    role: str = "viewer"
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + _SESSION_TTL)

    def to_dict(self):
        return {
            "token": self.token, "username": self.username, "role": self.role,
            "created_at": self.created_at, "expires_at": self.expires_at,
        }


def _hash_password(password: str) -> str:
    if _HAS_BCRYPT:
        return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("ascii")
    import hashlib
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return "PBKDF2:sha256:200000:$%s$%s" % (salt, h.hex())


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        if password_hash.startswith("PBKDF2:"):
            import hashlib
            _, algo, iterations, rest = password_hash.split(":", 3)
            salt, hx = rest.split("$", 1)
            h = hashlib.pbkdf2_hmac(algo, password.encode(), salt.encode(), int(iterations))
            return secrets.compare_digest(h.hex(), hx)
        if _HAS_BCRYPT:
            return _bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except Exception:
        return False
    return False


def is_weak_password(password: str) -> bool:
    if len(password) < _WEAK_PASSWORD_MIN:
        return True
    cat = 0
    if any(c.islower() for c in password): cat += 1
    if any(c.isupper() for c in password): cat += 1
    if any(c.isdigit() for c in password): cat += 1
    if any(not c.isalnum() for c in password): cat += 1
    return cat < 2


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


# 内存滑动窗口限流：同窗口内失败次数过多即拒绝（独立于 DB 锁定的第二道防线）
_LOGIN_RATE_LIMIT_WINDOW = 60
_LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 20
_login_attempts: dict[str, list[float]] = {}


def _check_login_rate_limit(username: str) -> tuple[bool, float]:
    now = time.time()
    attempts = [t for t in _login_attempts.get(username, []) if now - t < _LOGIN_RATE_LIMIT_WINDOW]
    _login_attempts[username] = attempts
    if len(attempts) >= _LOGIN_RATE_LIMIT_MAX_ATTEMPTS:
        return False, _LOGIN_RATE_LIMIT_WINDOW - (now - attempts[0])
    return True, 0.0


def _record_attempt(username: str) -> None:
    _login_attempts.setdefault(username, []).append(time.time())


class AuthSystem:
    def __init__(self, db_file: str = _DB_FILE, legacy_users_file: str = _LEGACY_USERS_FILE) -> None:
        self._db_file = db_file
        self._legacy_users_file = legacy_users_file
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(db_file) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_file, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._migrate_legacy()
        self._ensure_admin()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'viewer',
                    display_name TEXT NOT NULL DEFAULT '',
                    email TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    must_change_password INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL DEFAULT 0,
                    last_login REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_username ON sessions(username);
                CREATE TABLE IF NOT EXISTS api_tokens (
                    token TEXT PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT '',
                    username TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_used REAL NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS login_failures (
                    username TEXT PRIMARY KEY,
                    fail_count INTEGER NOT NULL DEFAULT 0,
                    first_fail_at REAL NOT NULL DEFAULT 0,
                    locked_until REAL NOT NULL DEFAULT 0
                );
                """
            )

    def _migrate_legacy(self) -> None:
        if not os.path.exists(self._legacy_users_file):
            return
        cur = self._conn.execute("SELECT COUNT(*) AS c FROM users")
        if cur.fetchone()["c"] > 0:
            return
        imported = 0
        try:
            with open(self._legacy_users_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    username = obj.get("username", "")
                    if not username:
                        continue
                    role = obj.get("role", "viewer")
                    if role not in VALID_ROLES:
                        role = "viewer"
                    self._conn.execute(
                        "INSERT OR IGNORE INTO users"
                        "(username, password_hash, role, display_name, email,"
                        " enabled, must_change_password, created_at, last_login)"
                        " VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?)",
                        (username, "LEGACY:" + str(obj.get("password_hash", "")),
                         role, obj.get("display_name", username),
                         obj.get("email", ""),
                         float(obj.get("created_at", time.time())),
                         float(obj.get("last_login", 0))),
                    )
                    imported += 1
            self._conn.commit()
        except OSError as e:
            logger.warning("旧用户迁移失败: %s", e)
        if imported:
            logger.info("已迁移 %d 个旧用户（旧密码失效，需强制改密）", imported)
            try:
                os.replace(self._legacy_users_file, self._legacy_users_file + ".migrated")
            except OSError:
                pass

    def _ensure_admin(self) -> None:
        cur = self._conn.execute("SELECT 1 FROM users WHERE username='admin' LIMIT 1")
        if cur.fetchone():
            return
        self._conn.execute(
            "INSERT INTO users"
            "(username, password_hash, role, display_name, email, enabled,"
            " must_change_password, created_at, last_login)"
            " VALUES ('admin', ?, 'superadmin', '超级管理员', '', 1, 1, ?, 0)",
            (_hash_password("bluedeer888"), time.time()),
        )
        self._conn.commit()
        logger.warning("已创建默认超级管理员 admin（初始密码 bluedeer888，首次登录必须改密）")

    def create_user(self, username, password, role="viewer", display_name="", email=""):
        username = username.strip()
        if not username:
            raise ValueError("用户名不能为空")
        if role not in VALID_ROLES:
            raise ValueError("无效角色: %s" % role)
        if is_weak_password(password):
            raise ValueError("密码强度不足：至少 %d 位，且包含两类字符" % _WEAK_PASSWORD_MIN)
        with self._lock, self._conn:
            cur = self._conn.execute("SELECT 1 FROM users WHERE username=?", (username,))
            if cur.fetchone():
                raise ValueError("用户 %s 已存在" % username)
            now = time.time()
            self._conn.execute(
                "INSERT INTO users"
                "(username, password_hash, role, display_name, email, enabled,"
                " must_change_password, created_at, last_login)"
                " VALUES (?, ?, ?, ?, ?, 1, 1, ?, 0)",
                (username, _hash_password(password), role,
                 display_name or username, email, now),
            )
        return self.get_user(username)

    def update_user(self, username, *, role=None, display_name=None, email=None, enabled=None, password=None):
        user = self.get_user(username)
        if not user:
            return False
        if role is not None and role not in VALID_ROLES:
            return False
        if password is not None and is_weak_password(password):
            return False
        with self._lock, self._conn:
            if role is not None:
                self._conn.execute("UPDATE users SET role=? WHERE username=?", (role, username))
            if display_name is not None:
                self._conn.execute("UPDATE users SET display_name=? WHERE username=?", (display_name, username))
            if email is not None:
                self._conn.execute("UPDATE users SET email=? WHERE username=?", (email, username))
            if enabled is not None:
                self._conn.execute("UPDATE users SET enabled=? WHERE username=?", (1 if enabled else 0, username))
            if password is not None:
                self._conn.execute(
                    "UPDATE users SET password_hash=?, must_change_password=0 WHERE username=?",
                    (_hash_password(password), username))
                self._conn.execute("DELETE FROM login_failures WHERE username=?", (username,))
                self._conn.execute("DELETE FROM sessions WHERE username=?", (username,))
        return True

    def delete_user(self, username):
        if username == "admin":
            return False
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM users WHERE username=?", (username,))
            deleted = cur.rowcount > 0
            self._conn.execute("DELETE FROM sessions WHERE username=?", (username,))
            self._conn.execute("DELETE FROM api_tokens WHERE username=?", (username,))
            self._conn.execute("DELETE FROM login_failures WHERE username=?", (username,))
        return deleted

    def list_users(self):
        rows = self._conn.execute("SELECT * FROM users ORDER BY created_at ASC").fetchall()
        return [
            {
                "username": r["username"], "role": r["role"],
                "display_name": r["display_name"], "email": r["email"],
                "enabled": bool(r["enabled"]),
                "must_change_password": bool(r["must_change_password"]),
                "created_at": r["created_at"], "last_login": r["last_login"],
            }
            for r in rows
        ]

    def get_user(self, username):
        row = self._conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not row:
            return None
        return User(
            username=row["username"], password_hash=row["password_hash"],
            role=row["role"], display_name=row["display_name"], email=row["email"],
            enabled=bool(row["enabled"]),
            must_change_password=bool(row["must_change_password"]),
            created_at=row["created_at"], last_login=row["last_login"],
        )

    def _is_locked(self, username):
        row = self._conn.execute(
            "SELECT locked_until FROM login_failures WHERE username=?", (username,)).fetchone()
        if not row:
            return False, 0
        locked_until = row["locked_until"]
        if locked_until > 0:
            remaining = int(locked_until - time.time())
            if remaining > 0:
                return True, remaining
            with self._lock, self._conn:
                self._conn.execute("DELETE FROM login_failures WHERE username=?", (username,))
        return False, 0

    def _record_failure(self, username):
        now = time.time()
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT fail_count, first_fail_at FROM login_failures WHERE username=?",
                (username,)).fetchone()
            if not row:
                self._conn.execute(
                    "INSERT INTO login_failures(username, fail_count, first_fail_at, locked_until)"
                    " VALUES (?, 1, ?, 0)", (username, now))
            else:
                count = row["fail_count"] + 1
                if count >= _LOGIN_MAX_FAILURES:
                    self._conn.execute(
                        "UPDATE login_failures SET fail_count=?, locked_until=? WHERE username=?",
                        (count, now + _LOGIN_LOCK_SECONDS, username))
                    logger.warning("用户 %s 连续登录失败 %d 次，已锁定 15 分钟", username, count)
                else:
                    first = row["first_fail_at"] or now
                    self._conn.execute(
                        "UPDATE login_failures SET fail_count=?, first_fail_at=? WHERE username=?",
                        (count, first, username))

    def _clear_failures(self, username):
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM login_failures WHERE username=?", (username,))

    def authenticate(self, username, password):
        user = self.get_user(username)
        if not user or not user.enabled:
            return None
        allowed, _ = _check_login_rate_limit(username)
        if not allowed:
            logger.warning("用户 %s 触发登录限流，拒绝登录", username)
            return None
        _record_attempt(username)
        locked, _ = self._is_locked(username)
        if locked:
            logger.warning("用户 %s 处于锁定状态，拒绝登录", username)
            return None
        if user.password_hash.startswith("LEGACY:"):
            return None
        if not _verify_password(password, user.password_hash):
            self._record_failure(username)
            return None
        self._clear_failures(username)
        _login_attempts.pop(username, None)
        token = SessionToken(token=_generate_token(), username=username, role=user.role)
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO sessions(token, username, role, created_at, expires_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (token.token, token.username, token.role, token.created_at, token.expires_at))
            self._conn.execute("UPDATE users SET last_login=? WHERE username=?", (time.time(), username))
        return token

    def get_session(self, token_str):
        row = self._conn.execute("SELECT * FROM sessions WHERE token=?", (token_str,)).fetchone()
        if not row:
            return None
        if time.time() > row["expires_at"]:
            with self._lock, self._conn:
                self._conn.execute("DELETE FROM sessions WHERE token=?", (token_str,))
            return None
        return SessionToken(
            token=row["token"], username=row["username"], role=row["role"],
            created_at=row["created_at"], expires_at=row["expires_at"])

    def logout(self, token_str):
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM sessions WHERE token=?", (token_str,))

    def refresh_token(self, expired_token):
        row = self._conn.execute("SELECT * FROM sessions WHERE token=?", (expired_token,)).fetchone()
        if not row:
            return None
        now = time.time()
        if now > row["expires_at"] + _SESSION_REFRESH_THRESHOLD:
            return None
        token = SessionToken(token=_generate_token(), username=row["username"], role=row["role"])
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM sessions WHERE token=?", (expired_token,))
            self._conn.execute(
                "INSERT INTO sessions(token, username, role, created_at, expires_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (token.token, token.username, token.role, token.created_at, token.expires_at))
        return token

    def change_password(self, username, old_password, new_password):
        user = self.get_user(username)
        if not user:
            return False, "用户不存在"
        if not user.password_hash.startswith("LEGACY:"):
            if not _verify_password(old_password, user.password_hash):
                return False, "旧密码错误"
        if is_weak_password(new_password):
            return False, "新密码强度不足：至少 %d 位，且包含两类字符" % _WEAK_PASSWORD_MIN
        if _verify_password(new_password, user.password_hash):
            return False, "新密码不能与旧密码相同"
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE users SET password_hash=?, must_change_password=0 WHERE username=?",
                (_hash_password(new_password), username))
            self._conn.execute("DELETE FROM login_failures WHERE username=?", (username,))
            self._conn.execute("DELETE FROM sessions WHERE username=?", (username,))
        return True, "密码修改成功"

    def create_api_token(self, username, name):
        token = ApiToken(token="bd_" + _generate_token(), name=name or "default", username=username)
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO api_tokens(token, name, username, created_at, last_used, enabled)"
                " VALUES (?, ?, ?, ?, 0, 1)",
                (token.token, token.name, token.username, token.created_at))
        return token

    def list_api_tokens(self, username=""):
        if username:
            rows = self._conn.execute(
                "SELECT * FROM api_tokens WHERE username=? ORDER BY created_at DESC", (username,)).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM api_tokens ORDER BY created_at DESC").fetchall()
        return [
            {
                "token": r["token"], "name": r["name"], "username": r["username"],
                "created_at": r["created_at"], "last_used": r["last_used"],
                "enabled": bool(r["enabled"]),
            }
            for r in rows
        ]

    def authenticate_api(self, token_str):
        row = self._conn.execute(
            "SELECT * FROM api_tokens WHERE token=? AND enabled=1", (token_str,)).fetchone()
        if not row:
            return None
        user = self.get_user(row["username"])
        if not user or not user.enabled:
            return None
        with self._lock, self._conn:
            self._conn.execute("UPDATE api_tokens SET last_used=? WHERE token=?", (time.time(), token_str))
        return user

    def revoke_api_token(self, token_str):
        with self._lock, self._conn:
            cur = self._conn.execute("UPDATE api_tokens SET enabled=0 WHERE token=?", (token_str,))
        return cur.rowcount > 0

    def check_permission(self, username, required_role):
        user = self.get_user(username)
        if not user or not user.enabled:
            return False
        if user.must_change_password:
            return False
        return ROLE_HIERARCHY.get(user.role, 0) >= ROLE_HIERARCHY.get(required_role, 0)

    def role_of(self, username):
        user = self.get_user(username)
        return user.role if user else "guest"


_auth_singleton = None
_auth_lock = threading.Lock()


def get_auth():
    global _auth_singleton
    with _auth_lock:
        if _auth_singleton is None:
            _auth_singleton = AuthSystem()
        return _auth_singleton


def role_required(required_role):
    def decorator(func):
        import functools

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            from fastapi import Request
            from fastapi.responses import JSONResponse

            request = kwargs.get("request")
            if request is None:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
            if request is None:
                return JSONResponse({"error": "无法获取请求上下文"}, status_code=401)
            token = request.cookies.get("bluedeer_token", "")
            session = get_auth().get_session(token) if token else None
            if not session:
                return JSONResponse({"error": "未登录"}, status_code=401)
            if not get_auth().check_permission(session.username, required_role):
                return JSONResponse({"error": "权限不足"}, status_code=403)
            request.state.user = session.username
            request.state.role = session.role
            return await func(*args, **kwargs)

        return wrapper

    return decorator
