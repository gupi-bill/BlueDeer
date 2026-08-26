"""第 6 层：规划层。第一版占位，后续拆多步任务。"""

import logging

log = logging.getLogger(__name__)


class PlanningLayer:
    name = "planning"

    def process(self, ctx):
        # TODO: 多步任务拆成有序步骤
        ctx.plan = []
        log.info("[planning] stub")
