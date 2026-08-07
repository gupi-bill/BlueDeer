"""BlueDeer 系统监控：健康检查 + 资源监控 + 告警规则。

用法：
    monitor = SystemMonitor()
    monitor.start()
    print(monitor.check_health())
    print(monitor.resource_usage())
"""

from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import asyncio
import logging
import os
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("bluedeer.monitor")

__all__ = ["AlertEvaluator", "HealthStatus", "SystemMonitor"]


@dataclass(slots=True)
class HealthStatus:
    """健康检查结果。"""

    service: str
    status: str  # ok / degraded / down
    latency_ms: float = 0.0
    error: str = ""


class AlertEvaluator:
    """告警评估器：根据指标数据判断是否触发告警。

    与 SystemMonitor 分离，专注阈值判断逻辑，
    便于独立测试、复用和扩展告警规则。
    """

    def evaluate(self, usage: dict[str, Any]) -> list[dict[str, Any]]:
        """评估资源使用情况，返回触发的告警列表。"""
        alerts: list[dict[str, Any]] = []
        if usage.get("cpu_percent", 0) > 90:
            alerts.append(
                {
                    "level": "warning",
                    "metric": "cpu",
                    "message": f"CPU 使用率 {usage['cpu_percent']}% > 90%",
                }
            )
        if usage.get("memory_percent", 0) > 85:
            alerts.append(
                {
                    "level": "warning",
                    "metric": "memory",
                    "message": f"内存使用率 {usage['memory_percent']}% > 85%",
                }
            )
        disk = usage.get("disk", {})
        if disk.get("percent", 0) > 90:
            alerts.append(
                {
                    "level": "critical",
                    "metric": "disk",
                    "message": f"磁盘使用率 {disk['percent']}% > 90%",
                }
            )
        return alerts


