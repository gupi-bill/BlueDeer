"""第 7 层：任务队列层。第一版占位，后续并行与重试。"""

import logging

log = logging.getLogger(__name__)


class TaskQueueLayer:
    name = "task_queue"

    def process(self, ctx):
        # TODO: 子任务并行、超时、失败重试
        ctx.tasks = []
        log.info("[task_queue] stub")
