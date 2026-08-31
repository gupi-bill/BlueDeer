"""PolicyEngine 单测。"""

from __future__ import annotations

from core.policy_engine import PolicyEngine


def test_create_and_assign_role() -> None:
    engine = PolicyEngine()
    engine.create_role("admin", permissions={"read", "write"})
    engine.assign_role("agent-1", "admin")
    assert "agent-1" in engine._agent_roles


def test_revoke_role() -> None:
    engine = PolicyEngine()
    engine.create_role("admin", permissions={"read"})
    engine.assign_role("agent-1", "admin")
    engine.revoke_role("agent-1")
    assert engine._agent_roles.get("agent-1") is None


def test_role_inheritance() -> None:
    engine = PolicyEngine()
    engine.create_role("base", permissions={"read"})
    engine.create_role("admin", permissions={"write"}, parent="base")
    engine.assign_role("agent-1", "admin")
    perms = engine.get_user_permissions("agent-1")
    assert "read" in perms
    assert "write" in perms


def test_grant_tool_access() -> None:
    engine = PolicyEngine()
    engine.grant("agent-1", "tool-a")
    assert engine.check_tool_access("agent-1", "tool-a").allowed is True


def test_deny_tool_access() -> None:
    engine = PolicyEngine()
    decision = engine.check_tool_access("agent-1", "tool-a")
    assert decision.allowed is False
    assert "无权调用" in decision.reason


def test_hazardous_tool_whitelist() -> None:
    engine = PolicyEngine()
    engine.allow_hazardous("danger-tool")
    assert engine.check_tool_access("agent-1", "danger-tool").allowed is True


def test_hazardous_tool_not_whitelisted() -> None:
    engine = PolicyEngine()
    decision = engine.check_tool_access("agent-1", "danger-tool")
    assert decision.allowed is False


def test_confirm_token_lifecycle() -> None:
    engine = PolicyEngine()
    token = engine.issue_confirm_token("test")
    assert engine.has_pending_confirm_tokens() == 1
    assert engine.revoke_confirm_token(token) is True
    assert engine.has_pending_confirm_tokens() == 0
    assert engine.revoke_confirm_token(token) is False


def test_to_dict_serialization() -> None:
    engine = PolicyEngine()
    engine.create_role("admin", permissions={"read"})
    engine.assign_role("agent-1", "admin")
    data = engine.to_dict()
    assert "roles" in data
    assert "agent_roles" in data
    assert data["agent_roles"]["agent-1"] == "admin"
