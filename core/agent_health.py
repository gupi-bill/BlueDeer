"""BlueDeer Agent Health Monitor: heartbeat, health checks, status tracking."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("bluedeer.health")


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheck:
    name: str
    check_fn: Callable[[], bool | Coroutine[Any, Any, bool]]
    interval: float = 30.0
    timeout: float = 5.0
    last_status: HealthStatus = HealthStatus.UNKNOWN
    last_check: float = field(default_factory=time.time)
    error_count: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


@dataclass
class AgentHealth:
    agent_id: str
    status: HealthStatus = HealthStatus.UNKNOWN
    last_heartbeat: float = field(default_factory=time.time)
    heartbeat_timeout: float = 60.0
    checks: dict[str, HealthCheck] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _heartbeat_task: Any = field(default=None, repr=False)

    def register_check(self, check: HealthCheck) -> None:
        with self._lock:
            self.checks[check.name] = check

    def update_heartbeat(self) -> None:
        with self._lock:
            self.last_heartbeat = time.time()
            if self.status == HealthStatus.UNKNOWN:
                self.status = HealthStatus.HEALTHY

    def is_alive(self) -> bool:
        with self._lock:
            elapsed = time.time() - self.last_heartbeat
            return elapsed < self.heartbeat_timeout

    def evaluate(self) -> HealthStatus:
        with self._lock:
            if not self.is_alive():
                self.status = HealthStatus.UNHEALTHY
                return self.status

            degraded = False
            for check in self.checks.values():
                if check.last_status == HealthStatus.UNHEALTHY:
                    self.status = HealthStatus.UNHEALTHY
                    return self.status
                if check.last_status == HealthStatus.DEGRADED:
                    degraded = True

            if degraded:
                self.status = HealthStatus.DEGRADED
            else:
                self.status = HealthStatus.HEALTHY
            return self.status

    def record_check_result(self, check_name: str, passed: bool) -> None:
        with self._lock:
            check = self.checks.get(check_name)
            if check is None:
                return
            check.last_check = time.time()
            if passed:
                check.last_status = HealthStatus.HEALTHY
                check.error_count = 0
            else:
                check.error_count += 1
                if check.error_count >= 3:
                    check.last_status = HealthStatus.UNHEALTHY
                else:
                    check.last_status = HealthStatus.DEGRADED


class HealthMonitor:
    """Central health monitor for all agents."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentHealth] = {}
        self._lock = threading.Lock()
        self._running = False
        self._monitor_thread: threading.Thread | None = None

    def register_agent(
        self,
        agent_id: str,
        heartbeat_timeout: float = 60.0,
    ) -> AgentHealth:
        with self._lock:
            if agent_id in self._agents:
                return self._agents[agent_id]
            health = AgentHealth(agent_id=agent_id, heartbeat_timeout=heartbeat_timeout)
            self._agents[agent_id] = health
            logger.info("Registered health monitor for agent %s", agent_id)
            return health

    def unregister_agent(self, agent_id: str) -> None:
        with self._lock:
            self._agents.pop(agent_id, None)

    def heartbeat(self, agent_id: str) -> None:
        with self._lock:
            health = self._agents.get(agent_id)
        if health is not None:
            health.update_heartbeat()

    def get_health(self, agent_id: str) -> HealthStatus | None:
        with self._lock:
            health = self._agents.get(agent_id)
        if health is None:
            return None
        return health.evaluate()

    def get_all_health(self) -> dict[str, HealthStatus]:
        with self._lock:
            agents = dict(self._agents)
        return {aid: h.evaluate() for aid, h in agents.items()}

    def start_background_monitor(self, interval: float = 10.0) -> None:
        if self._running:
            return
        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval,),
            daemon=True,
        )
        self._monitor_thread.start()
        logger.info(
            "Health monitor background thread started (interval=%.1fs)", interval
        )

    def stop(self) -> None:
        self._running = False
        if self._monitor_thread is not None:
            self._monitor_thread.join(timeout=5.0)

    def _monitor_loop(self, interval: float) -> None:
        while self._running:
            try:
                time.sleep(interval)
                all_health = self.get_all_health()
                for agent_id, status in all_health.items():
                    if status == HealthStatus.UNHEALTHY:
                        logger.warning("Agent %s is UNHEALTHY", agent_id)
                    elif status == HealthStatus.DEGRADED:
                        logger.info("Agent %s is DEGRADED", agent_id)
            except Exception:
                logger.exception("Health monitor 循环异常（已恢复）")


_global_monitor: HealthMonitor | None = None
_health_lock = threading.Lock()


def get_health_monitor() -> HealthMonitor:
    global _global_monitor
    if _global_monitor is None:
        with _health_lock:
            if _global_monitor is None:
                _global_monitor = HealthMonitor()
    return _global_monitor


__all__ = [
    "AgentHealth",
    "HealthCheck",
    "HealthMonitor",
    "HealthStatus",
    "get_health_monitor",
]
