# 自动拆分自 web_server.py（路由域: admin）
import logging

logger = logging.getLogger(__name__)
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from web_server.app import (
    ADMIN_AUTH_ENABLED,
    LOGIN_HTML,
    app,
)

router = APIRouter()


@router.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request) -> str:
    return LOGIN_HTML


@router.post("/admin/login")
async def admin_login(request: Request) -> HTMLResponse:
    form = await request.form()
    u, p = form.get("username", ""), form.get("password", "")
    from core.auth import get_auth

    session = get_auth().authenticate(u, p)
    if session:
        resp = RedirectResponse(url="/admin", status_code=302)
        resp.set_cookie(
            key="bluedeer_token",
            value=session.token,
            max_age=86400,
            httponly=True,
            secure=True,  # 生产环境必须部署 HTTPS，否则浏览器不会发送 secure cookie
        )
        return resp
    return HTMLResponse(
        content=LOGIN_HTML.replace(
            '<div id="error" class="error"></div>',
            '<div class="error">用户名或密码错误</div>',
        )
    )


@router.get("/admin/logout")
async def admin_logout(request: Request) -> RedirectResponse:
    token = request.cookies.get("bluedeer_token", "")
    if token:
        from core.auth import get_auth

        get_auth().logout(token)
    resp = RedirectResponse(url="/admin/login", status_code=302)
    resp.delete_cookie("bluedeer_token")
    return resp


if ADMIN_AUTH_ENABLED:

    @app.middleware("http")
    async def admin_auth_middleware(request: Request, call_next):
        path = request.url.path
        if path.startswith("/admin") and path not in ("/admin/login", "/admin/logout"):
            token = request.cookies.get("bluedeer_token", "")
            from core.auth import get_auth

            session = get_auth().get_session(token)
            if not session:
                return RedirectResponse(url="/admin/login", status_code=302)
            request.state.user = session.username
            request.state.role = session.role
        return await call_next(request)


# ── 用户管理 API ──


def _require_role(role: str, request: Request) -> bool:
    from core.auth import ROLE_HIERARCHY

    user_role = getattr(request.state, "role", "viewer")
    return ROLE_HIERARCHY.get(user_role, 0) >= ROLE_HIERARCHY.get(role, 0)
