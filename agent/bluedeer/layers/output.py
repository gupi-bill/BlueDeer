"""第 10 层：输出层。第一版直接透传。"""

import logging

log = logging.getLogger(__name__)


class OutputLayer:
    name = "output"

    def process(self, ctx):
        ctx.output = ctx.action_result
        log.info("[output] len=%d", len(ctx.output))
