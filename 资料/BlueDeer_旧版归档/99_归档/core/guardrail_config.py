"""BlueDeer Guardrail Config：声明式安全护栏。

对标 OpenAI Agents SDK Guardrails（InputGuardrail / OutputGuardrail）。
本实现将护栏规则从硬编码迁移为声明式配置，支持：
- 输入护栏：拦截注入 / 越权 / 敏感词
- 输出护栏：验证 schema / 敏感信息 / 长度限制
-  tripwire 异常类型（匹配 OpenAI 的 GuardrailTripwireTriggered）

用法：
    guardrails = GuardrailConfig.from_file("guardrails.yaml")
    await guardrails.check_input(agent_id, payload)
    await guardrails.check_output(agent_id, output)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("bluedeer.guardrail")


class GuardrailViolationType(Enum):
    """护栏违规类型。"""

    INPUT_INJECTION = "input.injection"
    INPUT_SENSITIVE = "input.sensitive"
    INPUT_RATE_LIMIT = "input.rate_limit"
    OUTPUT_SCHEMA = "output.schema"
    OUTPUT_SENSITIVE = "output.sensitive"
    OUTPUT_LENGTH = "output.length"


class GuardrailTripwire(Exception):
    """护栏触发异常，对应 OpenAI Agents SDK 的 GuardrailTripwireTriggered。"""

    def __init__(
        self,
        violation_type: GuardrailViolationType,
        detail: str = "",
        agent_id: str = "",
    ) -> None:
        self.violation_type = violation_type
        self.agent_id = agent_id
        super().__init__(f"[Guardrail:{violation_type.value}] {detail}")


@dataclass(slots=True)
class InputGuardrailRule:
    """输入护栏规则。"""

    rule_id: str
    type: str
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OutputGuardrailRule:
    """输出护栏规则。"""

    rule_id: str
    type: str
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GuardrailConfig:
    """护栏配置容器。"""

    input_rules: list[InputGuardrailRule] = field(default_factory=list)
    output_rules: list[OutputGuardrailRule] = field(default_factory=list)
    global_settings: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GuardrailConfig:
        input_rules = [
            InputGuardrailRule(
                rule_id=r.get("id", r.get("rule_id", "")),
                type=r.get("type", ""),
                enabled=r.get("enabled", True),
                config=r.get("config", {}),
            )
            for r in data.get("input", [])
        ]
        output_rules = [
            OutputGuardrailRule(
                rule_id=r.get("id", r.get("rule_id", "")),
                type=r.get("type", ""),
                enabled=r.get("enabled", True),
                config=r.get("config", {}),
            )
            for r in data.get("output", [])
        ]
        return cls(
            input_rules=input_rules,
            output_rules=output_rules,
            global_settings=data.get("global", {}),
        )

    @classmethod
    def from_file(cls, path: str) -> GuardrailConfig:
        if path.endswith(".yaml") or path.endswith(".yml"):
            try:
                import yaml
            except ImportError as exc:
                raise RuntimeError("读取 YAML 护栏配置需要 PyYAML: pip install pyyaml") from exc
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        elif path.endswith(".json"):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            raise ValueError(f"不支持的护栏配置文件格式: {path}")
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "input": [
                {
                    "id": r.rule_id,
                    "type": r.type,
                    "enabled": r.enabled,
                    "config": r.config,
                }
                for r in self.input_rules
            ],
            "output": [
                {
                    "id": r.rule_id,
                    "type": r.type,
                    "enabled": r.enabled,
                    "config": r.config,
                }
                for r in self.output_rules
            ],
            "global": self.global_settings,
        }


class GuardrailEngine:
    """护栏执行引擎。

    负责：
    - 遍历输入/输出规则
    - 调用对应 checker
    - 触发 GuardrailTripwire 异常
    """

    def __init__(self, config: GuardrailConfig) -> None:
        self._config = config
        self._checkers: dict[str, Any] = {
            "injection": self._check_injection,
            "sensitive": self._check_sensitive,
            "length": self._check_length,
            "schema": self._check_schema,
            "rate_limit": self._check_rate_limit,
        }
        self._rate_limit_counters: dict[str, list[float]] = {}

    async def check_input(self, agent_id: str, payload: dict[str, Any]) -> None:
        """检查输入 payload，违规则抛 GuardrailTripwire。"""
        text = self._extract_text(payload)
        for rule in self._config.input_rules:
            if not rule.enabled:
                continue
            checker = self._checkers.get(rule.type)
            if checker is None:
                logger.warning("未知输入护栏规则类型: %s", rule.type)
                continue
            checker(agent_id, text, rule.config, direction="input")

    async def check_output(self, agent_id: str, output: dict[str, Any]) -> None:
        """检查输出，违规则抛 GuardrailTripwire。"""
        text = self._extract_text(output)
        for rule in self._config.output_rules:
            if not rule.enabled:
                continue
            checker = self._checkers.get(rule.type)
            if checker is None:
                logger.warning("未知输出护栏规则类型: %s", rule.type)
                continue
            checker(agent_id, text, rule.config, direction="output")

    def _extract_text(self, payload: dict[str, Any]) -> str:
        parts = []
        for key in ("query", "prompt", "content", "text", "message"):
            val = payload.get(key)
            if isinstance(val, str):
                parts.append(val)
            elif isinstance(val, dict):
                for sub in ("content", "text"):
                    if sub in val and isinstance(val[sub], str):
                        parts.append(val[sub])
        return " ".join(parts)

    def _check_injection(
        self, agent_id: str, text: str, config: dict[str, Any], direction: str
    ) -> None:
        patterns = config.get("patterns", [])
        if not patterns:
            return
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                raise GuardrailTripwire(
                    GuardrailViolationType.INPUT_INJECTION,
                    detail=f"匹配注入模式: {pattern[:50]}",
                    agent_id=agent_id,
                )

    def _check_sensitive(
        self, agent_id: str, text: str, config: dict[str, Any], direction: str
    ) -> None:
        keywords = config.get("keywords", [])
        if not keywords:
            return
        found = [kw for kw in keywords if kw.lower() in text.lower()]
        if found:
            vtype = (
                GuardrailViolationType.INPUT_SENSITIVE
                if direction == "input"
                else GuardrailViolationType.OUTPUT_SENSITIVE
            )
            raise GuardrailTripwire(
                vtype,
                detail=f"命中敏感词: {found}",
                agent_id=agent_id,
            )

    def _check_length(
        self, agent_id: str, text: str, config: dict[str, Any], direction: str
    ) -> None:
        max_len = config.get("max_chars", config.get("max_length", 0))
        if max_len and len(text) > max_len:
            raise GuardrailTripwire(
                GuardrailViolationType.OUTPUT_LENGTH,
                detail=f"输出过长: {len(text)} > {max_len}",
                agent_id=agent_id,
            )

    def _check_schema(
        self, agent_id: str, text: str, config: dict[str, Any], direction: str
    ) -> None:
        required_fields = config.get("required_fields", [])
        if not required_fields:
            return
        missing = [f for f in required_fields if f not in text]
        if missing:
            raise GuardrailTripwire(
                GuardrailViolationType.OUTPUT_SCHEMA,
                detail=f"输出缺字段: {missing}",
                agent_id=agent_id,
            )

    def _check_rate_limit(
        self, agent_id: str, text: str, config: dict[str, Any], direction: str
    ) -> None:
        window = config.get("window_seconds", 60)
        max_requests = config.get("max_requests", 10)
        key = f"{agent_id}:{direction}"
        now = __import__("time").time()
        window_start = now - window
        self._rate_limit_counters.setdefault(key, [])
        self._rate_limit_counters[key] = [
            t for t in self._rate_limit_counters[key] if t > window_start
        ]
        self._rate_limit_counters[key].append(now)
        if len(self._rate_limit_counters[key]) > max_requests:
            raise GuardrailTripwire(
                GuardrailViolationType.INPUT_RATE_LIMIT,
                detail=f"频率超限: {len(self._rate_limit_counters[key])} 次 / {window}s",
                agent_id=agent_id,
            )

    def reload(self, config: GuardrailConfig) -> None:
        """热重载护栏配置。"""
        self._config = config
        logger.info("护栏配置已热重载")
