"""行动层：默认单发调用；开启 agent_loop 后走 ReAct 工具循环。"""

import logging

log = logging.getLogger(__name__)


class ActionLayer:
    name = "action"

    def __init__(self, provider, tools: dict | None = None, cfg: dict | None = None):
        self.provider = provider
        self.tools = tools or {}
        self.cfg = cfg or {}

    def process(self, ctx):
        system = ctx.metadata.get("system_prompt")
        if self.cfg.get("agent_loop", True) and self.tools:
            from bluedeer.loop import run_loop

            ctx.action_result = run_loop(
                self.provider,
                self.tools,
                ctx.cleaned_input,
                system or "",
                self.cfg,
                ctx=ctx,
            )
            log.info(
                "[action] loop steps=%s stop=%s",
                len(ctx.metadata.get("steps", [])),
                ctx.metadata.get("stop_reason"),
            )
        else:
            ctx.action_result = self.provider.generate(ctx.cleaned_input, ctx, system=system)
            log.info("[action] provider=%s", self.provider.name)
