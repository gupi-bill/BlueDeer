"""Provider 抽象。第一版只实现 MockProvider，真实 LLM 后续接入。"""

import json
import urllib.request
import urllib.error
import logging

logger = logging.getLogger(__name__)


class BaseProvider:
    name = "base"

    def generate(self, text: str, context=None, system: str | None = None) -> str:
        raise NotImplementedError


class MockProvider(BaseProvider):
    name = "mock"

    def generate(self, text: str, context=None, system: str | None = None) -> str:
        return f"FINAL: [Mock回复] 你说的是：{text}"


class OllamaProvider(BaseProvider):
    name = "ollama"

    def __init__(self, model: str = "qwen2.5vl:7b", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def generate(self, text: str, context=None, system: str | None = None) -> str:
        """调用 Ollama /api/generate 接口，返回生成的文本。"""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": text,
            "stream": False,
        }
        if system:
            payload["system"] = system
        body = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("response", "[Ollama] 无响应内容")
        except urllib.error.URLError as e:
            logger.error(f"Ollama 连接失败: {e}")
            return f"[Ollama 错误] 无法连接到 {self.base_url}，请确保 Ollama 已启动。"
        except Exception as e:
            logger.error(f"Ollama 生成失败: {e}")
            return f"[Ollama 错误] {str(e)}"


class OpenAIProvider(BaseProvider):
    """OpenAI 兼容 API（chat/completions），支持任意兼容中转。"""

    name = "openai"

    def __init__(self, api_base: str = "", api_key: str = "", model: str = ""):
        self.api_base = (api_base or "").rstrip("/")
        self.api_key = api_key
        self.model = model or "gpt-4o-mini"

    def generate(self, text: str, context=None, system: str | None = None) -> str:
        if not self.api_base:
            return "[API 错误] 未配置 api_base。"
        url = f"{self.api_base}/chat/completions"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": text})
        payload = {"model": self.model, "messages": messages}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content")
                    or "[API] 无响应内容"
                )
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8")[:300]
            except Exception:
                pass
            logger.error(f"API HTTP {e.code}: {detail}")
            return f"[API 错误] HTTP {e.code}：{detail or e.reason}"
        except urllib.error.URLError as e:
            logger.error(f"API 连接失败: {e}")
            return f"[API 错误] 无法连接到 {self.api_base}。"
        except Exception as e:
            logger.error(f"API 生成失败: {e}")
            return f"[API 错误] {str(e)}"


def get_provider(name: str, **kwargs) -> BaseProvider:
    if name == "mock":
        return MockProvider()
    elif name == "ollama":
        model = kwargs.get("model", "qwen2.5vl:7b")
        base_url = kwargs.get("base_url", "http://localhost:11434")
        return OllamaProvider(model=model, base_url=base_url)
    elif name == "openai":
        return OpenAIProvider(
            api_base=kwargs.get("api_base", ""),
            api_key=kwargs.get("api_key", ""),
            model=kwargs.get("api_model", ""),
        )
    return MockProvider()
