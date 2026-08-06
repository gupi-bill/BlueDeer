"""长跑稳定性冒烟套件：1000 轮随机种子，验证数字生命生态不崩。

用法:
    python scripts/smoke_stability.py                  # 默认 1000 轮 × 24 tick
    python scripts/smoke_stability.py --rounds 100     # 少跑一点
    python scripts/smoke_stability.py --seed 42        # 固定基础种子（可复现）

判定标准（每轮全部满足才算通过）:
    - tick 全程无异常
    - 每只生命体 energy / health 始终在 [0, 100]
    - 环境资源（能量/植物）为有限数值，无 NaN / 负值爆表
退出码: 0 = 全绿, 1 = 有失败
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.digital_life import (
    Badger,
    Beaver,
    Butterfly,
    Deer,
    Environment,
    Fox,
    Hare,
    Hedgehog,
    Kite,
    Lark,
    Raven,
    Squirrel,
)

SPECIES_CLASSES = [
    Deer,
    Squirrel,
    Butterfly,
    Fox,
    Hedgehog,
    Beaver,
    Raven,
    Hare,
    Badger,
    Lark,
    Kite,
]

DEFAULT_ROUNDS = 1000
DEFAULT_HOURS = 24


def reset_shared_env() -> None:
    """Environment 是 Borg 单例：回收上一轮遗留的共享状态。

    只做测试隔离，不碰产品逻辑；保证每轮从干净的种群/日志开始。
    """
    env = Environment()
    with env._lock:
        for life in list(env.population):
            try:
                env.population.remove(life)
            except ValueError:
                pass
        env.event_log.clear()
        env.death_log.clear()
        env.birth_log.clear()
        env.relics.clear()
        env.relationship_events.clear()
        env.dialogue_bubbles.clear()
        env.active_messages.clear()
        env.active_eco_events.clear()
        env.zone_occupancy.clear()
        env.interaction_count.clear()
        env.eco_stats = env._init_eco_stats()


def build_world(rng: random.Random):
    """每轮重建一个独立世界：11 只动物 + 环境。"""
    env = Environment()
    life_forms = []
    for cls in SPECIES_CLASSES:
        life = cls(environment=env, gender=rng.choice(["male", "female"]))
        env.register(life)
        life_forms.append(life)
    return env, life_forms


def check_world(env: Environment, life_forms: list) -> str | None:
    """返回错误描述；None = 正常。"""
    for life in life_forms:
        e, h = life.energy, life.health
        if not (0.0 <= e <= 100.0 + 1e-6):
            return f"{type(life).__name__} energy 越界: {e}"
        if not (0.0 <= h <= 100.0 + 1e-6):
            return f"{type(life).__name__} health 越界: {h}"
    for name, val in [("food", env.food_available), ("plants", env.plant_biomass)]:
        if not isinstance(val, (int, float)) or not math.isfinite(float(val)):
            return f"环境 {name} 非有限数值: {val!r}"
        if float(val) < 0:
            return f"环境 {name} 为负: {val}"
    return None


def run_round(seed: int, hours: int) -> tuple[bool, str]:
    """单轮长跑：seed 种子跑 hours 小时。返回 (通过?, 失败原因)。"""
    rng = random.Random(seed)
    reset_shared_env()
    env, life_forms = build_world(rng)
    try:
        for _ in range(hours):
            env.tick(dt=1.0)
            for life in life_forms:
                life.tick()
        err = check_world(env, life_forms)
        return (err is None, err or "")
    except Exception as e:
        return (False, f"{type(e).__name__}: {e}")


def main() -> int:
    ap = argparse.ArgumentParser(description="BlueDeer 长跑稳定性冒烟")
    ap.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    ap.add_argument("--seed", type=int, default=0, help="基础随机种子")
    ap.add_argument("--hours", type=int, default=DEFAULT_HOURS, help="每轮模拟小时数")
    args = ap.parse_args()

    if args.rounds < 1 or args.hours < 1:
        print("rounds/hours 必须 >= 1")
        return 1

    total = args.rounds
    failed: list[tuple[int, str]] = []
    start = time.perf_counter()

    for i in range(total):
        seed = args.seed + i
        ok, reason = run_round(seed, args.hours)
        if not ok:
            failed.append((seed, reason))
            if len(failed) <= 5:
                print(f"  [失败] seed={seed} -> {reason}")

    elapsed = time.perf_counter() - start
    per_round_ms = elapsed / total * 1000
    total_ticks = total * args.hours
    print(
        f"== 稳定性结果: {total - len(failed)}/{total} 轮通过 "
        f"({total_ticks} tick, 用时 {elapsed:.1f}s, {per_round_ms:.1f}ms/轮) =="
    )
    if failed:
        print(f"\n--- 失败 {len(failed)} 轮（前 10 个种子）---")
        for seed, reason in failed[:10]:
            print(f"  seed={seed} -> {reason}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
