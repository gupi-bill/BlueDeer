"""BlueDeer 可观测性：OpenTelemetry 轻量封装。

缺省降级为 no-op，未安装 opentelemetry 三件套时整体不崩溃。
用法：
    from core.observability import Observability
    obs = Observability.setup(service_name="bluedeer")
    with obs.span("agent.run", agent_id="deer"):
        ...
"""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Any, Self

logger = logging.getLogger("bluedeer.observability")


class _NoOpSpan:
    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None) -> None:
        return None

    def set_attribute(self, key: str, value: Any) -> None:
        return None

    def set_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        return None

    def record_exception(self, exc: BaseException) -> None:
        return None


class Observability:
    """OTel 可观测性封装。

    未安装 opentelemetry 时降级为 no-op，不影响既有逻辑。
    """

    _tracer: Any = None
    _meter: Any = None
    _provider: Any = None
    _initialized: bool = False

    @classmethod
    def setup(cls, service_name: str = "bluedeer") -> Observability:
        """初始化 OTel（懒加载，失败则 no-op）。"""
        if cls._initialized:
            return cls

        try:
            from opentelemetry import metrics, trace  # type: ignore
            from opentelemetry.sdk.metrics import MeterProvider  # type: ignore
            from opentelemetry.sdk.resources import Resource  # type: ignore
            from opentelemetry.sdk.trace import TracerProvider  # type: ignore

            resource = Resource.create({"service.name": service_name})
            trace_provider = TracerProvider(resource=resource)
            trace.set_tracer_provider(trace_provider)
            cls._tracer = trace.get_tracer(service_name)

            meter_provider = MeterProvider(resource=resource)
            metrics.set_meter_provider(meter_provider)
            cls._meter = metrics.get_meter(service_name)

            cls._provider = trace_provider
            cls._initialized = True
            logger.info("Observability 已初始化（service=%s）", service_name)
        except Exception as exc:
            logger.debug("Observability 降级为 no-op: %s", exc)
            cls._tracer = None
            cls._meter = None

        return cls

    @classmethod
    def is_enabled(cls) -> bool:
        return cls._initialized and cls._tracer is not None

    @classmethod
    def span(cls, name: str, **attributes: Any) -> _NoOpSpan:
        if not cls.is_enabled():
            return _NoOpSpan()
        try:
            with cls._tracer.start_as_current_span(name) as span:
                for key, value in attributes.items():
                    span.set_attribute(key, value)
                return _NoOpSpan()  # type: ignore[return-value]
        except Exception as exc:
            logger.debug("span 异常: %s", exc)
            return _NoOpSpan()

    @classmethod
    def counter(cls, name: str, description: str = "") -> Any:
        if not cls.is_enabled() or cls._meter is None:
            return _NoOpCounter()
        try:
            return cls._meter.create_counter(name, description=description)
        except Exception as exc:
            logger.debug("counter 异常: %s", exc)
            return _NoOpCounter()

    @classmethod
    def shutdown(cls) -> None:
        if cls._provider is not None:
            try:
                cls._provider.shutdown()
            except Exception as exc:
                logger.debug("Observability shutdown 异常: %s", exc)
        cls._initialized = False
        cls._tracer = None
        cls._meter = None


class _NoOpCounter:
    def add(self, amount: int, attributes: dict[str, Any] | None = None) -> None:
        return None