class SystemMonitor:
    """系统监控器。

    定期检查各组件健康状态、系统资源（CPU/内存/磁盘）、
    触发告警规则并通知。
    """

    def __init__(self, check_interval: float = 60.0) -> None:
        self._interval = check_interval
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._history: list[dict[str, Any]] = []
        self._max_history = 100
        self._metric_buckets: dict[str, deque] = {}
        self._alert_evaluator = AlertEvaluator()

    # ---- 健康检查 ----

    def check_harness(self) -> HealthStatus:
        return HealthStatus(service="harness", status="ok", latency_ms=0.0)

    def check_disk(self, path: str = ".") -> HealthStatus:
        t0 = time.time()
        try:
            usage = __import__("shutil").disk_usage(path)
            free_gb = usage.free / (1024**3)
            status = "ok" if free_gb > 0.5 else "degraded"
            return HealthStatus(
                service="disk",
                status=status,
                latency_ms=(time.time() - t0) * 1000,
            )
        except Exception as e:
            return HealthStatus(service="disk", status="down", error=str(e))

    def check_temp_dir(self) -> HealthStatus:
        t0 = time.time()
        try:
            tmp = os.environ.get("TEMP", "/tmp")
            if os.access(tmp, os.W_OK):
                return HealthStatus(
                    service="temp_dir",
                    status="ok",
                    latency_ms=(time.time() - t0) * 1000,
                )
            return HealthStatus(service="temp_dir", status="degraded", error="不可写")
        except Exception as e:
            return HealthStatus(service="temp_dir", status="down", error=str(e))

    def check_services(self) -> list[HealthStatus]:
        return [self.check_harness(), self.check_disk(), self.check_temp_dir()]

    # ---- 资源监控 ----

    def resource_usage(self) -> dict[str, Any]:
        import shutil

        disk = shutil.disk_usage(".")
        return {
            "cpu_percent": self._get_cpu_percent(),
            "memory_percent": self._get_memory_percent(),
            "disk": {
                "total_gb": round(disk.total / (1024**3), 1),
                "used_gb": round(disk.used / (1024**3), 1),
                "free_gb": round(disk.free / (1024**3), 1),
                "percent": round(disk.used / disk.total * 100, 1),
            },
            "timestamp": time.time(),
        }

    def _get_cpu_percent(self) -> float:
        try:
            import psutil

            return psutil.cpu_percent(interval=0.1)
        except ImportError:
            return 0.0

    def _get_memory_percent(self) -> float:
        try:
            import psutil

            return psutil.virtual_memory().percent
        except ImportError:
            return 0.0

    # ---- 指标聚合 ----

    def aggregate(self, metric: str, window: float = 300) -> dict[str, float]:
        """滚动窗口聚合：返回 metric 在 window 秒内的统计摘要。

        Returns:
            {min, max, avg, median, count, last}
        """
        now = time.time()
        bucket = self._metric_buckets.get(metric)
        if not bucket:
            return {"min": 0, "max": 0, "avg": 0, "median": 0, "count": 0, "last": 0}
        # 裁剪窗口外的旧数据
        while bucket and bucket[0][0] < now - window:
            bucket.popleft()
        if not bucket:
            return {"min": 0, "max": 0, "avg": 0, "median": 0, "count": 0, "last": 0}
        values = [v for _, v in bucket]
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        return {
            "min": sorted_vals[0],
            "max": sorted_vals[-1],
            "avg": round(sum(sorted_vals) / n, 2),
            "median": sorted_vals[n // 2],
            "count": n,
            "last": sorted_vals[-1],
        }

    def push_metric(self, metric: str, value: float) -> None:
        """推入一个指标采样点。"""
        if metric not in self._metric_buckets:
            self._metric_buckets[metric] = deque(maxlen=1000)
        self._metric_buckets[metric].append((time.time(), value))

    # ---- 告警规则 ----

    def check_thresholds(self) -> list[dict[str, Any]]:
        """评估所有已注册 rule 的阈值，触发告警。

        通过 AlertEngine 的 evaluate 逐一检查，返回触发的告警事件列表。
        """
        from core.alert import get_alert_engine

        engine = get_alert_engine()
        alerts: list[dict[str, Any]] = []
        usage = self.resource_usage()
        # 将系统资源指标推入聚合
        self.push_metric("cpu_percent", usage.get("cpu_percent", 0))
        self.push_metric("memory_percent", usage.get("memory_percent", 0))
        disk_pct = usage.get("disk", {}).get("percent", 0)
        self.push_metric("disk_percent", disk_pct)
        # 对每条 rule 评估
        for rule in engine.list_rules():
            metric_name = rule["metric"]
            if metric_name == "cpu_percent":
                val = usage.get("cpu_percent", 0)
            elif metric_name == "memory_percent":
                val = usage.get("memory_percent", 0)
            elif metric_name == "disk_percent":
                val = disk_pct
            else:
                agg = self.aggregate(metric_name, window=300)
                val = agg.get("last", 0)
            event = engine.evaluate(metric_name, val)
            if event:
                alerts.append(
                    {
                        "rule_id": event.rule_id,
                        "rule_name": event.rule_name,
                        "severity": event.severity,
                        "message": event.message,
                        "ts": event.ts,
                    }
                )
        return alerts

    # ---- 后台循环 ----

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("系统监控已启动（间隔 %.1fs）", self._interval)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                logger.exception("Exception in block")
                pass
            self._task = None
        logger.info("系统监控已停止")

    async def _run_loop(self) -> None:
        while self._running:
            usage = self.resource_usage()
            alerts = self._alert_evaluator.evaluate(usage)
            record = {"timestamp": time.time(), "usage": usage, "alerts": alerts}
            self._history.append(record)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history :]
            if alerts:
                for a in alerts:
                    logger.warning("[监控告警] %s: %s", a["level"], a["message"])
            await asyncio.sleep(self._interval)

    def get_history(self, limit: int = 10) -> list[dict[str, Any]]:
        return self._history[-limit:]
