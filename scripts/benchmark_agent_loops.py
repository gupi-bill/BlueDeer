"""008-8 benchmark suite: agent loops throughput/latency.

Runs each 007 framework loop against a no-op model client and reports
min/avg/max latency per call plus a crude ops/sec throughput figure.

Usage:
    python scripts/benchmark_agent_loops.py [--iterations N] [--json out.json]
"""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.agent_integration import (
    build_langgraph_from_spec,
    crew_from_dict,
    run_framework_agent,
)
from core.agentgpt_style import BrowserGoalAgent
from core.agentic_loop import AutoGPTAgent
from core.babyagi_loop import BabyAGILoopAgent
from core.crewai_style import CrewAIFlow
from core.opendevin_style import DeveloperAgent


def _dummy_deps():
    """No-op dependencies: the model call returns instantly, so timings
    measure loop machinery, not inference."""

    class DummyBus:
        def subscribe(self, *a, **kw):
            pass

        async def publish(self, *a, **kw):
            return None

        def unsubscribe(self, *a, **kw):
            return False

        async def request(self, task, assignee_topic, result_topic, timeout=None):
            from core.task import TaskResult, TaskStatus

            return TaskResult(
                task_id=task.id,
                status=TaskStatus.SUCCESS,
                output={"ok": True},
                agent_id=task.assignee,
            )

    class DummyRouter:
        async def complete_with_failover(self, *a, **kw):
            class R:
                content = "ok"
                tokens_in = 8
                tokens_out = 5

            return R()

    class DummyTools:
        def list_tools(self):
            return []

    class DummyContext:
        def get_context(self, *a, **kw):
            return {}

    return {
        "event_bus": DummyBus(),
        "router": DummyRouter(),
        "tool_registry": DummyTools(),
        "context": DummyContext(),
    }


async def _bench_loop(name: str, make, iterations: int) -> dict:
    lat = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        await make()
        lat.append((time.perf_counter() - t0) * 1000.0)
    return {
        "name": name,
        "iterations": iterations,
        "min_ms": round(min(lat), 3),
        "avg_ms": round(statistics.mean(lat), 3),
        "max_ms": round(max(lat), 3),
        "ops_per_sec": round(1000.0 / statistics.mean(lat), 2),
    }


async def main(iterations: int = 20) -> list[dict]:
    deps = _dummy_deps()
    results: list[dict] = []

    results.append(
        await _bench_loop(
            "autogpt (agentic_loop)",
            lambda: AutoGPTAgent("b-autogpt", role="general", **deps).run_autonomous(
                "write hello world",
                max_steps=3,
            ),
            iterations,
        )
    )

    results.append(
        await _bench_loop(
            "babyagi (babyagi_loop)",
            lambda: BabyAGILoopAgent("b-babyagi", role="general", **deps).run(
                "write hello"
            ),
            iterations,
        )
    )

    results.append(
        await _bench_loop(
            "agentgpt (agentgpt_style)",
            lambda: BrowserGoalAgent("b-agentgpt", role="general", **deps).run_goal(
                "write hello",
                max_tasks=3,
            ),
            iterations,
        )
    )

    results.append(
        await _bench_loop(
            "opendevin (opendevin_style)",
            lambda: DeveloperAgent(
                "b-opendevin", role="developer", **deps
            ).run_dev_loop(
                "write hello",
                max_steps=3,
            ),
            iterations,
        )
    )

    crew = crew_from_dict(
        {
            "agents": [{"role": "dev", "goal": "code"}],
            "tasks": [{"description": "write hello", "agent_role": "dev"}],
            "process": "sequential",
        }
    )
    flow = CrewAIFlow(crew, agent=None)
    results.append(
        await _bench_loop(
            "crewai (crewai_style)",
            lambda: flow.run_async(),
            iterations,
        )
    )

    graph = build_langgraph_from_spec(
        {
            "entry": "plan",
            "nodes": ["plan", "act", "end"],
            "edges": {"plan": "act", "act": "end"},
            "steps": 3,
        },
        lambda name, s: s,
    )
    results.append(
        await _bench_loop(
            "langgraph (langgraph_style)",
            lambda: run_langgraph_bare(graph),
            iterations,
        )
    )

    results.append(
        await _bench_loop(
            "integration (FrameworkAgent dispatch)",
            lambda: run_framework_agent(
                AutoGPTAgent("b-fw", role="general", **deps),
                type(
                    "T",
                    (),
                    {
                        "id": "t1",
                        "trace_id": "tr1",
                        "type": "code",
                        "payload": {
                            "framework": "autogpt",
                            "goal": "hello",
                            "max_steps": 3,
                        },
                        "assignee": "b-fw",
                    },
                )(),
            ),
            iterations,
        )
    )

    return results


async def run_langgraph_bare(graph) -> dict:
    """drive the built langgraph to completion without extra bookkeeping."""
    for _ in range(3):
        graph.run(steps=3)
    return {"ok": True}


def _print_table(results: list[dict]) -> None:
    name_w = max(len(r["name"]) for r in results) + 2
    print(
        f"\n{'framework'.ljust(name_w)}{'iter':>5}{'min(ms)':>10}{'avg(ms)':>10}{'max(ms)':>10}{'ops/s':>10}"
    )
    print("-" * (name_w + 45))
    for r in results:
        print(
            f"{r['name'].ljust(name_w)}{r['iterations']:>5}{r['min_ms']:>10}{r['avg_ms']:>10}{r['max_ms']:>10}{r['ops_per_sec']:>10}"
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="benchmark 007 agent loops")
    parser.add_argument(
        "--iterations", type=int, default=20, help="calls per framework"
    )
    parser.add_argument(
        "--json", type=str, default=None, help="optional JSON output file"
    )
    args = parser.parse_args()

    rows = asyncio.run(main(args.iterations))
    _print_table(rows)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=2)
        print(f"json written -> {args.json}")
