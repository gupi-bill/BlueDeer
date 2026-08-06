"""DAG 模板库：预置常用任务编排模式。

每个模板由 name, description, category 和 nodes（DAGNode dict 列表）组成。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.task_dag import TaskDAG


@dataclass
class TemplateParam:
    name: str
    default: Any = None
    param_type: str = "string"


@dataclass
class DAGTemplate:
    id: str
    name: str
    description: str
    category: str
    nodes: list[dict[str, Any]] = field(default_factory=list)
    parent_id: str = ""
    params: list[TemplateParam] = field(default_factory=list)

    def extend(self, template_name: str) -> None:
        """继承模板，复制其 nodes。"""
        parent = get_template(template_name)
        if parent is None:
            raise ValueError(f"模板不存在: {template_name}")
        self.parent_id = template_name
        self.nodes = [dict(n) for n in parent.nodes] + self.nodes
        self.params = list(parent.params) + self.params

    def add_param(
        self, name: str, default: Any = None, param_type: str = "string"
    ) -> None:
        """添加参数化变量。"""
        self.params.append(
            TemplateParam(name=name, default=default, param_type=param_type)
        )

    def render(self, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """渲染模板实例：用传入的 params 替换节点中的占位符。"""
        resolved = params or {}
        rendered: list[dict[str, Any]] = []
        for node in self.nodes:
            n = dict(node)
            for key, val in n.items():
                if isinstance(val, str):
                    for p in self.params:
                        placeholder = "{{" + p.name + "}}"
                        if placeholder in val:
                            n[key] = val.replace(
                                placeholder, str(resolved.get(p.name, p.default or ""))
                            )
            rendered.append(n)
        return rendered


_TEMPLATES: list[DAGTemplate] = []


def _t(
    tid: str,
    name: str,
    desc: str,
    cat: str,
    nodes: list[dict[str, Any]],
) -> DAGTemplate:
    t = DAGTemplate(id=tid, name=name, description=desc, category=cat, nodes=nodes)
    _TEMPLATES.append(t)
    return t


# ── 线性管道 ──

_t(
    "linear-3",
    "线性 3 步",
    "顺序执行：A → B → C，每步依赖上一步",
    "线性",
    [
        {
            "id": "fetch",
            "depends_on": [],
            "description": "获取原始数据",
            "metadata": {"type": "data_ingest", "icon": "📥"},
        },
        {
            "id": "process",
            "depends_on": ["fetch"],
            "description": "处理转换数据",
            "metadata": {"type": "transform", "icon": "⚙️"},
        },
        {
            "id": "store",
            "depends_on": ["process"],
            "description": "存储结果",
            "metadata": {"type": "output", "icon": "💾"},
        },
    ],
)

_t(
    "linear-5",
    "线性 5 步",
    "顺序执行五阶段：采集 → 清洗 → 分析 → 报告 → 归档",
    "线性",
    [
        {
            "id": "collect",
            "depends_on": [],
            "description": "数据采集",
            "metadata": {"type": "ingest", "icon": "📡"},
        },
        {
            "id": "clean",
            "depends_on": ["collect"],
            "description": "数据清洗",
            "metadata": {"type": "transform", "icon": "🧹"},
        },
        {
            "id": "analyze",
            "depends_on": ["clean"],
            "description": "数据分析",
            "metadata": {"type": "analysis", "icon": "🔬"},
        },
        {
            "id": "report",
            "depends_on": ["analyze"],
            "description": "生成报告",
            "metadata": {"type": "output", "icon": "📝"},
        },
        {
            "id": "archive",
            "depends_on": ["report"],
            "description": "归档结果",
            "metadata": {"type": "archive", "icon": "📦"},
        },
    ],
)

# ── 并行扇出 ──

_t(
    "fan-out-3",
    "扇出 3 路",
    "一个入口并行分发到三个独立处理任务",
    "并行",
    [
        {
            "id": "router",
            "depends_on": [],
            "description": "请求分发",
            "metadata": {"type": "router", "icon": "🔀"},
        },
        {
            "id": "worker_a",
            "depends_on": ["router"],
            "description": "处理分支 A",
            "metadata": {"type": "worker", "icon": "🅰️"},
        },
        {
            "id": "worker_b",
            "depends_on": ["router"],
            "description": "处理分支 B",
            "metadata": {"type": "worker", "icon": "🅱️"},
        },
        {
            "id": "worker_c",
            "depends_on": ["router"],
            "description": "处理分支 C",
            "metadata": {"type": "worker", "icon": "©️"},
        },
    ],
)

_t(
    "fan-out-5",
    "扇出 5 路",
    "一个入口并行分发到五个独立处理任务",
    "并行",
    [
        {
            "id": "router",
            "depends_on": [],
            "description": "请求分发",
            "metadata": {"type": "router", "icon": "🔀"},
        },
        {
            "id": "w1",
            "depends_on": ["router"],
            "description": "处理分支 1",
            "metadata": {"type": "worker", "icon": "1️⃣"},
        },
        {
            "id": "w2",
            "depends_on": ["router"],
            "description": "处理分支 2",
            "metadata": {"type": "worker", "icon": "2️⃣"},
        },
        {
            "id": "w3",
            "depends_on": ["router"],
            "description": "处理分支 3",
            "metadata": {"type": "worker", "icon": "3️⃣"},
        },
        {
            "id": "w4",
            "depends_on": ["router"],
            "description": "处理分支 4",
            "metadata": {"type": "worker", "icon": "4️⃣"},
        },
        {
            "id": "w5",
            "depends_on": ["router"],
            "description": "处理分支 5",
            "metadata": {"type": "worker", "icon": "5️⃣"},
        },
    ],
)

# ── 扇入汇聚 ──

_t(
    "fan-in-3",
    "汇聚 3 路",
    "三个独立入口汇聚到一个合并任务",
    "汇聚",
    [
        {
            "id": "source_a",
            "depends_on": [],
            "description": "数据源 A",
            "metadata": {"type": "source", "icon": "🔵"},
        },
        {
            "id": "source_b",
            "depends_on": [],
            "description": "数据源 B",
            "metadata": {"type": "source", "icon": "🟢"},
        },
        {
            "id": "source_c",
            "depends_on": [],
            "description": "数据源 C",
            "metadata": {"type": "source", "icon": "🟡"},
        },
        {
            "id": "merge",
            "depends_on": ["source_a", "source_b", "source_c"],
            "description": "合并汇总",
            "metadata": {"type": "merge", "icon": "🔗"},
        },
        {
            "id": "output",
            "depends_on": ["merge"],
            "description": "输出结果",
            "metadata": {"type": "output", "icon": "📤"},
        },
    ],
)

# ── 批处理 ──

_t(
    "batch-etl",
    "ETL 批处理",
    "抽取 → 转换 → 加载 经典 ETL 流水线",
    "批处理",
    [
        {
            "id": "extract_db",
            "depends_on": [],
            "description": "从数据库抽取",
            "metadata": {"type": "extract", "icon": "🗄️"},
        },
        {
            "id": "extract_api",
            "depends_on": [],
            "description": "从 API 抽取",
            "metadata": {"type": "extract", "icon": "🌐"},
        },
        {
            "id": "validate",
            "depends_on": ["extract_db", "extract_api"],
            "description": "校验原始数据",
            "metadata": {"type": "validate", "icon": "✅"},
        },
        {
            "id": "transform",
            "depends_on": ["validate"],
            "description": "数据转换清洗",
            "metadata": {"type": "transform", "icon": "🔄"},
        },
        {
            "id": "load_dw",
            "depends_on": ["transform"],
            "description": "加载到数仓",
            "metadata": {"type": "load", "icon": "🏢"},
        },
        {
            "id": "notify",
            "depends_on": ["load_dw"],
            "description": "发送完成通知",
            "metadata": {"type": "notify", "icon": "🔔"},
        },
    ],
)

# ── CI/CD ──

_t(
    "ci-pipeline",
    "CI 流水线",
    "代码提交 → 构建 → 测试 → 部署",
    "CI/CD",
    [
        {
            "id": "checkout",
            "depends_on": [],
            "description": "拉取代码",
            "metadata": {"type": "vcs", "icon": "📦"},
        },
        {
            "id": "lint",
            "depends_on": ["checkout"],
            "description": "代码检查",
            "metadata": {"type": "quality", "icon": "🔍"},
        },
        {
            "id": "unit_test",
            "depends_on": ["checkout"],
            "description": "单元测试",
            "metadata": {"type": "test", "icon": "🧪"},
        },
        {
            "id": "build",
            "depends_on": ["lint", "unit_test"],
            "description": "编译构建",
            "metadata": {"type": "build", "icon": "🔨"},
        },
        {
            "id": "integration_test",
            "depends_on": ["build"],
            "description": "集成测试",
            "metadata": {"type": "test", "icon": "🧪"},
        },
        {
            "id": "deploy_staging",
            "depends_on": ["integration_test"],
            "description": "部署预发布",
            "metadata": {"type": "deploy", "icon": "🚀"},
        },
        {
            "id": "deploy_prod",
            "depends_on": ["deploy_staging"],
            "description": "部署生产",
            "metadata": {"type": "deploy", "icon": "🌟"},
        },
    ],
)

_t(
    "daily-report",
    "日报生成",
    "每日自动采集数据、生成报表、发送邮件",
    "批处理",
    [
        {
            "id": "collect_metrics",
            "depends_on": [],
            "description": "采集当日指标",
            "metadata": {"type": "collect", "icon": "📊"},
        },
        {
            "id": "generate_chart",
            "depends_on": ["collect_metrics"],
            "description": "生成趋势图",
            "metadata": {"type": "viz", "icon": "📈"},
        },
        {
            "id": "compile_report",
            "depends_on": ["generate_chart"],
            "description": "编写报告",
            "metadata": {"type": "report", "icon": "📝"},
        },
        {
            "id": "send_email",
            "depends_on": ["compile_report"],
            "description": "发送邮件",
            "metadata": {"type": "notify", "icon": "📧"},
        },
    ],
)


def list_templates(category: str | None = None) -> list[dict[str, Any]]:
    result = []
    for t in _TEMPLATES:
        if category and t.category != category:
            continue
        result.append(
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "node_count": len(t.nodes),
            }
        )
    return result


def list_categories() -> list[str]:
    cats: list[str] = []
    seen: set[str] = set()
    for t in _TEMPLATES:
        if t.category not in seen:
            seen.add(t.category)
            cats.append(t.category)
    return cats


def get_template(template_id: str) -> DAGTemplate | None:
    for t in _TEMPLATES:
        if t.id == template_id:
            return t
    return None


def apply_template(template_id: str, clear_existing: bool = True) -> TaskDAG:
    t = get_template(template_id)
    if t is None:
        raise ValueError(f"模板不存在: {template_id}")

    dag = TaskDAG()
    if clear_existing:
        dag.reset()

    for node_data in t.nodes:
        dag.add_node(
            node_id=node_data["id"],
            depends_on=node_data.get("depends_on", []),
            description=node_data.get("description", ""),
            metadata=node_data.get("metadata", {}),
        )

    dag.save()
    return dag
