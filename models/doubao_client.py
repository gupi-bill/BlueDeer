"""BlueDeer DoubaoClient：真实 Doubao Seed API HTTP 调用客户端。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request

from models.client import ModelClient, ModelResponse

logger = logging.getLogger("bluedeer.doubao")

# Doubao API 默认 endpoint
_DEFAULT_ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
_DEFAULT_TIMEOUT = 30
_DEFAULT_MAX_RETRIES = 3


class DoubaoClient(ModelClient):
    """真实 Doubao Seed API 客户端。

    通过 HTTP 调用 Doubao Seed API，支持超时、重试、错误处理。
    构造时读取环境变量 DOUBAO_API_KEY 和 DOUBAO_API_ENDPOINT。
    无 API Key 时实例化抛 ValueError，由 Router 决定是否回退 MockClient。

    使用 urllib.request（标准库）避免新增第三方依赖。
    异步通过 asyncio.to_thread 包装同步 HTTP 调用实现。
    """

    def __init__(
        self,
        model_name: str = "doubao-seed",
        api_key: str | None = None,
        endpoint: str | None = None,
        timeout: int = _DEFAULT_TIMEOUT,
        max_retries: int = _DEFAULT_MAX_RETRIES,
    ) -> None:
        self._model_name = model_name
        self._api_key = api_key or os.environ.get("DOUBAO_API_KEY")
        self._endpoint = endpoint or os.environ.get(
            "DOUBAO_API_ENDPOINT", _DEFAULT_ENDPOINT
        )
        self._timeout = timeout
        self._max_retries = max_retries
        self._rate_limit_remaining: int = -1
        self._rate_limit_reset: float = 0.0

        if not self._api_key:
            raise ValueError(
                "DoubaoClient 需要 API Key：请设置环境变量 DOUBAO_API_KEY "
                "或传入 api_key 参数"
            )

        logger.info(
            "DoubaoClient 初始化: model=%s, endpoint=%s", model_name, self._endpoint
        )

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def rate_limit_remaining(self) -> int:
        return self._rate_limit_remaining

    def handle_error(self, response_code: int) -> str:
        if response_code == 400:
            return "bad_request"
        elif response_code == 401:
            return "auth_error"
        elif response_code == 429:
            return "rate_limited"
        elif response_code == 500:
            return "server_error"
        elif response_code == 503:
            return "service_unavailable"
        elif 200 <= response_code < 300:
            return "ok"
        return "unknown"

    async def stream_chat(self, messages: list[dict[str, str]], **kwargs: object):
        """流式聊天，返回异步生成器。

        Yields:
            每次响应的增量内容。
        """
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 4096)
        payload = json.dumps(
            {
                "model": self._model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            }
        ).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        req = urllib.request.Request(
            self._endpoint, data=payload, headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            for line in resp:
                decoded = line.decode("utf-8").strip()
                if decoded.startswith("data: "):
                    data_str = decoded[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = (
                            chunk.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("content", "")
                        )
                        if delta:
                            yield delta
                    except json.JSONDecodeError:
                        continue

    async def complete(self, prompt: str, **kwargs: object) -> ModelResponse:
        """调用 Doubao API 完成推理。

        内置超时（30s）和重试（3 次）。
        """
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 4096)

        payload = json.dumps(
            {
                "model": self._model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        ).encode("utf-8")

        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            now = time.time()
            if self._rate_limit_remaining == 0 and now < self._rate_limit_reset:
                wait = self._rate_limit_reset - now
                logger.warning("触发频率限制，等待 %.1fs", wait)
                await asyncio.sleep(wait)

            try:
                response_data = await asyncio.to_thread(self._http_post, payload)
                resp = self._parse_response(response_data)
                return resp
            except urllib.error.HTTPError as e:
                error_type = self.handle_error(e.code)
                if error_type == "rate_limited":
                    self._rate_limit_remaining = 0
                    self._rate_limit_reset = time.time() + 30
                last_error = e
                logger.warning(
                    "DoubaoClient 调用失败（第 %d/%d 次）: code=%s type=%s",
                    attempt,
                    self._max_retries,
                    e.code,
                    error_type,
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    "DoubaoClient 调用失败（第 %d/%d 次）: %s",
                    attempt,
                    self._max_retries,
                    e,
                )

        raise RuntimeError(
            f"DoubaoClient 调用失败（重试 {self._max_retries} 次）: {last_error}"
        )

    def _http_post(self, payload: bytes) -> dict:
        """同步 HTTP POST 请求（在 to_thread 中调用）。"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        req = urllib.request.Request(
            self._endpoint, data=payload, headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            remaining = resp.headers.get("X-RateLimit-Remaining")
            if remaining is not None:
                self._rate_limit_remaining = int(remaining)
            reset = resp.headers.get("X-RateLimit-Reset")
            if reset is not None:
                self._rate_limit_reset = float(reset)
            return json.loads(resp.read().decode("utf-8"))

    def _parse_response(self, data: dict) -> ModelResponse:
        """解析 Doubao API 响应。"""
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("Doubao API 返回空 choices")

        content = choices[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)

        return ModelResponse(
            content=content,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
