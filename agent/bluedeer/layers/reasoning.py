"""第 4 层：推理层。第一版占位，后续补思维链。"""

import logging

log = logging.getLogger(__name__)


class ReasoningLayer:
    name = "reasoning"

    def process(self, ctx):
        # TODO: 复杂问题用思维链拆分步骤
        ctx.reasoning = ""
        log.info("[reasoning] stub")
