# 自动拆分自 web_server.py（路由域: users）
import logging
# ruff: noqa: F821

logger = logging.getLogger(__name__)
from fastapi import APIRouter

router = APIRouter()


@router.get("/api/users")
async def list_users(request: Request) -> dict[str, Any]:
    from core.auth import get_auth

    return {"users": get_auth().list_users()}


@router.post("/api/users")
async def create_user(request: Request) -> dict[str, Any]:
    if not _require_role("admin", request):
        return {"ok": False, "error": "权限不足"}
    from core.auth import get_auth

    body = await request.json()
    try:
        get_auth().create_user(
            username=body["username"],
            password=body["password"],
            role=body.get("role", "viewer"),
            display_name=body.get("display_name", ""),
            email=body.get("email", ""),
        )
        return {"ok": True}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


@router.put("/api/users/{username}")
async def update_user(username: str, request: Request) -> dict[str, Any]:
    if not _require_role("admin", request):
        return {"ok": False, "error": "权限不足"}
    from core.auth import get_auth

    body = await request.json()
    ok = get_auth().update_user(
        username, **{k: v for k, v in body.items() if v is not None}
    )
    return {"ok": ok}


@router.delete("/api/users/{username}")
async def delete_user(username: str, request: Request) -> dict[str, Any]:
    if not _require_role("admin", request):
        return {"ok": False, "error": "权限不足"}
    from core.auth import get_auth

    ok = get_auth().delete_user(username)
    return {"ok": ok}


@router.get("/api/users/tokens")
async def list_tokens(request: Request) -> dict[str, Any]:
    from core.auth import get_auth

    username = request.state.user if hasattr(request.state, "user") else ""
    return {"tokens": get_auth().list_api_tokens(username)}


@router.post("/api/users/tokens")
async def create_token(request: Request) -> dict[str, Any]:
    from core.auth import get_auth

    body = await request.json()
    username = request.state.user if hasattr(request.state, "user") else "admin"
    token = get_auth().create_api_token(username, body.get("name", "default"))
    return {"ok": True, "token": token.token}


@router.delete("/api/users/tokens/{token_str}")
async def revoke_token(token_str: str, request: Request) -> dict[str, Any]:
    from core.auth import get_auth

    ok = get_auth().revoke_api_token(token_str)
    return {"ok": ok}


# ── 系统健康 API ──
