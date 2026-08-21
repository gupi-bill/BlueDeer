# 自动拆分自 web_server.py（路由域: dag）
import logging

# ruff: noqa: F821

logger = logging.getLogger(__name__)
from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/dag/nodes")
async def dag_list_nodes() -> dict[str, Any]:
    from core.task_dag import TaskDAG

    dag = TaskDAG()
    nodes = dag.list_nodes()
    return {
        "nodes": [
            {
                "id": n.id,
                "depends_on": n.depends_on,
                "description": n.description,
                "metadata": n.metadata,
            }
            for n in nodes
        ],
        "total": len(nodes),
        "has_cycle": dag.detect_cycle() is not None,
    }


@router.post("/api/dag/nodes")
async def dag_add_node(body: dict[str, Any]) -> dict[str, Any]:
    from core.task_dag import TaskDAG

    dag = TaskDAG()
    node = dag.add_node(
        body["id"],
        depends_on=body.get("depends_on", []),
        description=body.get("description", ""),
        metadata=body.get("metadata", {}),
    )
    dag.save()
    return {
        "success": True,
        "node": {
            "id": node.id,
            "depends_on": node.depends_on,
            "description": node.description,
        },
    }


@router.put("/api/dag/nodes/{node_id}")
async def dag_update_node(node_id: str, body: dict[str, Any]) -> dict[str, Any]:
    from core.task_dag import TaskDAG

    dag = TaskDAG()
    existing = dag.get_node(node_id)
    if not existing:
        return {"success": False, "error": f"节点 {node_id} 未找到"}
    node = dag.add_node(
        node_id,
        depends_on=body.get("depends_on", existing.depends_on),
        description=body.get("description", existing.description),
        metadata=body.get("metadata", existing.metadata),
    )
    dag.save()
    return {
        "success": True,
        "node": {
            "id": node.id,
            "depends_on": node.depends_on,
            "description": node.description,
        },
    }


@router.delete("/api/dag/nodes/{node_id}")
async def dag_delete_node(node_id: str) -> dict[str, Any]:
    from core.task_dag import TaskDAG

    dag = TaskDAG()
    ok = dag.remove_node(node_id)
    if ok:
        dag.save()
    return {"success": ok}


@router.post("/api/dag/auto-layout")
async def dag_auto_layout() -> dict[str, Any]:
    from core.task_dag import TaskDAG

    dag = TaskDAG()
    plan = dag.execution_plan()
    dag.list_nodes()
    layout = {}
    y_offset = 80
    for layer_idx, layer in enumerate(plan):
        x_offset = 60
        for node_id in layer:
            layout[node_id] = {"x": x_offset, "y": y_offset}
            x_offset += 220
        y_offset += 120
    return {"layout": layout, "layers": plan}


@router.get("/api/dag/plan")
async def dag_plan() -> dict[str, Any]:
    from core.task_dag import TaskDAG

    dag = TaskDAG()
    try:
        plan = dag.execution_plan()
    except ValueError as e:
        return {"error": str(e), "plan": []}
    return {"plan": plan, "total_layers": len(plan)}


# ── Gantt ──


@router.get("/api/gantt")
async def gantt_data(max_bars: int = 50) -> dict[str, Any]:
    from core.gantt import GanttFormatter, GanttGenerator

    gen = GanttGenerator()
    try:
        from core.scheduler import Scheduler

        sched = Scheduler()
        jobs = sched.list_jobs()
        sched_data = {
            jid: {"cron": j.cron, "task_type": j.task_type, "enabled": j.enabled}
            for jid, j in jobs.items()
        }
    except Exception:
        sched_data = {}
    try:
        from core.harness import Harness

        h = Harness()
        agg = h.aggregate()
    except Exception:
        agg = None
    gantt = gen.generate(
        harness_aggregate=agg, scheduler_jobs=sched_data, since=time.time() - 3600
    )
    chart = GanttFormatter.to_chart_data(gantt, max_bars=max_bars)
    return chart


@router.get("/api/tasks/retry")
async def retry_status() -> dict[str, Any]:
    cfg = get_config().task
    active = {}
    try:
        from core.harness import Harness

        h = Harness()
        mgr = getattr(h, "_retry_mgr", None)
        if mgr:
            active = mgr.retry_summary()
    except Exception:
        logger.exception("Exception in block")
    return {
        "config": {
            "retry_enabled": cfg.retry_enabled,
            "retry_max_attempts": cfg.retry_max_attempts,
            "retry_base_delay": cfg.retry_base_delay,
            "retry_max_delay": cfg.retry_max_delay,
            "retry_jitter": cfg.retry_jitter,
            "max_reallocate": cfg.max_reallocate,
        },
        "active_retries": active,
    }


# ── DAG 模板 ──


@router.get("/api/dag-templates")
async def dag_templates_list(category: str = "") -> dict[str, Any]:
    from core.dag_templates import list_categories, list_templates

    cat = category or None
    return {
        "categories": list_categories(),
        "templates": list_templates(cat),
    }


@router.get("/api/dag-templates/{template_id}")
async def dag_templates_get(template_id: str) -> dict[str, Any]:
    from core.dag_templates import get_template

    t = get_template(template_id)
    if t is None:
        return {"error": "模板不存在"}
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "category": t.category,
        "nodes": t.nodes,
    }


@router.post("/api/dag-templates/{template_id}/apply")
async def dag_templates_apply(template_id: str) -> dict[str, Any]:
    from core.dag_templates import apply_template

    try:
        dag = apply_template(template_id, clear_existing=True)
        return {
            "ok": True,
            "node_count": len(dag.list_nodes()),
            "topological_order": dag.topological_sort(),
        }
    except ValueError as e:
        return {"error": str(e)}


# ── 审计日志 ──


@router.get("/api/audit")
async def audit_query(
    task_id: str = "",
    action: str = "",
    agent: str = "",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    from core.audit import get_audit_log

    log = get_audit_log()
    entries = log.query(
        task_id=task_id or None,
        action=action or None,
        agent=agent or None,
        limit=min(limit, 500),
        offset=offset,
    )
    summary = log.summary()
    return {"entries": entries, "summary": summary}


# ── 告警 ──
