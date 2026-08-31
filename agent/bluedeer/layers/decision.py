"""第 5 层：决策层。第一版直接回答。"""

import logging

log = logging.getLogger(__name__)


class DecisionLayer:
    name = "decision"

    def process(self, ctx):
        ctx.decision = "direct_answer"
        log.info("[decision] %s", ctx.decision)
