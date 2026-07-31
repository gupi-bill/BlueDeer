"""外部任务系统 ExternalTaskSystem。

职责：
- 11 种任务类型与物种岗位匹配
- Task 类（task_id / type / difficulty / reward / deadline / status）
- inject / inject_batch / inject_random 注入任务
- assign / auto_assign 分配任务给员工
- 后台自动分配线程（start_auto_assigner / stop_auto_assigner）
- execute 执行任务（调用员工的 job_skill）
- try_complete_assigned / check_expired 完成与超时检查
- 物种绩效统计

任务成功概率公式：0.7 + 0.05*(energy-50) - 0.1*difficulty
老年期 ×0.5

零基础读者可以这样理解：
- 公司外部派来的活，11 种岗位对应 11 种任务。
- 每个员工只能接自己物种岗位的任务。
- 员工必须醒着、健康、有能量、成年、没在忙才能接单。
- 任务完成有奖励（食物/能量恢复），失败有惩罚。
"""
from __future__ import annotations

import random
import threading
import time
from collections import defaultdict, deque

# 11 种任务类型与物种岗位匹配
TASK_TYPES = {
    "deploy":        {"species": "beaver",    "difficulty": 3, "reward_food": 50, "reward_energy": -15, "description": "部署服务"},
    "test":          {"species": "fox",       "difficulty": 2, "reward_food": 30, "reward_energy": -10, "description": "自动化测试"},
    "ui_design":     {"species": "butterfly", "difficulty": 2, "reward_food": 25, "reward_energy": -8,  "description": "UI 设计"},
    "code":          {"species": "squirrel",  "difficulty": 3, "reward_food": 40, "reward_energy": -12, "description": "编码开发"},
    "security_scan": {"species": "hedgehog",  "difficulty": 2, "reward_food": 35, "reward_energy": -10, "description": "安全扫描"},
    "archive":       {"species": "raven",     "difficulty": 1, "reward_food": 20, "reward_energy": -5,  "description": "归档记忆"},
    "audit":         {"species": "hare",      "difficulty": 1, "reward_food": 20, "reward_energy": -5,  "description": "资源核算"},
    "route":         {"species": "badger",    "difficulty": 2, "reward_food": 25, "reward_energy": -8,  "description": "工具路由"},
    "monitor":       {"species": "lark",      "difficulty": 1, "reward_food": 15, "reward_energy": -4,  "description": "状态监控"},
    "plan":          {"species": "kite",      "difficulty": 2, "reward_food": 30, "reward_energy": -8,  "description": "任务规划"},
    "dispatch":      {"species": "deer",      "difficulty": 3, "reward_food": 45, "reward_energy": -15, "description": "总管调度"},
}


