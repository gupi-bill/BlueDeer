"""BlueDeer Input Validator: security input validation and sanitization."""

from __future__ import annotations

import logging
import re
import threading
from typing import Any

logger = logging.getLogger("bluedeer.validation")

MAX_PAYLOAD_SIZE = 1024 * 1024  # 1MB
MAX_STRING_LENGTH = 10000
DANGEROUS_PATTERNS = [
    re.compile(r"<script[^>]*>", re.IGNORECASE),
    re.compile(r"</script>", re.IGNORECASE),
    re.compile(r"javascript:", re.IGNORECASE),
    re.compile(r"on\w+\s*=", re.IGNORECASE),
    re.compile(r"\.\.[\\/]", re.IGNORECASE),
]


class ValidationError(Exception):
    """Raised when input validation fails."""

    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"Validation failed for '{field}': {reason}")


def validate_task_payload(payload: dict[str, Any], agent_id: str) -> None:
    if not isinstance(payload, dict):
        raise ValidationError("payload", "must be a dict")
    if len(str(payload)) > MAX_PAYLOAD_SIZE:
        raise ValidationError("payload", f"exceeds max size {MAX_PAYLOAD_SIZE}")
    for key, value in payload.items():
        _validate_value(key, value)


def _validate_value(field: str, value: Any) -> None:
    if isinstance(value, str):
        if "\x00" in value:
            raise ValidationError(field, "contains null byte")
        if len(value) > MAX_STRING_LENGTH:
            raise ValidationError(
                field, f"string exceeds max length {MAX_STRING_LENGTH}"
            )
        for pattern in DANGEROUS_PATTERNS:
            if pattern.search(value):
                raise ValidationError(
                    field, f"matches dangerous pattern: {pattern.pattern}"
                )
    elif isinstance(value, dict):
        for k, v in value.items():
            _validate_value(f"{field}.{k}", v)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _validate_value(f"{field}[{i}]", item)


def sanitize_string(value: str) -> str:
    for pattern in DANGEROUS_PATTERNS:
        value = pattern.sub("", value)
    return value[:MAX_STRING_LENGTH]


class InputValidator:
    """Central input validator for agent tasks."""

    def __init__(self, max_payload_size: int = MAX_PAYLOAD_SIZE) -> None:
        self._max_payload_size = max_payload_size

    def validate(self, payload: dict[str, Any], agent_id: str) -> None:
        validate_task_payload(payload, agent_id)

    def sanitize(self, value: str) -> str:
        return sanitize_string(value)


_global_validator: InputValidator | None = None
_validator_lock = threading.Lock()


def get_validator() -> InputValidator:
    global _global_validator
    if _global_validator is None:
        with _validator_lock:
            if _global_validator is None:
                _global_validator = InputValidator()
    return _global_validator


__all__ = [
    "InputValidator",
    "ValidationError",
    "get_validator",
    "sanitize_string",
    "validate_task_payload",
]
