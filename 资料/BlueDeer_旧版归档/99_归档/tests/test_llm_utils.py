"""Tests for core.llm_utils module."""

from __future__ import annotations

from core.llm_utils import (
    build_prompt,
    extract_token_usage,
    parse_numbered_tasks,
    parse_tasks_from_json,
    safe_get,
)


class TestBuildPrompt:
    def test_single_part(self):
        assert build_prompt("hello") == "hello"

    def test_multiple_parts(self):
        result = build_prompt("hello", "world", separator=" ")
        assert result == "hello world"

    def test_empty_parts_filtered(self):
        result = build_prompt("hello", "", "world")
        assert result == "hello\n\nworld"

    def test_custom_separator(self):
        result = build_prompt("a", "b", separator=" | ")
        assert result == "a | b"


class TestParseTasksFromJson:
    def test_valid_json_array(self):
        content = '[{"description": "task 1", "type": "code"}]'
        tasks = parse_tasks_from_json(content)
        assert len(tasks) == 1
        assert tasks[0]["description"] == "task 1"
        assert tasks[0]["type"] == "code"

    def test_empty_description_filtered(self):
        content = '[{"description": "", "type": "code"}]'
        tasks = parse_tasks_from_json(content)
        assert len(tasks) == 0

    def test_default_type(self):
        content = '[{"description": "task 1"}]'
        tasks = parse_tasks_from_json(content)
        assert tasks[0]["type"] == "auto"

    def test_invalid_json_returns_empty(self):
        tasks = parse_tasks_from_json("not json")
        assert tasks == []

    def test_non_list_returns_empty(self):
        tasks = parse_tasks_from_json('{"key": "value"}')
        assert tasks == []


class TestParseNumberedTasks:
    def test_valid_numbered_list(self):
        content = "1. task one\n2. task two\n3. task three"
        tasks = parse_numbered_tasks(content)
        assert len(tasks) == 3
        assert tasks[0]["description"] == "task one"
        assert tasks[2]["description"] == "task three"

    def test_ignores_non_numbered(self):
        content = "1. task one\nnot a task\n2. task two"
        tasks = parse_numbered_tasks(content)
        assert len(tasks) == 2

    def test_empty_description_filtered(self):
        content = "1. \n2. task two"
        tasks = parse_numbered_tasks(content)
        assert len(tasks) == 1


class TestSafeGet:
    def test_existing_key(self):
        data = {"key": "value"}
        assert safe_get(data, "key") == "value"

    def test_missing_key_returns_default(self):
        data = {"key": "value"}
        assert safe_get(data, "missing") is None
        assert safe_get(data, "missing", "default") == "default"

    def test_non_dict_returns_default(self):
        assert safe_get("not a dict", "key") is None
        assert safe_get("not a dict", "key", "default") == "default"


class TestExtractTokenUsage:
    def test_valid_response(self):
        class Response:
            tokens_in = 100
            tokens_out = 50

        usage = extract_token_usage(Response())
        assert usage.tokens_in == 100
        assert usage.tokens_out == 50

    def test_missing_attributes_returns_zero(self):
        class EmptyResponse:
            pass

        usage = extract_token_usage(EmptyResponse())
        assert usage.tokens_in == 0
        assert usage.tokens_out == 0

    def test_exception_returns_zero(self):
        usage = extract_token_usage(None)
        assert usage.tokens_in == 0
        assert usage.tokens_out == 0
