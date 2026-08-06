"""Tests for core.langgraph_style module."""

from __future__ import annotations

import json
import os

import pytest

from core.langgraph_style import State, StateGraph


class TestState:
    def test_create_state(self):
        state = State()
        assert state.data == {}

    def test_set_and_get(self):
        state = State()
        state.set("key", "value")
        assert state.get("key") == "value"

    def test_get_with_default(self):
        state = State()
        assert state.get("missing", "default") == "default"


class TestStateGraph:
    def test_create_graph(self):
        graph = StateGraph()
        assert graph._nodes == {}
        assert graph._edges == {}
        assert graph._entry_point is None

    def test_add_node(self):
        graph = StateGraph()
        graph.add_node("start", lambda s: s)
        assert "start" in graph._nodes

    def test_add_edge(self):
        graph = StateGraph()
        graph.add_node("start", lambda s: s)
        graph.add_node("end", lambda s: s)
        graph.add_edge("start", "end")
        assert graph._edges["start"] == "end"

    def test_set_entry_point(self):
        graph = StateGraph()
        graph.set_entry_point("start")
        assert graph._entry_point == "start"

    def test_run_without_entry_point_raises(self):
        graph = StateGraph()
        with pytest.raises(RuntimeError, match="entry_point not set"):
            graph.run(steps=1)

    def test_run_simple_flow(self):
        graph = StateGraph()
        graph.add_node("start", lambda s: State(data={"step": 1}))
        graph.add_node("end", lambda s: State(data={"step": 2}))
        graph.add_edge("start", "end")
        graph.set_entry_point("start")
        result = graph.run(steps=5)
        assert result.data["step"] == 2

    def test_checkpoint(self):
        graph = StateGraph()
        graph.set_entry_point("start")
        snap = graph.checkpoint()
        assert "state" in snap
        assert "checkpoints" in snap


class TestCheckpointPersistence:
    def test_save_and_load_roundtrip(self, tmp_path):
        path = str(tmp_path / "ckpt.json")
        graph = StateGraph(checkpoint_path=path)
        graph.add_node("start", lambda s: s.set("step", 1) or s)
        graph.add_node("end", lambda s: s.set("step", 2) or s)
        graph.add_edge("start", "end")
        graph.set_entry_point("start")
        graph.run(steps=5)
        assert graph.checkpoints

        restored = StateGraph(checkpoint_path=path)
        assert restored._state.data.get("step") == 2
        assert restored.checkpoints == graph.checkpoints

    def test_run_appends_and_persists_each_step(self, tmp_path):
        path = str(tmp_path / "ckpt.json")
        graph = StateGraph(checkpoint_path=path)
        graph.add_node("a", lambda s: s)
        graph.add_edge("a", "a")
        graph.set_entry_point("a")
        graph.run(steps=3)
        assert len(graph.checkpoints) == 3
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        assert len(payload["checkpoints"]) == 3

    def test_load_missing_file_returns_false(self, tmp_path):
        graph = StateGraph(checkpoint_path=str(tmp_path / "nope.json"))
        assert graph._state.data == {}
        assert graph.checkpoints == []

    def test_load_corrupt_file_returns_false(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        graph = StateGraph()
        assert graph.load(str(path)) is False

    def test_save_without_path_raises(self):
        graph = StateGraph()
        with pytest.raises(ValueError, match="checkpoint_path"):
            graph.save()

    def test_explicit_save_sets_path(self, tmp_path):
        path = str(tmp_path / "ckpt.json")
        graph = StateGraph()
        graph._state.set("k", "v")
        graph.save(path)
        assert os.path.exists(path)

    def test_resume_after_reload(self, tmp_path):
        path = str(tmp_path / "ckpt.json")
        graph = StateGraph(checkpoint_path=path)
        graph._state.set("done", True)
        graph.checkpoint()
        restored = StateGraph(checkpoint_path=path)
        assert restored._state.get("done") is True
