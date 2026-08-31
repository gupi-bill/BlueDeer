"""核心 Agent：按 13 层顺序逐层推进，支持开关、追踪与角色注入。"""

import logging
import time
from pathlib import Path

from bluedeer.context import Context
from bluedeer.config import get_env, load_config, resolve_path
from bluedeer.memory import InMemoryMemory
from bluedeer.providers import get_provider
from bluedeer.roles import resolve_system_prompt
from bluedeer.tools import build_tools
from bluedeer.tracing import RunTrace

from bluedeer.layers.input import InputLayer
from bluedeer.layers.understanding import UnderstandingLayer
from bluedeer.layers.memory import MemoryLayer
from bluedeer.layers.reasoning import ReasoningLayer
from bluedeer.layers.decision import DecisionLayer
from bluedeer.layers.planning import PlanningLayer
from bluedeer.layers.task_queue import TaskQueueLayer
from bluedeer.layers.action import ActionLayer
from bluedeer.layers.result_check import ResultCheckLayer
from bluedeer.layers.output import OutputLayer
from bluedeer.layers.safety import SafetyLayer
from bluedeer.layers.mcp import McpLayer
from bluedeer.layers.monitoring import MonitoringLayer

log = logging.getLogger(__name__)


class BlueDeerAgent:
    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        self.memory = InMemoryMemory()
        provider_kwargs = {
            "model": self.config.get("ollama_model", "qwen2.5vl:7b"),
            "base_url": self.config.get("ollama_base_url", "http://localhost:11434"),
            "api_base": self.config.get("api_base", ""),
            "api_key": self.config.get("api_key", "") or get_env("BLUEDEER_API_KEY"),
            "api_model": self.config.get("api_model", ""),
        }
        self.provider = get_provider(self.config.get("provider", "mock"), **provider_kwargs)
        self.system_prompt = resolve_system_prompt(self.config)
        self.tools = build_tools(self.config.get("tools_enabled"))

        self.layers = [
            InputLayer(),
            UnderstandingLayer(),
            MemoryLayer(self.memory),
            ReasoningLayer(),
            DecisionLayer(),
            PlanningLayer(),
            TaskQueueLayer(),
            ActionLayer(self.provider, self.tools, self.config),
            ResultCheckLayer(),
            OutputLayer(),
            SafetyLayer(),
            McpLayer(),
            MonitoringLayer(),
        ]
        self.layer_enabled = self.config.get("layers", {})
        log.info(
            "BlueDeerAgent initialized, provider=%s, role=%s",
            self.provider.name,
            self.config.get("role") or "-",
        )

    def run(self, text: str) -> str:
        ctx = Context(raw_input=text)
        ctx.metadata["started_at"] = time.time()
        if self.system_prompt:
            ctx.metadata["system_prompt"] = self.system_prompt

        tracer = None
        if self.config.get("trace", True):
            tracer = RunTrace(resolve_path(self.config, "runs_dir"))
            ctx.metadata["run_id"] = tracer.start()

        for layer in self.layers:
            if not self.layer_enabled.get(layer.name, True):
                continue
            t0 = time.time()
            layer.process(ctx)
            elapsed_ms = int((time.time() - t0) * 1000)
            ctx.metadata.setdefault("layer_timings", {})[layer.name] = elapsed_ms
            if tracer:
                tracer.snapshot(layer.name, ctx, elapsed_ms)
            if ctx.blocked:
                break

        if tracer:
            tracer.finish(ctx)

        if ctx.blocked:
            return f"[安全拦截] {ctx.block_reason}"
        return ctx.output
