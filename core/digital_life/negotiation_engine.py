"""commit 38：动态分工协商引擎。

零基础读者可以这样理解：
- 鹿/青鸢拆解出一个任务后，不直接指派，而是先广播给相关智能体
- 每个智能体根据自己的状态"竞标"：是否可接、信心度多少、能量够不够
- 协商引擎收集所有竞标后按评分排序，挑最合适的派活
- 如果所有候选都不可接，任务挂起并通知监工

评分规则（6 因子）：
1. 信心度 × 30  （自信能做好）
2. 能量 × 25    （体力够不够）
3. 工作量       （无→+20，轻→+10，中→0，重→-10）
4. 相关经验     （最多 +10）
5. 情绪         （低落→-10，开心→+5）
6. 可用性       （不可接直接 0 分）
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

# ----------------------------------------------------------------------
# 常量
# ----------------------------------------------------------------------

NEGOTIATION_TIMEOUT_SEC = 5.0  # 单次协商超时


# ----------------------------------------------------------------------
# NegotiationEngine 单例
# ----------------------------------------------------------------------


class NegotiationEngine:
    """动态分工协商引擎（单例）。

    零基础理解：鹿把任务需求广播出去，相关智能体各自评估并竞标，
    本引擎收集竞标后挑分数最高的派活。
    """

    _instance: NegotiationEngine | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._active: dict[str, dict] = {}  # {negotiation_id: state}
        self._history: list[dict] = []  # 历史记录（最多 200 条）
        self._biosphere_ref: Any = None

    @classmethod
    def get_instance(cls) -> NegotiationEngine:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def set_biosphere(self, biosphere: Any) -> None:
        """注入 Biosphere 引用（用于查找活体智能体）。"""
        self._biosphere_ref = biosphere

    # ---------------- 主入口 ----------------

    def _create_negotiation(
        self,
        pipeline_id: str,
        step_id: int,
        task: str,
        candidate_species: list[str],
        timeout: float,
    ) -> str:
        neg_id = "neg-" + uuid.uuid4().hex[:8]
        deadline = time.time() + timeout
        with self._lock:
            self._active[neg_id] = {
                "negotiation_id": neg_id,
                "pipeline_id": pipeline_id,
                "step_id": step_id,
                "task": task,
                "candidates": list(candidate_species),
                "started_ts": time.time(),
                "deadline": deadline,
            }
        return neg_id

    def _collect_and_score_bids(
        self, candidate_species: list[str], task: str
    ) -> list[dict]:
        bids: list[dict] = []
        for species in candidate_species:
            bid = self._collect_bid(species, task)
            if bid is not None:
                bid["score"] = self._score_bid(bid, task)
                bids.append(bid)
        bids.sort(key=lambda b: b.get("score", 0), reverse=True)
        return bids

    def _decide_winner(
        self, bids: list[dict], candidate_species: list[str]
    ) -> tuple[str, str, str, bool]:
        winner = ""
        winner_name = ""
        reason = ""
        fallback = False
        available_bids = [b for b in bids if b.get("available", False)]
        if available_bids:
            top = available_bids[0]
            winner = top.get("species", "")
            winner_name = top.get("agent_name", "")
            reason = self._explain_winner(top, available_bids)
        elif candidate_species:
            winner = candidate_species[0]
            reason = (
                f"所有候选都不可接（{len(bids)} 个竞标均 available=False），"
                f"默认指派给 {winner}"
            )
            fallback = True
        else:
            reason = "无候选物种"
        return winner, winner_name, reason, fallback

    def _record_negotiation_history(
        self,
        neg_id: str,
        pipeline_id: str,
        step_id: int,
        task: str,
        candidate_species: list[str],
        bids: list[dict],
        winner: str,
        winner_name: str,
        reason: str,
        fallback: bool,
    ) -> None:
        record = {
            "negotiation_id": neg_id,
            "pipeline_id": pipeline_id,
            "step_id": step_id,
            "task": task,
            "candidates": list(candidate_species),
            "bids": bids,
            "winner": winner,
            "winner_name": winner_name,
            "reason": reason,
            "fallback": fallback,
            "ts": time.time(),
        }
        with self._lock:
            self._history.append(record)
            if len(self._history) > 200:
                self._history = self._history[-200:]
            self._active.pop(neg_id, None)

    def negotiate(
        self,
        pipeline_id: str,
        step_id: int,
        task: str,
        candidate_species: list[str],
        timeout: float = NEGOTIATION_TIMEOUT_SEC,
    ) -> dict:
        """对一个任务发起协商。

        Args:
            pipeline_id: 所属流水线 ID
            step_id: 流水线步骤 ID
            task: 任务文本
            candidate_species: 候选物种列表
            timeout: 超时秒数

        Returns:
            {
                "ok": bool,
                "negotiation_id": str,
                "winner": str,           # 中标的物种代号（可能为空）
                "winner_name": str,      # 中标智能体的显示名
                "bids": list[dict],      # 全部竞标（含评分）
                "reason": str,           # 中标理由 / 失败原因
                "fallback": bool,        # 是否走默认指派（协商失败时）
            }
        """
        neg_id = self._create_negotiation(
            pipeline_id, step_id, task, candidate_species, timeout
        )
        bids = self._collect_and_score_bids(candidate_species, task)
        winner, winner_name, reason, fallback = self._decide_winner(
            bids, candidate_species
        )
        self._record_negotiation_history(
            neg_id,
            pipeline_id,
            step_id,
            task,
            candidate_species,
            bids,
            winner,
            winner_name,
            reason,
            fallback,
        )
        return {
            "ok": True,
            "negotiation_id": neg_id,
            "winner": winner,
            "winner_name": winner_name,
            "bids": bids,
            "reason": reason,
            "fallback": fallback,
        }

    # ---------------- 竞标收集 ----------------

    def _collect_bid(self, species: str, task: str) -> dict | None:
        """让指定物种的智能体竞标。

        策略：找该物种中第一个活着的智能体，调用其 bid_for_task。
        如果该物种没有活体智能体，返回 None。
        """
        if self._biosphere_ref is None:
            return None
        try:
            employees = getattr(self._biosphere_ref, "employees", []) or []
            for emp in employees:
                if not getattr(emp, "_alive", False):
                    continue
                if getattr(emp, "species", "") != species:
                    continue
                bid = emp.bid_for_task(task)
                if bid:
                    return bid
            # 该物种无活体——返回不可接
            return {
                "agent": species,
                "species": species,
                "agent_name": "",
                "available": False,
                "confidence": 0.0,
                "estimated_min": 0,
                "current_state": {
                    "energy": 0,
                    "emotion": "absent",
                    "current_workload": "无",
                    "mood_score": 0,
                    "pending_count": 0,
                },
                "relevant_experience_count": 0,
                "special_notes": "无活体智能体",
                "score": 0,
            }
        except Exception as e:
            return {
                "agent": species,
                "species": species,
                "agent_name": "",
                "available": False,
                "confidence": 0.0,
                "estimated_min": 0,
                "current_state": {
                    "energy": 0,
                    "emotion": "error",
                    "current_workload": "无",
                    "mood_score": 0,
                    "pending_count": 0,
                },
                "relevant_experience_count": 0,
                "special_notes": f"竞标异常: {e}",
                "score": 0,
            }

    # ---------------- 评分 ----------------

    def _score_bid(self, bid: dict, task: str) -> float:
        """6 因子评分（满分约 100）。

        1. 信心度 × 30  （0~1 → 0~30）
        2. 能量 × 25    （0~100 → 0~25）
        3. 工作量       （无→+20，轻→+10，中→0，重→-10）
        4. 相关经验     （最多 +10）
        5. 情绪         （低落→-10，开心→+5，中性→0）
        6. 可用性       （不可接直接 0 分）
        """
        # 不可接直接 0 分
        if not bid.get("available", False):
            return 0.0

        confidence = float(bid.get("confidence", 0) or 0)
        state = bid.get("current_state", {}) or {}
        energy = float(state.get("energy", 0) or 0)
        workload = state.get("current_workload", "无")
        emotion = state.get("emotion", "neutral")
        exp_count = int(bid.get("relevant_experience_count", 0) or 0)

        score = 0.0
        # 1. 信心度（0~30）
        score += confidence * 30.0
        # 2. 能量（0~25）
        score += (energy / 100.0) * 25.0
        # 3. 工作量
        if workload == "无":
            score += 20.0
        elif workload == "轻":
            score += 10.0
        elif workload == "中":
            score += 0.0
        elif workload == "重":
            score -= 10.0
        # 4. 相关经验（最多 +10）
        score += min(10.0, float(exp_count) * 2.0)
        # 5. 情绪
        if emotion == "low":
            score -= 10.0
        elif emotion == "happy":
            score += 5.0

        return round(score, 2)

    def _explain_winner(self, top: dict, all_bids: list[dict]) -> str:
        """生成中标理由。"""
        species = top.get("species", "")
        score = top.get("score", 0)
        confidence = top.get("confidence", 0)
        energy = (top.get("current_state", {}) or {}).get("energy", 0)
        exp_count = top.get("relevant_experience_count", 0)
        notes = top.get("special_notes", "")

        parts = [
            f"{species} 以 {score:.1f} 分胜出",
            f"信心度 {confidence:.2f}",
            f"能量 {energy:.0f}",
        ]
        if exp_count > 0:
            parts.append(f"相关经验 {exp_count} 条")
        if notes:
            parts.append(f"备注: {notes}")
        return "；".join(parts)

    # ---------------- 查询 ----------------

    def list_active(self) -> list[dict]:
        """列出进行中的协商。"""
        with self._lock:
            return [dict(v) for v in self._active.values()]

    def list_history(self, limit: int = 50) -> list[dict]:
        """列出协商历史（按时间倒序）。"""
        with self._lock:
            sorted_hist = sorted(
                self._history, key=lambda x: x.get("ts", 0), reverse=True
            )
            return [dict(h) for h in sorted_hist[:limit]]


# ----------------------------------------------------------------------
# 模块级便捷 API
# ----------------------------------------------------------------------


def get_negotiation_engine() -> NegotiationEngine:
    return NegotiationEngine.get_instance()
