"""BlueDeer 梦境核心引擎：DreamSystem 主类（流水线 + 协同）。

P2-1 拆分自 core/dream.py。
"""

from __future__ import annotations

import logging

from core.config import get_config
from core.dream_models import DreamMemory, DreamQuality, DreamReport, NightmareAlert
from core.task import TaskResult, TaskStatus

logger = logging.getLogger("bluedeer.dream")


class DreamSystem:
    """梦境记忆自主进化系统。

    四阶段流水线：
    1. 浅睡分拣（LightSleep）：扫描任务结果，提取成功方案，评定质量
    2. REM 推演（REMDream）：对方案做模拟优化
    3. 深睡固化（DeepSleep）：将优化方案写入向量库
    4. 噩梦告警（Nightmare）：检测重复失败模式

    P6 优化：
    - 噩梦阈值可配置（默认 3）
    - 记忆质量三级评定
    - 质量分布统计
    - 节省 Token 估算
    """

    def __init__(self, nightmare_threshold: int = 3) -> None:
        self._nightmare_threshold = nightmare_threshold

    @property
    def nightmare_threshold(self) -> int:
        return self._nightmare_threshold

    @nightmare_threshold.setter
    def nightmare_threshold(self, value: int) -> None:
        if value < 1:
            raise ValueError("nightmare_threshold 必须 ≥ 1")
        self._nightmare_threshold = value

    def dream(
        self,
        results: list[TaskResult],
        agent_id_map: dict[str, str] | None = None,
    ) -> tuple[DreamReport, list[DreamMemory]]:
        """执行完整梦境流水线。

        Args:
            results: 本次梦境要处理的任务结果列表。
            agent_id_map: task_id → agent_id 映射（用于标注记忆归属）。

        Returns:
            (DreamReport, optimized_memories)：梦境报告 + 优化后待固化的记忆列表。
        """
        agent_id_map = agent_id_map or {}

        # 阶段 1：浅睡分拣（含质量评定）
        memories = self._light_sleep(results, agent_id_map)
        logger.info("浅睡分拣完成: 提取 %d 条记忆", len(memories))

        # 阶段 2：REM 推演
        optimized = self._rem_dream(memories)
        logger.info("REM 推演完成: 优化 %d 条记忆", len(optimized))

        # 阶段 3：深睡固化（返回记忆，由调用方写入向量库）
        logger.info("深睡固化: 待写入 %d 条记忆", len(optimized))

        # 阶段 4：噩梦告警
        nightmares = self._nightmare_check(results)
        if nightmares:
            logger.warning("噩梦告警: 检测到 %d 条重复失败模式", len(nightmares))

        # 统计质量分布
        quality_counts = {"normal": 0, "high": 0, "legendary": 0}
        for m in optimized:
            quality_counts[m.quality.value] += 1

        # 估算节省 Token：高质量记忆复用减少的调用
        # 粗略：每条 HIGH 节省 200 token，LEGENDARY 节省 500
        token_saved = quality_counts["high"] * 200 + quality_counts["legendary"] * 500

        report = DreamReport(
            phase="complete",
            memories_extracted=len(memories),
            memories_optimized=len(optimized),
            memories_persisted=len(optimized),
            optimized_memories=optimized,
            nightmares=nightmares,
            quality_counts=quality_counts,
            total_token_saved=token_saved,
        )

        return report, optimized

    def _light_sleep(
        self,
        results: list[TaskResult],
        agent_id_map: dict[str, str],
    ) -> list[DreamMemory]:
        """浅睡分拣：从成功任务中提取有价值方案并评定质量。"""
        memories: list[DreamMemory] = []
        for result in results:
            if result.status != TaskStatus.SUCCESS:
                continue
            if not result.output:
                continue

            content = self._extract_content(result)
            if not content:
                continue

            quality = self._assess_quality(content, result.token_usage.total)

            memory = DreamMemory(
                source_task_id=result.task_id,
                agent_id=agent_id_map.get(result.task_id, "unknown"),
                task_type=self._infer_task_type(result),
                content=content,
                quality=quality,
                metadata={
                    "token_usage": result.token_usage.total,
                    "timestamp": result.timestamp,
                    "code_lines": content.count("\n") + 1,
                },
            )
            memories.append(memory)

        return memories

    def _assess_quality(self, content: str, token_usage: int) -> DreamQuality:
        """评定记忆质量。

        - LEGENDARY：代码 > 100 行 且 token < 200
        - HIGH：代码 > 20 行 或 token < 500
        - NORMAL：其余
        """
        code_lines = content.count("\n") + 1
        _dream_cfg = get_config().dream

        if (
            code_lines > _dream_cfg.quality_legendary_code_lines
            and token_usage < _dream_cfg.quality_legendary_token
        ):
            return DreamQuality.LEGENDARY
        if (
            code_lines > _dream_cfg.quality_high_code_lines
            or token_usage < _dream_cfg.quality_high_token
        ):
            return DreamQuality.HIGH
        return DreamQuality.NORMAL

    def _extract_content(self, result: TaskResult) -> str:
        """从任务结果中提取有价值内容。"""
        output = result.output
        if isinstance(output, dict):
            if "generated_code" in output:
                return str(output["generated_code"])
            if "model_response" in output:
                return str(output["model_response"])
            return str(output)
        return str(output) if output else ""

    def _infer_task_type(self, result: TaskResult) -> str:
        """从结果推断任务类型。"""
        output = result.output
        if isinstance(output, dict):
            if "generated_code" in output:
                return "code"
            if "model_response" in output:
                return "general"
        return "general"

    def _rem_dream(self, memories: list[DreamMemory]) -> list[DreamMemory]:
        """REM 推演：对记忆做模拟优化。

        P3 用 mock 优化：标注"已优化"，不调用真实 LLM。
        P4+ 将接入真实 LLM 做方案优化推演。
        """
        optimized: list[DreamMemory] = []
        for memory in memories:
            opt_memory = DreamMemory(
                source_task_id=memory.source_task_id,
                agent_id=memory.agent_id,
                task_type=memory.task_type,
                content=memory.content,
                quality=memory.quality,
                metadata={
                    **memory.metadata,
                    "optimized": True,
                    "optimization_note": "mock 优化：已标注为高质量方案",
                },
            )
            optimized.append(opt_memory)
        return optimized

    def _nightmare_check(self, results: list[TaskResult]) -> list[NightmareAlert]:
        """噩梦告警：检测重复失败模式。"""
        error_patterns: dict[str, list[str]] = {}

        for result in results:
            if result.status != TaskStatus.FAILED or not result.error:
                continue
            error_msg = result.error
            if ":" in error_msg:
                pattern = error_msg.split(":")[0].strip()
            else:
                pattern = error_msg[:50]
            if pattern not in error_patterns:
                error_patterns[pattern] = []
            error_patterns[pattern].append(result.task_id)

        nightmares: list[NightmareAlert] = []
        for pattern, task_ids in error_patterns.items():
            if len(task_ids) >= self._nightmare_threshold:
                nightmares.append(
                    NightmareAlert(
                        error_pattern=pattern,
                        occurrences=len(task_ids),
                        task_ids=task_ids,
                    )
                )

        return nightmares

    # ============== P3 扩容：跨岗位协同推演 ==============

    def collaborative_dream(
        self,
        results_by_role: dict[str, list[TaskResult]],
    ) -> tuple[DreamReport, list[DreamMemory]]:
        """跨岗位协同梦境推演。

        将多角色（代码/美术/安全/运维）的任务结果合并到一轮梦境，
        提取跨岗位可复用的方案，标注协同来源。

        Args:
            results_by_role: {agent_id: [TaskResult, ...]} 按角色分组的任务结果。

        Returns:
            (DreamReport, memories)：合并报告 + 协同记忆。
        """
        all_results: list[TaskResult] = []
        agent_id_map: dict[str, str] = {}
        for agent_id, results in results_by_role.items():
            for r in results:
                all_results.append(r)
                agent_id_map[r.task_id] = agent_id

        report, memories = self.dream(all_results, agent_id_map=agent_id_map)

        # 标注协同来源
        for m in memories:
            m.metadata["collaborative"] = True
            m.metadata["collaborators"] = list(results_by_role.keys())

        logger.info(
            "跨岗位协同梦境: %d 角色, %d 结果, %d 记忆",
            len(results_by_role),
            len(all_results),
            len(memories),
        )
        return report, memories
