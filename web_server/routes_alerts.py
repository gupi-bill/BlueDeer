# 自动拆分自 web_server.py（路由域: alerts）
from fastapi import APIRouter

router = APIRouter()


@router.get("/api/alerts/rules")
async def alert_rules() -> dict[str, Any]:
    from core.alert import get_alert_engine

    return {"rules": get_alert_engine().list_rules()}


@router.post("/api/alerts/rules")
async def alert_add_rule(request: Request) -> dict[str, Any]:
    from core.alert import AlertRule, get_alert_engine

    body = await request.json()
    rule = AlertRule(**body)
    get_alert_engine().add_rule(rule)
    return {"ok": True, "rule_id": rule.id}


@router.delete("/api/alerts/rules/{rule_id}")
async def alert_remove_rule(rule_id: str) -> dict[str, Any]:
    from core.alert import get_alert_engine

    ok = get_alert_engine().remove_rule(rule_id)
    return {"ok": ok}


@router.get("/api/alerts/events")
async def alert_events(limit: int = 50) -> dict[str, Any]:
    from core.alert import get_alert_engine

    return {"events": get_alert_engine().recent_alerts(limit=min(limit, 200))}


@router.post("/api/alerts/acknowledge/{rule_id}")
async def alert_acknowledge(rule_id: str) -> dict[str, Any]:
    from core.alert import get_alert_engine

    get_alert_engine().acknowledge(rule_id)
    return {"ok": True}


# ── Agent 市场 ──
