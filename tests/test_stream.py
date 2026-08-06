"""Tests for core.stream module."""

from __future__ import annotations

import pytest

from core.stream import Stream


class TestStream:
    @pytest.fixture
    def stream(self):
        return Stream()

    def test_create_stream(self, stream):
        assert len(stream) == 0

    def test_add_message(self, stream):
        msg_id = stream.add({"event": "click", "user": "alice"})
        assert msg_id is not None
        assert len(stream) == 1

    def test_add_many(self, stream):
        ids = stream.add_many([{"event": "a"}, {"event": "b"}])
        assert len(ids) == 2
        assert len(stream) == 2

    def test_range(self, stream):
        stream.add({"event": "a"})
        stream.add({"event": "b"})
        msgs = stream.range()
        assert len(msgs) == 2

    def test_revrange(self, stream):
        stream.add({"event": "a"})
        stream.add({"event": "b"})
        msgs = stream.revrange()
        assert len(msgs) == 2
        assert msgs[0][1]["event"] == "b"

    def test_first_last_id(self, stream):
        stream.add({"event": "a"})
        stream.add({"event": "b"})
        assert stream.first_id() is not None
        assert stream.last_id() is not None

    def test_trim(self, stream):
        for i in range(10):
            stream.add({"event": f"e{i}"})
        trimmed = stream.trim(5)
        assert trimmed == 5
        assert len(stream) == 5

    def test_create_group(self, stream):
        group = stream.create_group("workers")
        assert group.name == "workers"

    def test_create_duplicate_group_raises(self, stream):
        stream.create_group("workers")
        with pytest.raises(ValueError, match="组 .* 已存在"):
            stream.create_group("workers")

    def test_delete_group(self, stream):
        stream.create_group("workers")
        assert stream.delete_group("workers") is True
        assert stream.delete_group("nonexistent") is False


class TestConsumerGroup:
    @pytest.fixture
    def stream_with_group(self):
        stream = Stream()
        group = stream.create_group("workers")
        return stream, group

    def test_read(self, stream_with_group):
        stream, group = stream_with_group
        stream.add({"event": "a"})
        msgs = group.read("worker-1", count=10)
        assert len(msgs) == 1
        assert msgs[0][1]["event"] == "a"

    def test_ack(self, stream_with_group):
        stream, group = stream_with_group
        stream.add({"event": "a"})
        msgs = group.read("worker-1", count=10)
        acked = group.ack("worker-1", msgs[0][0])
        assert acked == 1

    def test_pending(self, stream_with_group):
        stream, group = stream_with_group
        stream.add({"event": "a"})
        group.read("worker-1", count=10)
        pending = group.pending()
        assert len(pending) == 1
