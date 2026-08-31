"""Debugger 单元测试（适配当前 Debugger API）。"""

from __future__ import annotations

import pytest

from core.debugger import Debugger


class TestDebugger:
    @pytest.fixture
    def debugger(self):
        dbg = Debugger()
        dbg.enable()
        return dbg

    def test_create_debugger(self, debugger):
        assert debugger._spans == {}

    def test_record_span_and_summary(self, debugger):
        debugger.record_span(
            trace_id="t1",
            component="Agent",
            action="handle",
            task_id="task-1",
        )
        summaries = debugger.summary()
        assert len(summaries) == 1
        assert summaries[0].trace_id == "t1"

    def test_summary_filter_by_trace(self, debugger):
        debugger.record_span(trace_id="t1", component="A", action="x")
        debugger.record_span(trace_id="t2", component="B", action="y")
        summaries = debugger.summary(trace_id="t1")
        assert len(summaries) == 1
        assert summaries[0].trace_id == "t1"

    def test_summary_empty(self, debugger):
        assert debugger.summary() == []

    def test_watch_variable(self, debugger):
        debugger.watch_variable("x")
        assert debugger.watch_variable("x") is None

    def test_watch_variable_missing(self, debugger):
        assert debugger.watch_variable("missing") is None
