"""第 13 层：监控层。记录耗时与关键日志。"""

import logging
import time

log = logging.getLogger(__name__)


class MonitoringLayer:
    name = "monitoring"

    def process(self, ctx):
        started = ctx.metadata.get("started_at")
        if started:
            elapsed_ms = int((time.time() - started) * 1000)
            ctx.metadata["elapsed_ms"] = elapsed_ms
            log.info("[monitoring] elapsed_ms=%d", elapsed_ms)
