"""BlueDeer 模型路由引擎：按任务类型自动分流，环境变量感知真实/mock 切换。

P1 扩容（A 级）：
- 任务类型 4 → 6：新增 reasoning（推理）/ multimedia（多媒体）
- 多候选模型：每个任务类型配主模型 + 备用模型列表
- 运行时故障切换：complete_with_failover 依次尝试候选，全部失败抛 RuntimeError
- 模型健康追踪：记录每个模型连续失败次数，超阈值自动降级

P0 修复（融合项目43 ponytail 多模型路由 + 项目41 PilotDeck 故障切换）：
- 降级模型加 TTL 自动恢复（30 秒后自动解除降级，避免永久黑名单）
- route_candidates 去重改为按 model_name（避免同名 MockClient 误判）
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from core.config import get_config
from models.client import ModelClient, ModelResponse
from models.mock_client import MockClient

logger = logging.getLogger("bluedeer.router")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    threshold: int = 5
    timeout: float = 30.0
    last_failure: float = 0.0

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure = time.time()
        if self.failure_count >= self.threshold:
            self.state = CircuitState.OPEN

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def try_half_open(self) -> bool:
        if (
            self.state == CircuitState.OPEN
            and time.time() - self.last_failure > self.timeout
        ):
            self.state = CircuitState.HALF_OPEN
            return True
        return False


class Router:
    """模型路由引擎。

    按任务类型映射到对应模型客户端：
    - code → Doubao-Seed-Code
    - architecture → Doubao-Seed-2.1-Pro
    - batch → Doubao-Seed-2.1-Turbo
    - voice → MiniMax-M3
    - reasoning → Doubao-Seed-2.1-Pro（P1 新增）
    - multimedia → Doubao-Vision-Pro（P1 新增）

    P2 升级：检测 DOUBAO_API_KEY 环境变量。
    - 有 Key：为每个模型创建 DoubaoClient（真实 API 调用）。
    - 无 Key：回退 MockClient（P1 行为不变）。

    P1 扩容（A 级）：
    - route_candidates(task_type) 返回主+备候选客户端列表
    - complete_with_failover(task_type, prompt) 运行时故障切换
    - 模型健康追踪：连续失败超阈值自动降级

    P0 修复：
    - 降级 TTL 自动恢复：降级超过 get_config().model.degrade_ttl_seconds 秒自动解除
    - route_candidates 按 model_name 去重（避免同名 MockClient 误判）
    """

    def __init__(self) -> None:
        self._use_real_api = bool(os.environ.get("DOUBAO_API_KEY"))
        self._clients: dict[str, ModelClient] = {}

        if self._use_real_api:
            # 延迟导入，避免无 Key 时导入失败
            from models.doubao_client import DoubaoClient

            model_names = set(get_config().model.task_model_map.values()) | {
                get_config().model.default_model
            }
            for name in model_names:
                try:
                    self._clients[name] = DoubaoClient(model_name=name)
                except ValueError:
                    logger.warning("DoubaoClient 初始化失败，回退 MockClient: %s", name)
                    self._clients[name] = MockClient(name=name)
            self._default_client = self._clients.get(
                get_config().model.default_model,
                MockClient(name=get_config().model.default_model),
            )
            logger.info("Router 模式: 真实 Doubao API")
        else:
            self._clients = {
                name: MockClient(name=name)
                for name in set(get_config().model.task_model_map.values())
            }
            self._default_client = MockClient(name=get_config().model.default_model)
            logger.info("Router 模式: MockClient（未设置 DOUBAO_API_KEY）")

        # P1 扩容：模型健康追踪（模型名 → 连续失败次数）
        self._model_failures: dict[str, int] = {}
        # 降级名单（连续失败超阈值，临时跳过）
        self._degraded: set[str] = set()
        # P0 修复：降级时间戳（模型名 → 降级时刻），用于 TTL 自动恢复
        self._degraded_at: dict[str, float] = {}
        # P0 修复：奖惩 perks 查询回调（agent_id → perks 列表）
        self._reward_query: Callable[[str], list[str]] | None = None

    def set_reward_query(self, callback: Callable[[str], list[str]]) -> None:
        """P0 修复：注入奖惩 perks 查询回调。

        callback 接受 agent_id 返回该 agent 已解锁的 perks 列表。
        若 perks 含"低成本模型优先"，complete_with_failover 会把 Turbo 模型排到候选列表前面。
        """
        self._reward_query = callback

    def route(self, task_type: str) -> ModelClient:
        """按任务类型路由到对应模型客户端。

        Args:
            task_type: 任务类型（code / architecture / batch / voice / reasoning / multimedia 等）。

        Returns:
            对应的 ModelClient 实例。
        """
        model_name = get_config().model.task_model_map.get(
            task_type, get_config().model.default_model
        )
        client = self._clients.get(model_name, self._default_client)

        logger.info(
            "路由决策: task_type=%s → model=%s (real_api=%s)",
            task_type,
            client.model_name,
            self._use_real_api,
        )
        return client

    def _recover_expired_degraded(self) -> None:
        """P0 修复：恢复超过 TTL 的降级模型。

        融合项目43 ponytail 故障自动切换 + 项目41 PilotDeck 模型故障切换。
        降级超过 get_config().model.degrade_ttl_seconds 秒自动解除，避免永久黑名单。
        """
        if not self._degraded:
            return
        now = time.time()
        expired = [
            name
            for name in list(self._degraded)
            if now - self._degraded_at.get(name, now)
            > get_config().model.degrade_ttl_seconds
        ]
        for name in expired:
            self._degraded.discard(name)
            self._degraded_at.pop(name, None)
            self._model_failures.pop(name, None)
            logger.info("模型 %s 降级已超 TTL，自动恢复", name)

    def route_candidates(self, task_type: str) -> list[ModelClient]:
        """P1 扩容：返回主模型 + 备用模型候选列表。

        故障切换时按顺序尝试。已降级的模型会被跳过。
        若所有候选都降级，强制返回主模型（最后一次机会）。

        P0 修复：按 model_name 去重（避免同名 MockClient 误判）；
        调用前先恢复超过 TTL 的降级模型。

        Args:
            task_type: 任务类型。

        Returns:
            候选 ModelClient 列表（至少 1 个）。
        """
        self._recover_expired_degraded()

        primary_name = get_config().model.task_model_map.get(
            task_type, get_config().model.default_model
        )
        fallback_names = get_config().model.task_fallbacks.get(task_type, [])

        candidates: list[ModelClient] = []
        seen_names: set[str] = set()

        # 主模型（除非降级）
        if primary_name not in self._degraded:
            client = self._clients.get(primary_name, self._default_client)
            if client.model_name not in seen_names:
                candidates.append(client)
                seen_names.add(client.model_name)

        # 备用模型（跳过降级的）
        for name in fallback_names:
            if name in self._degraded:
                continue
            client = self._clients.get(name)
            if client is not None and client.model_name not in seen_names:
                candidates.append(client)
                seen_names.add(client.model_name)

        # 全部降级，强制返回主模型
        if not candidates:
            candidates.append(self._clients.get(primary_name, self._default_client))

        return candidates

    async def complete_with_failover(
        self, task_type: str, prompt: str, *, agent_id: str = "", **kwargs: Any
    ) -> ModelResponse:
        """P1 扩容：带故障切换的模型调用。

        依次尝试主模型 + 备用模型，成功则重置该模型失败计数；
        失败则累计计数，超阈值降级。全部候选失败抛 RuntimeError。

        P0 修复：若 agent_id 非空且该 agent 已解锁"低成本模型优先" perk，
        把 Turbo 模型排到候选列表前面（融合项目43 ponytail 模型调度）。

        Args:
            task_type: 任务类型。
            prompt: 输入提示词。
            agent_id: 调用方 Agent ID（用于 perks 查询，可空）。
            **kwargs: 透传给 complete 的附加参数。

        Returns:
            ModelResponse。

        Raises:
            RuntimeError: 所有候选模型都失败。
        """
        candidates = self.route_candidates(task_type)

        # P0 修复：低成本模型优先 perk → Turbo 模型排前
        if agent_id and self._reward_query:
            try:
                perks = self._reward_query(agent_id)
            except Exception:
                perks = []
            if "低成本模型优先" in perks:
                turbo = [c for c in candidates if "Turbo" in c.model_name]
                others = [c for c in candidates if "Turbo" not in c.model_name]
                candidates = turbo + others
                logger.info(
                    "perk 命中[低成本模型优先]: agent=%s, Turbo 候选前置",
                    agent_id,
                )

        errors: list[str] = []

        for client in candidates:
            try:
                response = await client.complete(prompt, **kwargs)
                # 成功，重置失败计数
                self._model_failures[client.model_name] = 0
                logger.info(
                    "模型调用成功: task=%s model=%s",
                    task_type,
                    client.model_name,
                )
                return response
            except Exception as e:
                errors.append(f"{client.model_name}: {e}")
                self._record_failure(client.model_name)
                logger.warning(
                    "模型调用失败，尝试下一个候选: task=%s model=%s err=%s",
                    task_type,
                    client.model_name,
                    e,
                )

        raise RuntimeError(
            f"所有候选模型都失败（task={task_type}）: {'; '.join(errors)}"
        )

    def _record_failure(self, model_name: str) -> None:
        """记录模型失败，超阈值降级。"""
        count = self._model_failures.get(model_name, 0) + 1
        self._model_failures[model_name] = count
        if (
            count >= get_config().model.fail_threshold
            and model_name not in self._degraded
        ):
            self._degraded.add(model_name)
            self._degraded_at[model_name] = time.time()
            logger.error(
                "模型 %s 连续失败 %d 次，已降级（%g 秒后自动恢复）",
                model_name,
                count,
                get_config().model.degrade_ttl_seconds,
            )

    def reset_model(self, model_name: str) -> None:
        """P1 扩容：重置模型健康状态（解除降级）。"""
        self._model_failures.pop(model_name, None)
        self._degraded.discard(model_name)
        self._degraded_at.pop(model_name, None)
        logger.info("模型 %s 健康状态已重置", model_name)

    def is_degraded(self, model_name: str) -> bool:
        """P1 扩容：模型是否已降级（先检查 TTL 自动恢复）。"""
        self._recover_expired_degraded()
        return model_name in self._degraded

    def model_failure_count(self, model_name: str) -> int:
        """P1 扩容：模型连续失败次数。"""
        return self._model_failures.get(model_name, 0)

    def list_task_types(self) -> list[str]:
        """P1 扩容：列出所有支持的任务类型。"""
        return list(get_config().model.task_model_map.keys())

    @property
    def default_model(self) -> str:
        return get_config().model.default_model

    @property
    def use_real_api(self) -> bool:
        """是否使用真实 API。"""
        return self._use_real_api

    _load_balance_index: dict[str, int] = {}

    def route_to(self, model_name: str, strategy: str = "round_robin") -> ModelClient:
        """负载均衡路由。

        Args:
            model_name: 模型名或任务类型。
            strategy: round_robin | least_busy。

        Returns:
            ModelClient 实例。
        """
        if model_name in get_config().model.task_model_map:
            model_name = get_config().model.task_model_map[model_name]
        clients_for_model = [
            c for c in self._clients.values() if c.model_name == model_name
        ]
        if not clients_for_model:
            return self._default_client
        if strategy == "least_busy":
            return clients_for_model[0]
        idx = self._load_balance_index.get(model_name, 0) % len(clients_for_model)
        self._load_balance_index[model_name] = idx + 1
        return clients_for_model[idx]

    def fallback(self, model_name: str) -> ModelClient | None:
        """获取模型的降级备用客户端。"""
        config = get_config().model
        fallback_names = config.task_fallbacks.get(model_name, [])
        if not fallback_names:
            for task_type, fb_list in config.task_fallbacks.items():
                if config.task_model_map.get(task_type) == model_name and fb_list:
                    fallback_names = fb_list
                    break
        for name in fallback_names:
            client = self._clients.get(name)
            if client is not None:
                return client
        return None
