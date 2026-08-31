"""故障注入演练套件：对核心子系统注入故障，验证系统不崩、能恢复。

用法:
    python scripts/fault_drill.py             # 全量演练
    python scripts/fault_drill.py event_bus   # 只跑某个场景

场景:
    1. event_bus   - handler 抛异常，其他 handler 不受影响
    2. scheduler   - 触发任务失败，调度器继续运行、队列不丢
    3. database    - 数据库不可用，核心组件降级不崩
    4. router      - 模型路由主模型全挂，failover 到备用候选
退出码: 0 = 全部通过, 1 = 有场景失败
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.event_bus import EventBus
from core.task import Message, Task

PASS, FAIL = 0, 1


def drill_event_bus() -> int:
    """handler 抛异常不应阻断其他 handler。"""
    bus = EventBus()
    got: list[int] = []

    async def bad(msg: Message) -> None:
        raise RuntimeError("注入故障：handler 崩溃")

    async def good(msg: Message) -> None:
        got.append(1)

    bus.subscribe("t", bad)
    bus.subscribe("t", good)
    asyncio.run(bus.publish("t", Message()))
    ok = got == [1] and bus.subscriber_count("t") == 2
    print(
        f"  [{'PASS' if ok else 'FAIL'}] event_bus: 异常隔离 (其他 handler 收到 {got})"
    )
    return PASS if ok else FAIL


def drill_scheduler() -> int:
    """单个 job 失败不影响调度器后续运行。"""
    import asyncio as _asyncio

    from core.scheduler import JobDef, Scheduler

    fired: list[str] = []

    class _BrokenHarness:
        async def submit_task(self, task: Task) -> None:
            fired.append(task.type)
            raise RuntimeError("注入故障：任务提交失败")

    async def run() -> int:
        bus = EventBus()
        sched = Scheduler(event_bus=bus, harness=_BrokenHarness())
        sched.add_job(JobDef(id="boom", interval_seconds=1))
        await sched.start()
        await _asyncio.sleep(2.5)
        await sched.stop()
        alive = sched.get_job("boom") is not None
        print(
            f"  [{'PASS' if fired and alive else 'FAIL'}] scheduler: 失败 job 触发 {len(fired)} 次，任务仍保留"
        )
        return PASS if fired and alive else FAIL

    return asyncio.run(run())


def drill_database() -> int:
    """数据库不可用时降级不崩。"""
    import logging

    logging.disable(logging.CRITICAL)

    import core.scheduler as sched_mod
    from core.event_bus import EventBus
    from core.scheduler import JobDef, Scheduler

    class _DeadDB:
        def load_scheduler_jobs(self) -> list:
            raise RuntimeError("注入故障：数据库连接失败")

        def save_scheduler_jobs(self, raw: dict) -> None:
            raise RuntimeError("注入故障：数据库连接失败")

    sched_mod.Database = _DeadDB  # type: ignore[assignment]
    try:
        s = Scheduler(event_bus=EventBus())
        jid = s.add_job(JobDef(id="x", interval_seconds=5))
        alive = s.get_job(jid) is not None and s._queue.peek_min() is not None
        print(
            f"  [{'PASS' if alive else 'FAIL'}] database: 数据库挂掉后 add/get/队列仍可用"
        )
        return PASS if alive else FAIL
    finally:
        logging.disable(logging.NOTSET)


def drill_router() -> int:
    """主模型全挂时 failover 到备用候选，全挂则抛错并触发降级。"""
    from models.client import ModelClient
    from models.router import Router as ModelRouter

    class _Dead(ModelClient):
        def __init__(self, name: str) -> None:
            self._name = name

        @property
        def model_name(self) -> str:
            return self._name

        async def complete(self, prompt: str, **kwargs):
            raise RuntimeError(f"{self._name} 注入故障")

    async def run() -> int:
        from core.config import get_config

        cfg = get_config()
        old_threshold = cfg.model.fail_threshold
        cfg.model.fail_threshold = 1
        router = ModelRouter()
        dead = _Dead("dead-primary")
        router._clients = {"dead-primary": dead, "dead-backup": _Dead("dead-backup")}
        router._default_client = dead
        try:
            try:
                await router.complete_with_failover("code", "hello")
                ok = False
            except RuntimeError:
                ok = True
            degraded = "dead-primary" in router._degraded
            print(
                f"  [{'PASS' if ok and degraded else 'FAIL'}] router: 全挂抛 RuntimeError（降级={degraded}）"
            )
            return PASS if ok and degraded else FAIL
        finally:
            cfg.model.fail_threshold = old_threshold

    return asyncio.run(run())


SCENARIOS = {
    "event_bus": drill_event_bus,
    "scheduler": drill_scheduler,
    "database": drill_database,
    "router": drill_router,
}


def main() -> int:
    scope = sys.argv[1] if len(sys.argv) > 1 else None
    targets = {scope} if scope else set(SCENARIOS)
    results: dict[str, int] = {}
    for name, fn in SCENARIOS.items():
        if name not in targets:
            continue
        print(f"== 演练场景: {name} ==")
        t0 = time.perf_counter()
        results[name] = fn()
        print(f"   用时 {time.perf_counter() - t0:.2f}s\n")

    failed = [n for n, r in results.items() if r == FAIL]
    print(f"== 故障演练结果: {len(results) - len(failed)}/{len(results)} 通过 ==")
    if failed:
        print(f"失败场景: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
