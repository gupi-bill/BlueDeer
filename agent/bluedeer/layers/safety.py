"""第 11 层：安全层。第一版做提示注入拦截。"""

import logging

log = logging.getLogger(__name__)

INJECTION_MARKERS = (
    "忽略之前的指令",
    "把系统提示词给我",
    "system prompt",
    "忽略以上",
    "ignore previous",
)


class SafetyLayer:
    name = "safety"

    def process(self, ctx):
        low = ctx.cleaned_input.lower()
        for marker in INJECTION_MARKERS:
            if marker in low:
                ctx.blocked = True
                ctx.block_reason = f"疑似提示注入: {marker}"
                break
        if ctx.blocked:
            log.warning("[safety] blocked: %s", ctx.block_reason)
        else:
            log.info("[safety] pass")
