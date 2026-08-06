from __future__ import annotations

import contextvars
import json
import logging
import os
import random
import uuid
from typing import Any

_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(message)s"
_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id", default=""
)


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def get_trace_id() -> str:
    return _trace_id_var.get()


def set_trace_id(tid: str | None = None) -> str:
    tid = tid or new_trace_id()
    _trace_id_var.set(tid)
    return tid


class Tracer:
    _instance: Tracer | None = None

    def __init__(
        self,
        log_dir: str = "logs",
        level: int = logging.INFO,
        debugger: Any = None,
        sample_rate: float = 1.0,
    ) -> None:
        self._logger = logging.getLogger("bluedeer.tracer")
        self._logger.setLevel(level)
        self._logger.propagate = False
        self._debugger = debugger
        self._sample_rate = max(0.0, min(1.0, sample_rate))
        self._count = 0
        self._sampled = 0

        if not self._logger.handlers:
            os.makedirs(log_dir, exist_ok=True)
            file_handler = logging.FileHandler(
                os.path.join(log_dir, "trace.log"), encoding="utf-8"
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
            self._logger.addHandler(file_handler)
            console_handler = logging.StreamHandler()
            console_handler.setLevel(level)
            console_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
            self._logger.addHandler(console_handler)

    def _should_sample(self) -> bool:
        self._count += 1
        if random.random() < self._sample_rate:
            self._sampled += 1
            return True
        return False

    def span(self, trace_id: str, component: str, action: str, **fields: Any) -> None:
        if not self._should_sample():
            return
        record = {
            "trace_id": trace_id,
            "component": component,
            "action": action,
            **fields,
        }
        self._logger.info(json.dumps(record, ensure_ascii=False, default=str))
        if self._debugger is not None:
            self._debugger.record_span(trace_id, component, action, **fields)

    def span_ctx(self, component: str, action: str, **fields: Any) -> None:
        self.span(get_trace_id() or new_trace_id(), component, action, **fields)

    def error(
        self, trace_id: str, component: str, action: str, error: str, **fields: Any
    ) -> None:
        record = {
            "trace_id": trace_id,
            "component": component,
            "action": action,
            "error": error,
            **fields,
        }
        self._logger.error(json.dumps(record, ensure_ascii=False, default=str))
        if self._debugger is not None:
            self._debugger.record_span(
                trace_id, component, action, error=error, **fields
            )

    def error_ctx(self, component: str, action: str, error: str, **fields: Any) -> None:
        self.error(get_trace_id() or new_trace_id(), component, action, error, **fields)

    def stats(self) -> dict:
        return {
            "total": self._count,
            "sampled": self._sampled,
            "sample_rate": self._sample_rate,
        }
