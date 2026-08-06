"""观察者干预系统 Observer。

职责：
- feed：投放食物
- drought：制造干旱（按比例减少食物）
- cold_wave：制造寒流（影响代谢率）
- force_breed：手动配对强制繁殖
- isolate / release：隔离 / 释放个体
- heal / energize：治疗 / 补充能量
- 记录所有干预动作到 _action_log

关键设计：
- cold_wave 采用"先快照后加锁"避免死锁：
  env._lock → life._lock 与 tick() 内 life._lock → env._lock 反向获取会死锁。
  所以先在 env._lock 内拷贝 population 快照，释放锁后再逐个加 life._lock。
- force_breed 临时调 birth_time 到成年期，try/finally 恢复。
"""

from __future__ import annotations

import threading
import time

from .environment import Environment
from .naming import NamingSystem


class Observer:
    """观察者：管理员干预工具。"""

    def __init__(self, environment: Environment, naming: NamingSystem | None = None):
        """初始化观察者。

        Args:
            environment: 被观察的环境（Borg 单例）。
            naming: 关联的命名系统；None 时自动新建一个。
        """
        self._env = environment
        self._naming = naming if naming is not None else NamingSystem()
        self._lock = threading.RLock()
        self._action_log = []  # 历史干预动作
        self._isolated = {}  # life_id -> life_form（隔离区）

    # ------------------------------------------------------------------
    # 内部：日志
    # ------------------------------------------------------------------

    def _log(self, entry: dict) -> None:
        """记录一条干预动作到 _action_log。"""
        with self._lock:
            full = dict(entry)
            full.setdefault("time", time.time())
            self._action_log.append(full)

    # ------------------------------------------------------------------
    # 资源干预
    # ------------------------------------------------------------------

    def feed(self, amount: float) -> dict:
        """投放食物。"""
        amount = float(amount)
        with self._env._lock:
            self._env.food_available += amount
            new_total = self._env.food_available
        result = {
            "action": "feed",
            "amount": amount,
            "new_total": new_total,
            "ok": True,
        }
        self._log(result)
        self._env.broadcast_event("intervene_feed", {"amount": amount})
        return result

    def drought(self, severity: float = 0.5) -> dict:
        """制造干旱，按 severity 比例减少食物。"""
        severity = max(0.0, min(1.0, float(severity)))
        with self._env._lock:
            original = self._env.food_available
            reduced = original * (1.0 - severity)
            self._env.food_available = reduced
        result = {
            "action": "drought",
            "severity": severity,
            "original": original,
            "new_total": reduced,
            "ok": True,
        }
        self._log(result)
        self._env.broadcast_event("intervene_drought", {"severity": severity})
        return result

    def cold_wave(self, duration_hours: float = 6.0) -> dict:
        """制造寒流，影响所有生命体代谢率。

        关键：先在 env._lock 内快照 population，释放锁后再逐个加 life._lock，
        避免与 tick() 内部 life._lock → env._lock 的反向获取顺序发生死锁。
        """
        duration_hours = max(0.0, float(duration_hours))
        # 代谢提升因子：寒流越久越严重，最多 +50%
        factor = 1.0 + min(duration_hours / 24.0, 1.0) * 0.5

        # 1. 持 env._lock 短暂快照 population
        with self._env._lock:
            snapshot = list(self._env.population)

        # 2. 释放 env._lock 后逐个修改 life.genome
        affected = 0
        for lf in snapshot:
            try:
                with lf._lock:
                    if not getattr(lf, "_alive", False):
                        continue
                    old_rate = lf.genome.get("metabolic_rate", 0.5)
                    lf.genome["metabolic_rate"] = old_rate * factor
                    affected += 1
            except Exception:
                pass

        result = {
            "action": "cold_wave",
            "duration_hours": duration_hours,
            "metabolic_factor": factor,
            "affected_count": affected,
            "ok": True,
        }
        self._log(result)
        self._env.broadcast_event(
            "intervene_cold_wave",
            {
                "duration_hours": duration_hours,
                "affected": affected,
            },
        )
        return result

    # ------------------------------------------------------------------
    # 繁殖干预
    # ------------------------------------------------------------------

    def force_breed(self, id_a: str, id_b: str) -> dict:
        """手动配对两只个体强制繁殖。

        临时把两只个体的 birth_time 调到成年期，并提升能量至繁殖阈值，
        调用 reproduce 后恢复 birth_time。
        """
        if self._naming is None:
            return {"action": "force_breed", "ok": False, "reason": "no naming system"}
        a = self._naming.get_life_form(id_a)
        b = self._naming.get_life_form(id_b)
        if a is None or b is None:
            return {
                "action": "force_breed",
                "ok": False,
                "reason": "individual not found",
            }

        # 备份原 birth_time 和 energy
        a_birth_orig = a.birth_time
        b_birth_orig = b.birth_time
        a_energy_orig = a.energy
        b_energy_orig = b.energy

        # 计算目标 birth_time：让 my_age = age_min * 1.5（确保进入繁殖区间）
        age_min = float(a.genome.get("reproduction_age_min_days", 365 * 4))
        target_birth = time.time() - age_min * 1.5 * 86400.0

        try:
            a.birth_time = target_birth
            b.birth_time = target_birth
            a.energy = max(a.energy, 50.0)
            b.energy = max(b.energy, 50.0)
            child = a.reproduce(b)
            ok = child is not None
            result = {
                "action": "force_breed",
                "parent_a": id_a,
                "parent_b": id_b,
                "child_name": getattr(child, "_name_obj", None) if child else None,
                "ok": ok,
            }
        except Exception as e:
            result = {
                "action": "force_breed",
                "ok": False,
                "reason": str(e),
            }
        finally:
            # 恢复
            a.birth_time = a_birth_orig
            b.birth_time = b_birth_orig
            # 能量不恢复（已被消耗）

        self._log(result)
        self._env.broadcast_event(
            "intervene_force_breed",
            {
                "parent_a": id_a,
                "parent_b": id_b,
                "ok": result["ok"],
            },
        )
        return result

    # ------------------------------------------------------------------
    # 隔离
    # ------------------------------------------------------------------

    def isolate(self, life_id: str) -> dict:
        """隔离个体（从 population 临时移除，保留引用以便释放）。"""
        if self._naming is None:
            return {"action": "isolate", "ok": False, "reason": "no naming"}
        lf = self._naming.get_life_form(life_id)
        if lf is None:
            return {"action": "isolate", "ok": False, "reason": "not found"}
        with self._lock:
            if life_id in self._isolated:
                return {"action": "isolate", "ok": False, "reason": "already isolated"}
            self._env.unregister(lf)
            self._isolated[life_id] = lf
        result = {"action": "isolate", "life_id": life_id, "ok": True}
        self._log(result)
        self._env.broadcast_event("intervene_isolate", {"life_id": life_id})
        return result

    def release(self, life_id: str) -> dict:
        """释放隔离个体回种群。"""
        with self._lock:
            lf = self._isolated.pop(life_id, None)
        if lf is None:
            return {
                "action": "release",
                "life_id": life_id,
                "ok": False,
                "reason": "not in isolation",
            }
        self._env.register(lf)
        result = {"action": "release", "life_id": life_id, "ok": True}
        self._log(result)
        self._env.broadcast_event("intervene_release", {"life_id": life_id})
        return result

    # ------------------------------------------------------------------
    # 治疗 / 能量
    # ------------------------------------------------------------------

    def heal(self, life_id: str, amount: float = 30.0) -> dict:
        """治疗：增加 health（上限 100）。"""
        if self._naming is None:
            return {"action": "heal", "ok": False, "reason": "no naming system"}
        lf = self._naming.get_life_form(life_id)
        if lf is None:
            return {"action": "heal", "ok": False, "reason": "not found"}
        amount = float(amount)
        with lf._lock:
            before = lf.health
            lf.health = min(100.0, lf.health + amount)
            after = lf.health
        result = {
            "action": "heal",
            "life_id": life_id,
            "before": before,
            "after": after,
            "ok": True,
        }
        self._log(result)
        return result

    def energize(self, life_id: str, amount: float = 30.0) -> dict:
        """补充能量（上限 100）。"""
        if self._naming is None:
            return {"action": "energize", "ok": False, "reason": "no naming system"}
        lf = self._naming.get_life_form(life_id)
        if lf is None:
            return {"action": "energize", "ok": False, "reason": "not found"}
        amount = float(amount)
        with lf._lock:
            before = lf.energy
            lf.energy = min(100.0, lf.energy + amount)
            after = lf.energy
        result = {
            "action": "energize",
            "life_id": life_id,
            "before": before,
            "after": after,
            "ok": True,
        }
        self._log(result)
        return result

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def action_log(self, last_n: int = 50) -> list:
        """返回最近 N 条干预记录。"""
        with self._lock:
            return list(self._action_log[-last_n:])

    def isolated_ids(self) -> list:
        """返回当前隔离的 ID 列表。"""
        with self._lock:
            return list(self._isolated.keys())

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """返回观察者整体状态。"""
        with self._lock:
            return {
                "env": self._env.status(),
                "naming": self._naming.status(),
                "action_log_count": len(self._action_log),
                "isolated_count": len(self._isolated),
                "isolated_ids": list(self._isolated.keys()),
            }