class Task:
    """一个外部任务。"""

    __slots__ = (
        "assigned_to",
        "attempts",
        "completed_at",
        "created_at",
        "deadline",
        "description",
        "difficulty",
        "result",
        "reward_energy",
        "reward_food",
        "status",
        "task_id",
        "task_type",
    )

    def __init__(self, task_id, task_type, description="", difficulty=None,
                 reward_food=None, reward_energy=None, deadline=300.0):
        """构造一个任务。

        未显式传入的字段从 TASK_TYPES 取默认值。
        """
        spec = TASK_TYPES.get(task_type, {})
        self.task_id = task_id
        self.task_type = task_type
        self.description = description if description else spec.get("description", "")
        self.difficulty = difficulty if difficulty is not None else spec.get("difficulty", 2)
        self.reward_food = reward_food if reward_food is not None else spec.get("reward_food", 30)
        self.reward_energy = reward_energy if reward_energy is not None else spec.get("reward_energy", -10)
        self.created_at = time.time()
        self.deadline = float(deadline)
        self.assigned_to = None
        self.status = "pending"   # pending / running / completed / failed / expired
        self.result = None
        self.completed_at = None
        self.attempts = 0

    def is_expired(self) -> bool:
        """是否已超时。"""
        return (time.time() - self.created_at) > self.deadline

    def to_dict(self) -> dict:
        """序列化为 dict。"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "description": self.description,
            "difficulty": self.difficulty,
            "reward_food": self.reward_food,
            "reward_energy": self.reward_energy,
            "created_at": self.created_at,
            "deadline": self.deadline,
            "status": self.status,
            "attempts": self.attempts,
            "assigned_to": getattr(self.assigned_to, "_name_obj", None) if self.assigned_to else None,
            "result": self.result,
            "completed_at": self.completed_at,
        }


class ExternalTaskSystem:
    """外部任务系统。"""

    def __init__(self, environment, observer=None, naming=None):
        """初始化外部任务系统。

        Args:
            environment: 共享 Environment（Borg 单例），用于读取 population、
                         修改 food_available、广播事件。
            observer: 可选的 Observer，用于在奖励/惩罚时调用 energize/heal。
            naming: 可选的 NamingSystem，用于按 ID 查找 life_form。
        """
        self._env = environment
        self._observer = observer
        self._naming = naming
        self._lock = threading.RLock()
        self._pending: deque = deque()
        self._running: dict = {}               # task_id -> (task, life_form)
        self._completed: deque = deque(maxlen=200)
        self._failed: deque = deque(maxlen=200)
        self._history: deque = deque(maxlen=1000)
        self._task_counter = 0
        self._species_performance = defaultdict(lambda: {
            "assigned": 0, "completed": 0, "failed": 0,
        })
        # 自动分配线程
        self._auto_assign_thread = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # 注入
    # ------------------------------------------------------------------

    def inject(self, task_type, description="", difficulty=None,
               reward_food=None, reward_energy=None, deadline=300.0) -> Task:
        """注入一个任务到 pending 队列。"""
        if task_type not in TASK_TYPES:
            raise ValueError(f"未知任务类型: {task_type}")
        with self._lock:
            self._task_counter += 1
            task_id = f"task-{self._task_counter:04d}"
            task = Task(
                task_id=task_id, task_type=task_type,
                description=description, difficulty=difficulty,
                reward_food=reward_food, reward_energy=reward_energy,
                deadline=deadline,
            )
            self._pending.append(task)
            self._history.append({
                "action": "inject", "task_id": task_id, "time": time.time(),
            })
        self._env.broadcast_event("task_injected", {
            "task_id": task_id, "task_type": task_type,
        })
        return task

    def inject_batch(self, tasks: list) -> list:
        """批量注入。tasks 是 [(task_type, description), ...] 列表。"""
        result = []
        for t in tasks:
            if isinstance(t, str):
                result.append(self.inject(t))
            elif isinstance(t, dict):
                result.append(self.inject(**t))
            elif isinstance(t, (tuple, list)) and len(t) >= 1:
                kw = {"task_type": t[0]}
                if len(t) > 1:
                    kw["description"] = t[1]
                result.append(self.inject(**kw))
        return result

    def inject_random(self, n: int = 1) -> list:
        """随机注入 N 个任务。"""
        result = []
        types = list(TASK_TYPES.keys())
        for _ in range(n):
            t = random.choice(types)
            result.append(self.inject(t))
        return result

    # ------------------------------------------------------------------
    # 分配
    # ------------------------------------------------------------------

    def _find_eligible_worker(self, task: Task):
        """为 task 找一个合格的 worker。

        条件：醒着 / 健康≥40 / 能量≥30 / 成年 / 没在忙。
        """
        species = TASK_TYPES.get(task.task_type, {}).get("species")
        if not species:
            return None
        with self._env._lock:
            candidates = [
                lf for lf in self._env.population
                if getattr(lf, "species", "") == species
                and getattr(lf, "_alive", False)
            ]
        for lf in candidates:
            try:
                with lf._lock:
                    if getattr(lf, "sleeping", False):
                        continue
                    if getattr(lf, "health", 0) < 40:
                        continue
                    if getattr(lf, "energy", 0) < 30:
                        continue
                    from .digital_life_form import LifeStage
                    if getattr(lf, "life_stage", None) not in (
                            LifeStage.ADULT, LifeStage.MIDDLE):
                        continue
                    # 没在跑其他任务
                    if any(t[1] is lf for t in self._running.values()):
                        continue
                    return lf
            except Exception:
                continue
        return None

    def assign(self, task: Task, life_form) -> dict:
        """把任务手动分配给指定 life_form。"""
        with self._lock:
            try:
                self._pending.remove(task)
            except ValueError:
                pass
            task.assigned_to = life_form
            task.status = "running"
            task.attempts += 1
            self._running[task.task_id] = (task, life_form)
            self._history.append({
                "action": "assign", "task_id": task.task_id,
                "time": time.time(),
            })
            sp = getattr(life_form, "species", "unknown")
            self._species_performance[sp]["assigned"] += 1
        self._env.broadcast_event("task_assigned", {
            "task_id": task.task_id, "task_type": task.task_type,
            "worker": getattr(life_form, "_name_obj", ""),
        })
        return {"ok": True, "task_id": task.task_id}

    def auto_assign(self) -> int:
        """自动为 pending 中的任务寻找 worker 并分配，返回分配数量。"""
        with self._lock:
            pending_snapshot = list(self._pending)
        assigned = 0
        for task in pending_snapshot:
            if task.is_expired():
                continue
            worker = self._find_eligible_worker(task)
            if worker is None:
                continue
            self.assign(task, worker)
            assigned += 1
        return assigned

    def start_auto_assigner(self, interval: float = 5.0) -> None:
        """启动后台自动分配线程。"""
        with self._lock:
            if (self._auto_assign_thread is not None
                    and self._auto_assign_thread.is_alive()):
                return
            self._stop_event.clear()
            t = threading.Thread(
                target=self._auto_assign_loop,
                args=(float(interval),),
                daemon=True,
                name="external-task-auto-assigner",
            )
            self._auto_assign_thread = t
            t.start()

    def stop_auto_assigner(self) -> None:
        """停止后台自动分配线程。"""
        self._stop_event.set()
        t = self._auto_assign_thread
        if t is not None and t.is_alive():
            t.join(timeout=2.0)
        with self._lock:
            self._auto_assign_thread = None

    def _auto_assign_loop(self, interval: float) -> None:
        """自动分配循环。"""
        while not self._stop_event.is_set():
            try:
                self.auto_assign()
                self.try_complete_assigned()
                self.check_expired()
            except Exception:
                pass
            self._stop_event.wait(interval)

    # ------------------------------------------------------------------
    # 任务执行
    # ------------------------------------------------------------------

    def execute(self, task: Task, life_form) -> dict:
        """执行一个任务（同步）。

        成功概率：0.7 + 0.05*(energy-50) - 0.1*difficulty
        老年期 ×0.5
        """
        with life_form._lock:
            energy = life_form.energy
            from .digital_life_form import LifeStage
            is_elderly = life_form.life_stage == LifeStage.ELDERLY

        # 成功概率
        p = 0.7 + 0.05 * (energy - 50) - 0.1 * task.difficulty
        p = max(0.05, min(0.95, p))
        if is_elderly:
            p *= 0.5
        success = random.random() < p

        # 消耗能量
        with life_form._lock:
            life_form.energy = max(0.0, life_form.energy + task.reward_energy)
            # 调用 job_skill
            try:
                life_form.job_skill()
            except Exception:
                pass

        # 奖励/惩罚
        if success:
            with self._env._lock:
                self._env.food_available = min(
                    2000.0, self._env.food_available + task.reward_food)
            if self._observer is not None and self._naming is not None:
                lid = self._naming.get_id(life_form)
                if lid:
                    self._observer.energize(lid, 10)

        return {
            "task_id": task.task_id,
            "success": success,
            "probability": p,
            "reward_food": task.reward_food if success else 0,
            "reward_energy": task.reward_energy,
        }

    def try_complete_assigned(self) -> int:
        """尝试完成所有 running 中的任务，返回处理数量。

        注意：返回值是"本轮处理过的任务数"，无论成功、失败还是 worker 死亡，
        只要任务从 running 队列中被取出处理过就算一次。
        """
        with self._lock:
            running_snapshot = list(self._running.items())
        completed = 0
        for task_id, (task, life_form) in running_snapshot:
            if not getattr(life_form, "_alive", False):
                # worker 死了，任务失败
                with self._lock:
                    self._running.pop(task_id, None)
                    task.status = "failed"
                    task.result = "worker died"
                    task.completed_at = time.time()
                    self._failed.append(task)
                    sp = getattr(life_form, "species", "unknown")
                    self._species_performance[sp]["failed"] += 1
                    self._history.append({
                        "action": "complete", "task_id": task_id,
                        "success": False, "reason": "worker_died",
                        "time": time.time(),
                    })
                completed += 1
                self._env.broadcast_event("task_completed", {
                    "task_id": task_id, "success": False,
                    "worker": getattr(life_form, "_name_obj", ""),
                })
                continue
            # 执行
            result = self.execute(task, life_form)
            with self._lock:
                self._running.pop(task_id, None)
                if result["success"]:
                    task.status = "completed"
                    task.result = "success"
                    self._completed.append(task)
                    sp = getattr(life_form, "species", "unknown")
                    self._species_performance[sp]["completed"] += 1
                else:
                    task.status = "failed"
                    task.result = "failed"
                    self._failed.append(task)
                    sp = getattr(life_form, "species", "unknown")
                    self._species_performance[sp]["failed"] += 1
                task.completed_at = time.time()
                self._history.append({
                    "action": "complete", "task_id": task_id,
                    "success": result["success"], "time": time.time(),
                })
            completed += 1
            self._env.broadcast_event("task_completed", {
                "task_id": task_id, "success": result["success"],
                "worker": getattr(life_form, "_name_obj", ""),
            })
        return completed

    def check_expired(self) -> int:
        """检查 pending 中超时的任务，返回超时数。"""
        with self._lock:
            still_pending = deque()
            expired_count = 0
            for task in self._pending:
                if task.is_expired():
                    task.status = "expired"
                    task.completed_at = time.time()
                    self._failed.append(task)
                    expired_count += 1
                    self._env.broadcast_event("task_expired", {
                        "task_id": task.task_id,
                    })
                else:
                    still_pending.append(task)
            self._pending = still_pending
        return expired_count

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_pending(self) -> list:
        with self._lock:
            return list(self._pending)

    def get_running(self) -> list:
        with self._lock:
            return [t for t, _ in self._running.values()]

    def get_recent_completed(self, n: int = 20) -> list:
        with self._lock:
            return list(self._completed)[-n:]

    def get_species_performance(self) -> dict:
        with self._lock:
            return {k: dict(v) for k, v in self._species_performance.items()}

    def performance_report(self) -> str:
        """物种绩效文本报告。"""
        with self._lock:
            perf = {k: dict(v) for k, v in self._species_performance.items()}
        lines = ["=== 物种绩效报告 ==="]
        for sp, p in perf.items():
            total = p["completed"] + p["failed"]
            rate = p["completed"] / total if total > 0 else 0
            lines.append(
                f"  {sp}: 分配 {p['assigned']}  完成 {p['completed']}  "
                f"失败 {p['failed']}  成功率 {rate:.1%}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """返回系统整体状态。"""
        with self._lock:
            return {
                "pending": len(self._pending),
                "running": len(self._running),
                "completed": len(self._completed),
                "failed": len(self._failed),
                "history_size": len(self._history),
                "task_counter": self._task_counter,
                "species_performance": {k: dict(v) for k, v in self._species_performance.items()},
                "auto_assigner_running": (
                    self._auto_assign_thread is not None
                    and self._auto_assign_thread.is_alive()
                ),
            }
