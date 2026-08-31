"""007 agent frameworks unified integration layer (008-1).

把 AutoGPT / BabyAGI / AgentGPT / OpenDevin / CrewAI / LangGraph 六种 agent
框架统一接入 Harness + EventBus：

    Harness.submit_task(Task(payload={"framework": ..., "goal": ...}))
      -> EventBus publish agent.<id>
      -> FrameworkAgent.handle() 按 payload["framework"] 分派
      -> TaskResult 回 RESULT_TOPIC

集成要点：
- 四个 loop 型框架（AutoGPT/BabyAGI/AgentGPT/OpenDevin）复用各自 run_* 入口；
- CrewAI 从 payload 反序列化 CrewDef，经 CrewAIFlow 编排（agent=self 走 EventBus 子任务）；
- LangGraph 从 payload 图规格构建 StateGraph，节点经 router 推理（run_async 支持异步节点）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from core.base_agent import BaseAgent
from core.crewai_style import AgentDef, CrewAIFlow, CrewDef, TaskDef
from core.langgraph_style import State, StateGraph
from core.task import Task, TaskResult, TaskStatus, TokenUsage

logger = logging.getLogger("bluedeer.agent_integration")

__all__ = [
    "SUPPORTED_FRAMEWORKS",
    "FrameworkAgent",
    "build_langgraph_from_spec",
    "crew_from_dict",
    "run_framework_agent",
    "run_langgraph_async",
]

#: 六种受支持框架
SUPPORTED_FRAMEWORKS = (
    "autogpt",
    "babyagi",
    "agentgpt",
    "opendevin",
    "crewai",
    "langgraph",
)

_LOOP_GOAL_KEYS = {
    "autogpt": ("goal", "run_autonomous"),
    "babyagi": ("objective", "run"),
    "agentgpt": ("goal", "run_goal"),
    "opendevin": ("goal", "run_dev_loop"),
}


# ---------------------------------------------------------------------------
# 反序列化辅助
# ---------------------------------------------------------------------------


def crew_from_dict(data: dict[str, Any]) -> CrewDef:
    """从 payload dict 反序列化 CrewDef（防注入：只取已知字段）。"""
    agents = [
        AgentDef(
            role=str(a.get("role", "")),
            goal=str(a.get("goal", "")),
            backstory=str(a.get("backstory", "")),
            tools=[str(t) for t in a.get("tools", [])],
        )
        for a in data.get("agents", [])
    ]
    tasks = [
        TaskDef(
            description=str(t.get("description", "")),
            agent_role=str(t.get("agent_role", "")),
            expected_output=str(t.get("expected_output", "")),
        )
        for t in data.get("tasks", [])
    ]
    return CrewDef(
        agents=agents, tasks=tasks, process=str(data.get("process", "sequential"))
    )


def build_langgraph_from_spec(
    spec: dict[str, Any], node_fn: Callable[[str, State], State]
) -> StateGraph:
    """按规格构建 StateGraph。

    spec = {
        "entry": "research",
        "nodes": ["research", "draft", "review"],
        "edges": {"research": "draft", "draft": "review"},
        "conditional": {"review": lambda s: "end" if s.get("done") else "draft"},
        "steps": 20,
    }
    """
    graph = StateGraph()
    for name in spec.get("nodes", []):
        graph.add_node(name, (lambda n: lambda s: node_fn(n, s))(name))  # noqa: PLC3002
    for src, dst in spec.get("edges", {}).items():
        graph.add_edge(src, dst)
    for src, fn in spec.get("conditional", {}).items():
        graph.add_conditional_edge(src, fn)
    graph.set_entry_point(str(spec.get("entry", "")))
    return graph


async def run_langgraph_async(
    graph: StateGraph,
    steps: int = 20,
    *,
    node_runner: Callable[[str, State], Any] | None = None,
) -> State:
    """异步版图遍历：支持 async 节点执行（StateGraph.run 是同步的）。

    当节点函数为 async 时自动 await；node_runner 存在时用它兜底执行
    （用于把 StateGraph 接到 router / EventBus）。
    """
    if not graph._entry_point:
        raise RuntimeError("entry_point not set")
    current = graph._entry_point
    for _ in range(steps):
        if current not in graph._nodes:
            break
        node_fn = graph._nodes[current]
        if node_runner is not None:
            result = node_runner(current, graph._state)
            if hasattr(result, "__await__"):
                result = await result
            graph._state = result
        else:
            result = node_fn(graph._state)
            if hasattr(result, "__await__"):
                result = await result
            graph._state = result
        graph.checkpoint()
        if current in graph._conditional:
            current = graph._conditional[current](graph._state)
        elif current in graph._edges:
            current = graph._edges[current]
        else:
            break
    return graph._state


# ---------------------------------------------------------------------------
# FrameworkAgent：六框架统一接 Harness/EventBus 的 Agent
# ---------------------------------------------------------------------------


class FrameworkAgent(BaseAgent):
    """按 task.payload["framework"] 分派到对应 007 框架执行的集成 Agent。

    payload 约定：
        autogpt   -> {"framework": "autogpt", "goal": str, "max_steps": int?}
        babyagi   -> {"framework": "babyagi", "objective": str}
        agentgpt  -> {"framework": "agentgpt", "goal": str, "max_tasks": int?}
        opendevin -> {"framework": "opendevin", "goal": str, "max_steps": int?}
        crewai    -> {"framework": "crewai", "crew": {...CrewDef dict...}}
        langgraph -> {"framework": "langgraph", "graph": {...spec...}}

    四个 loop 型框架由内部组合的具体 agent（AutoGPTAgent 等）执行，各自
    订阅独立 topic（agent_id 加后缀），避免与自身 topic 冲突。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.agentgpt_style import BrowserGoalAgent
        from core.agentic_loop import AutoGPTAgent
        from core.babyagi_loop import BabyAGILoopAgent
        from core.opendevin_style import DeveloperAgent

        self._loop_agents: dict[str, BaseAgent] = {
            "autogpt": AutoGPTAgent(
                agent_id=f"{self.agent_id}.autogpt",
                role=self.role,
                event_bus=self._bus,
                router=self._router,
                tool_registry=self._tools,
                context=self._context,
            ),
            "babyagi": BabyAGILoopAgent(
                agent_id=f"{self.agent_id}.babyagi",
                role=self.role,
                event_bus=self._bus,
                router=self._router,
                tool_registry=self._tools,
                context=self._context,
            ),
            "agentgpt": BrowserGoalAgent(
                agent_id=f"{self.agent_id}.agentgpt",
                role=self.role,
                event_bus=self._bus,
                router=self._router,
                tool_registry=self._tools,
                context=self._context,
            ),
            "opendevin": DeveloperAgent(
                agent_id=f"{self.agent_id}.opendevin",
                role=self.role,
                event_bus=self._bus,
                router=self._router,
                tool_registry=self._tools,
                context=self._context,
            ),
        }

    async def handle(self, task: Task) -> TaskResult:
        """按 payload["framework"] 分派，返回统一 TaskResult。"""
        self._trace_span(
            task.trace_id,
            "framework_handle_start",
            task_id=task.id,
            task_type=task.type,
        )
        usage = TokenUsage()
        try:
            # 非框架任务（如 CrewAI 子任务）回退到默认 BaseAgent 逻辑
            if "framework" not in task.payload:
                return await super().handle(task)

            framework = str(task.payload.get("framework", "autogpt"))
            if framework not in SUPPORTED_FRAMEWORKS:
                raise ValueError(f"unsupported framework: {framework}")

            if framework == "crewai":
                output = await self._run_crewai(task)
            elif framework == "langgraph":
                output = await self._run_langgraph(task)
            else:
                output = await self._run_loop_framework(framework, task)

            self._trace_span(
                task.trace_id,
                "framework_handle_success",
                framework=framework,
                task_id=task.id,
            )
            return TaskResult(
                trace_id=task.trace_id,
                task_id=task.id,
                status=TaskStatus.SUCCESS,
                output={"framework": framework, "result": output},
                token_usage=usage,
            )
        except Exception as e:
            logger.exception("FrameworkAgent %s 执行 %s 失败", self.agent_id, task.id)
            if self._tracer:
                self._tracer.error(
                    task.trace_id,
                    component=f"FrameworkAgent:{self.agent_id}",
                    action="framework_handle_failed",
                    error=str(e),
                    task_id=task.id,
                )
            return TaskResult(
                trace_id=task.trace_id,
                task_id=task.id,
                status=TaskStatus.FAILED,
                error=str(e),
                token_usage=usage,
            )

    async def _run_loop_framework(self, framework: str, task: Task) -> Any:
        """四类 loop 框架：AutoGPT/BabyAGI/AgentGPT/OpenDevin。"""
        goal_key, method_name = _LOOP_GOAL_KEYS[framework]
        goal = str(task.payload.get(goal_key, ""))
        if not goal:
            raise ValueError(f"{framework} requires payload['{goal_key}']")
        loop_agent = self._loop_agents[framework]
        method = getattr(loop_agent, method_name)
        kwargs: dict[str, Any] = {}
        if "max_steps" in task.payload:
            kwargs["max_steps"] = int(task.payload["max_steps"])
        if "max_tasks" in task.payload:
            kwargs["max_tasks"] = int(task.payload["max_tasks"])
        result = method(goal, **kwargs)
        if hasattr(result, "__await__"):
            result = await result
        return _to_serializable(result)

    async def _run_crewai(self, task: Task) -> Any:
        """CrewAI：payload["crew"] -> CrewDef -> CrewAIFlow 顺序编排。"""
        crew = crew_from_dict(task.payload.get("crew") or {})
        flow = CrewAIFlow(crew, agent=self)
        return _to_serializable(await flow.run_async())

    async def _run_langgraph(self, task: Task) -> Any:
        """LangGraph：payload["graph"] 规格 -> StateGraph，节点经 router 推理。"""
        spec = task.payload.get("graph") or {}
        if not spec.get("nodes"):
            raise ValueError("langgraph requires payload['graph']['nodes']")

        async def node_runner(name: str, state: State) -> State:
            prompt = str(
                spec.get("prompts", {}).get(
                    name, f"[LangGraph node:{name}] {state.data}"
                )
            )
            model_response = await self._router.complete_with_failover(
                task.type,
                prompt,
                agent_id=self.agent_id,
            )
            state.set(name, model_response.content)
            if hasattr(model_response, "tokens_in"):
                nonlocal usage
                usage.tokens_in += model_response.tokens_in
                usage.tokens_out += getattr(model_response, "tokens_out", 0)
            return state

        usage = TokenUsage()
        graph = build_langgraph_from_spec(spec, node_fn=lambda n, s: s)
        final_state = await run_langgraph_async(
            graph,
            steps=int(spec.get("steps", 20)),
            node_runner=node_runner,
        )
        return {"state": final_state.data}


def _to_serializable(obj: Any) -> Any:
    """把框架返回对象转 JSON 友好结构。"""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_serializable(v) for v in obj]
    if hasattr(obj, "__dataclass_fields__"):
        return _to_serializable(asdict(obj))
    return str(obj)


async def run_framework_agent(agent: FrameworkAgent, task: Task) -> TaskResult:
    """便捷入口：直接跑集成 agent 的单次任务（非总线模式）。"""
    return await agent.handle(task)
