"""BlueDeer ModelClient 抽象接口。"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("bluedeer.model_client")


@dataclass
class ModelResponse:
    """模型响应。"""
    content: str
    tokens_in: int = 0
    tokens_out: int = 0


class ConnectionPool:
    """连接池管理。"""

    def __init__(self, max_connections: int = 10) -> None:
        self._max = max_connections
        self._active: set[int] = set()
        self._lock = asyncio.Lock()

    async def acquire(self) -> int:
        async with self._lock:
            if len(self._active) >= self._max:
                raise RuntimeError(f"连接池已满（{self._max}）")
            conn_id = id(self._active) + len(self._active)
            self._active.add(conn_id)
            return conn_id

    async def release(self, conn_id: int) -> None:
        async with self._lock:
            self._active.discard(conn_id)

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def available(self) -> int:
        return self._max - len(self._active)

    async def close_pool(self) -> None:
        async with self._lock:
            self._active.clear()


async def request_with_retry(
    method: str,
    url: str,
    retries: int = 3,
    timeout: int = 30,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
) -> Any:
    import urllib.request
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_error = e
            logger.warning("请求失败（第 %d/%d 次）: %s %s - %s", attempt, retries, method, url, e)
            if attempt < retries:
                await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"请求重试耗尽（{retries} 次）: {last_error}")


import json


class ModelClient(ABC):
    """模型客户端抽象基类。

    所有具体模型实现（Doubao-Seed-Code、Doubao-Seed-2.1-Pro、Turbo、MiniMax-M3 等）
    需继承此类并实现 complete 方法。
    P1 使用 MockClient 验证路由与审计链路，P2+ 接入真实 API。
    """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """模型名称。"""

    @abstractmethod
    async def complete(self, prompt: str, **kwargs: object) -> ModelResponse:
        """调用模型完成推理。

        Args:
            prompt: 输入提示词。
            **kwargs: 附加参数（temperature、max_tokens 等）。

        Returns:
            ModelResponse。
        """
