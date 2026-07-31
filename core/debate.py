"""BlueDeer 辩论校验器：高风险任务多方 Agent 交叉验证。

融合项目3 make-it-heavy 多视角辩论 + 项目45 TradingAgents 多角色辩论决策。
高风险任务类型（安全审计、架构重构、部署）自动分发给多个 Agent 独立推演，
收集结果后做共识校验：多数一致则采纳，分歧则标记人工复核。

纯标准库，无第三方依赖。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable

from core.task import Task, TaskResult, TaskStatus

logger = logging.getLogger("bluedeer.debate")

# 触发辩论校验的高风险任务类型
_HIGH_RISK_TYPES = frozenset({"security_audit", "architecture_refactor", "deploy"})


class DebateVerdict(Enum):
    """辩论结论。"""
    CONSENSUS = "consensus"          # 多数一致，采纳
    DISSENT = "dissent"              # 存在分歧，需人工复核
    INSUFFICIENT = "insufficient"    # 参与者不足


@dataclass
class DebateResult:
    """辩论校验结果。"""
    verdict: DebateVerdict
    consensus_result: TaskResult | None = None       # 共识结果（CONSENSUS 时非空）
    dissent_results: list[TaskResult] = field(default_factory=list)
    participants: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """是否通过（达成共识）。"""
        return self.verdict == DebateVerdict.CONSENSUS


# 分发函数类型：(task, agent_id) -> TaskResult
DispatchFn = Callable[[Task, str], Awaitable[TaskResult]]


@dataclass
class ArgumentSubmission:
    """辩论中的一次论点提交。"""
    participant: str
    content: str
    scores: list[int] = field(default_factory=list)

    @property
    def avg_score(self) -> float:
        if not self.scores:
            return 0.0
        return sum(self.scores) / len(self.scores)


class DebateVerifier:
    """辩论校验器。

    对高风险任务分发给多个 Agent 独立推演，交叉验证结果一致性。
    融合项目3 make-it-heavy + 项目45 TradingAgents。

    用法：
        verifier = DebateVerifier()
        if verifier.is_high_risk(task.type):
            result = await verifier.verify(task, ["squirrel", "fox"], dispatch_fn)
            if not result.passed:
                # 分歧，需人工复核
                ...
    """

    def __init__(self, min_participants: int = 2, min_consensus: int = 2) -> None:
        self._min_participants = max(2, min_participants)
        self._min_consensus = max(2, min_consensus)
        # 辩论赛模式
        self._current_topic: str = ""
        self._participants: list[str] = []
        self._arguments: dict[str, ArgumentSubmission] = {}
        self._started: bool = False

    @staticmethod
    def is_high_risk(task_type: str) -> bool:
        """判断任务类型是否需要辩论校验。"""
        return task_type in _HIGH_RISK_TYPES

    async def verify(
        self,
        task: Task,
        agent_ids: list[str],
        dispatch: DispatchFn,
    ) -> DebateResult:
        """对任务执行多方辩论校验。

        Args:
            task: 待校验任务。
            agent_ids: 参与辩论的 Agent ID 列表。
            dispatch: 异步分发函数 (task, agent_id) -> TaskResult。

        Returns:
            DebateResult。
        """
        if len(agent_ids) < self._min_participants:
            logger.warning(
                "辩论参与者不足: %d < %d", len(agent_ids), self._min_participants,
            )
            return DebateResult(
                verdict=DebateVerdict.INSUFFICIENT,
                participants=list(agent_ids),
            )

        # 逐个分发同一任务给多个 Agent
        results: list[tuple[str, TaskResult]] = []
        for aid in agent_ids:
            try:
                r = await dispatch(task, aid)
                results.append((aid, r))
            except Exception as e:
                logger.warning("辩论参与者 %s 执行失败: %s", aid, e)

        if len(results) < self._min_consensus:
            return DebateResult(
                verdict=DebateVerdict.INSUFFICIENT,
                participants=[a for a, _ in results],
            )

        return self._check_consensus(results)

    # ---- 辩论赛模式 ----

    def start_debate(self, topic: str, participants: list[str]) -> None:
        """开启一场新辩论。
        Args:
            topic: 辩论议题。
            participants: 参与者列表。
        """
        self._current_topic = topic
        self._participants = list(participants)
        self._arguments = {}
        self._started = True
        logger.info("辩论赛开始: topic=%s, participants=%s", topic, participants)

    def submit_argument(self, participant: str, content: str) -> str:
        """提交论点。
        Args:
            participant: 参与者名称。
            content: 论点内容。
        Returns:
            论点 ID。
        """
        if not self._started:
            raise RuntimeError("辩论尚未开始，请先调用 start_debate")
        arg_id = f"{participant}_{len(self._arguments)}"
        self._arguments[arg_id] = ArgumentSubmission(participant=participant, content=content)
        logger.info("论点提交: %s by %s", arg_id, participant)
        return arg_id

    def score_argument(self, arg_id: str, judge: str, score: int) -> None:
        """评委评分。
        Args:
            arg_id: 论点 ID。
            judge: 评委名称。
            score: 分数（0-100）。
        """
        arg = self._arguments.get(arg_id)
        if arg is None:
            raise KeyError(f"论点 {arg_id} 不存在")
        arg.scores.append(score)

    def get_winner(self) -> str | None:
        """返回得分最高的参与者。"""
        if not self._arguments:
            return None
        scores: dict[str, list[int]] = {}
        for arg in self._arguments.values():
            scores.setdefault(arg.participant, []).extend(arg.scores)
        best: str | None = None
        best_avg: float = -1.0
        for participant, sc in scores.items():
            if not sc:
                continue
            avg = sum(sc) / len(sc)
            if avg > best_avg:
                best_avg = avg
                best = participant
        return best

    def _check_consensus(
        self, results: list[tuple[str, TaskResult]],
    ) -> DebateResult:
        """检查结果共识：按 status 分组，找最大一致组。"""
        by_status: dict[TaskStatus, list[tuple[str, TaskResult]]] = {}
        for aid, r in results:
            by_status.setdefault(r.status, []).append((aid, r))

        # 找最大组
        majority_status = max(by_status, key=lambda s: len(by_status[s]))
        majority_group = by_status[majority_status]
        minority_results = [
            r for s, grp in by_status.items() if s != majority_status
            for _, r in grp
        ]

        participants = [a for a, _ in results]

        if len(majority_group) >= self._min_consensus:
            # 取多数组中首个成功结果作为共识
            consensus = next(
                (r for _, r in majority_group if r.status == TaskStatus.SUCCESS),
                majority_group[0][1],
            )
            logger.info(
                "辩论达成共识: %d/%d 一致（%s）",
                len(majority_group), len(results), majority_status.value,
            )
            return DebateResult(
                verdict=DebateVerdict.CONSENSUS,
                consensus_result=consensus,
                dissent_results=minority_results,
                participants=participants,
            )

        logger.warning(
            "辩论存在分歧: 最大组 %d/%d，需人工复核",
            len(majority_group), len(results),
        )
        return DebateResult(
            verdict=DebateVerdict.DISSENT,
            dissent_results=[r for _, r in results],
            participants=participants,
        )
