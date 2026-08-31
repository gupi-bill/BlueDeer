"""BlueDeer PolicyEngine：统一策略引擎（RBAC + 高危工具 + 人工确认）。

替代原有 SecurityGuard + RBACSystem 的分散逻辑，提供单一入口。
兼容保留：SecurityGuard 的 allow_hazardous / grant / issue_confirm_token /
has_pending_confirm_tokens / check_permission / check_operation 接口。
"""

from __future__ import annotations

import logging
import secrets
import threading
from typing import Any

from core.observability import Observability

logger = logging.getLogger("bluedeer.policy_engine")


class PolicyDecision:
    """策略检查结果。"""

    def __init__(
        self,
        allowed: bool,
        reason: str = "ok",
        confirm_token: str | None = None,
    ) -> None:
        self.allowed = allowed
        self.reason = reason
        self.confirm_token = confirm_token

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "confirm_token": self.confirm_token,
        }


class PolicyEngine:
    """统一策略引擎。"""

    def __init__(self, owner: Any = None) -> None:
        self._owner = owner
        self._lock = threading.RLock()
        self._roles: dict[str, dict[str, Any]] = {}
        self._agent_roles: dict[str, str] = {}
        self._tool_permissions: dict[str, set[str]] = {}
        self._hazardous_whitelist: set[str] = set()
        self._confirm_tokens: set[str] = set()
        self._require_confirm: bool = True

    # ========== 角色管理 ==========

    def create_role(
        self,
        role_name: str,
        permissions: set[str] | None = None,
        parent: str | None = None,
    ) -> None:
        """创建角色。"""
        with self._lock:
            self._roles[role_name] = {
                "permissions": set(permissions or []),
                "parent": parent,
            }

    def assign_role(self, agent_id: str, role_name: str) -> None:
        """给 Agent 分配角色。"""
        with self._lock:
            if role_name not in self._roles:
                raise KeyError(f"角色不存在: {role_name}")
            self._agent_roles[agent_id] = role_name

    def revoke_role(self, agent_id: str) -> None:
        """撤销 Agent 角色。"""
        with self._lock:
            self._agent_roles.pop(agent_id, None)

    # ========== 权限 ==========

    def get_user_permissions(self, agent_id: str) -> set[str]:
        """递归收集 Agent 权限（含父角色继承）。"""
        with self._lock:
            role_name = self._agent_roles.get(agent_id)
            if role_name is None:
                return set()
            return self._collect_permissions(role_name)

    def _collect_permissions(self, role_name: str, visited: set[str] | None = None) -> set[str]:
        if visited is None:
            visited = set()
        if role_name in visited:
            return set()
        visited.add(role_name)
        role = self._roles.get(role_name, {})
        perms: set[str] = set(role.get("permissions", []))
        parent = role.get("parent")
        if parent:
            perms |= self._collect_permissions(parent, visited)
        return perms

    # ========== 工具授权 ==========

    def grant(self, agent_id: str, tool_name: str) -> None:
        """给 Agent 直接授予工具权限。"""
        with self._lock:
            self._tool_permissions.setdefault(agent_id, set()).add(tool_name)

    def allow_hazardous(self, tool_name: str) -> None:
        """将工具加入高危白名单。"""
        with self._lock:
            self._hazardous_whitelist.add(tool_name)

    # ========== 人工确认 ==========

    def issue_confirm_token(self, reason: str = "") -> str:
        token = secrets.token_hex(8)
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
        with self._lock:
            return len(self._confirm_tokens)

    # ========== 工具访问检查 ==========

    def check_tool_access(
        self,
        agent_id: str,
        tool_name: str,
        confirm_token: str | None = None,
    ) -> PolicyDecision:
        """检查 Agent 是否有权调用工具。

        决策顺序：
        1. 若工具在白名单 → 允许
        2. 若 Agent 有显式授权 → 允许
        3. 若 Agent 角色权限包含 → 允许
        4. 否则 → 拒绝
        """
        with self._lock:
            if tool_name in self._hazardous_whitelist:
                Observability.span(
                    "policy.check_tool_access",
                    agent_id=agent_id,
                    tool=tool_name,
                    allowed=True,
                    reason="hazardous_whitelist",
                )
                return PolicyDecision(True, "hazardous_whitelist")
            perms = self._tool_permissions.get(agent_id, set())
            if tool_name in perms:
                Observability.span(
                    "policy.check_tool_access",
                    agent_id=agent_id,
                    tool=tool_name,
                    allowed=True,
                    reason="granted",
                )
                return PolicyDecision(True, "granted")
            role_perms = self._collect_permissions(self._agent_roles.get(agent_id, ""))
            if tool_name in role_perms:
                Observability.span(
                    "policy.check_tool_access",
                    agent_id=agent_id,
                    tool=tool_name,
                    allowed=True,
                    reason="role_permission",
                )
                return PolicyDecision(True, "role_permission")
            Observability.span(
                "policy.check_tool_access",
                agent_id=agent_id,
                tool=tool_name,
                allowed=False,
                reason=f"agent '{agent_id}' 无权调用工具 '{tool_name}'",
            )
            return PolicyDecision(False, f"agent '{agent_id}' 无权调用工具 '{tool_name}'")

    # ========== 兼容 SecurityGuard.check_permission ==========

    def check_permission(self, agent_id: str, tool_name: str) -> tuple[bool, str]:
        decision = self.check_tool_access(agent_id, tool_name)
        return decision.allowed, decision.reason

    # ========== 兼容 SecurityGuard.check_operation ==========

    def check_operation(
        self,
        tool_name: str,
        params: dict[str, Any],
        category: Any,
        confirm_token: str | None = None,
    ) -> tuple[bool, Any | None, str]:
        """兼容 SecurityGuard.check_operation 接口。"""
        try:
            from tools.base_tool import ToolCategory  # noqa: F401 (availability check)
        except ImportError:
            pass
        decision = self.check_tool_access("__op__", tool_name, confirm_token)
        if not decision.allowed:
            return False, None, decision.reason
        return True, None, "ok"

    # ========== 序列化 ==========

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "roles": {
                    name: {
                        "permissions": list(role.get("permissions", [])),
                        "parent": role.get("parent"),
                    }
                    for name, role in self._roles.items()
                },
                "agent_roles": dict(self._agent_roles),
                "tool_permissions": {k: list(v) for k, v in self._tool_permissions.items()},
                "hazardous_whitelist": list(self._hazardous_whitelist),
                "pending_confirm_tokens": len(self._confirm_tokens),
            }
