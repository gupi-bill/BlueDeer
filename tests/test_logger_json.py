"""006-28: structured JSON logging for core.logger."""

from __future__ import annotations

import json
import logging

import pytest

from core.logger import JsonFormatter, get_logger, init_logging


def make_record(
    name: str = "bluedeer.test",
    level: int = logging.INFO,
    msg: str = "hello",
    extra: dict | None = None,
) -> logging.LogRecord:
    rec = logging.LogRecord(name, level, __file__, 1, msg, (), None)
    if extra:
        for key, value in extra.items():
            rec.__dict__[key] = value
    return rec


def test_json_formatter_valid_json() -> None:
    f = JsonFormatter()
    line = f.format(make_record())
    obj = json.loads(line)
    assert obj["level"] == "INFO"
    assert obj["logger"] == "bluedeer.test"
    assert obj["message"] == "hello"
    assert "ts" in obj


def test_json_formatter_includes_extra_fields() -> None:
    f = JsonFormatter()
    line = f.format(make_record(extra={"task_id": "006-28", "agent": "deer"}))
    obj = json.loads(line)
    assert obj["task_id"] == "006-28"
    assert obj["agent"] == "deer"


def test_json_formatter_escapes_non_serializable() -> None:
    f = JsonFormatter()
    line = f.format(make_record(msg="weird \u4e2d\u6587 ok"))
    obj = json.loads(line)
    assert obj["message"] == "weird 中文 ok"


def test_get_logger_namespaced() -> None:
    assert get_logger("foo").name == "bluedeer.foo"


def test_init_json_streams_valid_json(capfd: pytest.CaptureFixture[str]) -> None:
    init_logging(level="INFO", json_format=True)
    logger = get_logger("json_test")
    logger.info("hello json", extra={"task": "x"})
    out, _ = capfd.readouterr()
    line = out.strip().splitlines()[-1]
    obj = json.loads(line)
    assert obj["level"] == "INFO"
    assert obj["message"] == "hello json"
    assert obj["task"] == "x"


def test_init_text_format_unchanged(capfd: pytest.CaptureFixture[str]) -> None:
    init_logging(level="INFO")
    logger = get_logger("text_test")
    logger.info("hi")
    out, _ = capfd.readouterr()
    assert "hi" in out
    assert "| INFO" in out
