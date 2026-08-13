"""Advanced observability: real OpenTelemetry traces, metrics, and logs.

This is the *heavier* tier - see optimizations/observability.py for the
lightweight, zero-setup one. This tier exports genuine spans/metrics/log
records over OTLP/HTTP to a real backend with a real UI (Grafana), so you
can see a waterfall of calls, latency trends, and full error detail - not
just a text summary.

Deliberately NOT wired into the "just works" default path: it requires
somewhere to export to. Two ways to get one, both giving *you* your own
fully isolated backend (no shared infra to host or secure):

  - Local: optimizations/observability_stack.py's
    start_local_observability_stack() runs a one-image Docker stack
    (grafana/otel-lgtm) and points this optimization at
    http://localhost:4318.
  - Cloud: sign up for your own free Grafana Cloud stack, click "Configure"
    on its OpenTelemetry connection tile, and paste the OTEL_EXPORTER_OTLP_*
    values it generates into your .env (or the notebook's cloud config cell).

Both converge on the same two settings (Config.otel_exporter_otlp_endpoint
/ _headers) - the instrumentation code below never needs to know which one
it's talking to. Always HTTP/protobuf, never gRPC: pure-Python, no grpcio
native wheel to install, which matters for the Windows/ARM-Mac audience
this is built for.

Same non-hiding rule as every other optimization here: a span gets marked
as an error and a log record captures the detail, but the real
exception/error always still propagates or returns exactly as it would
without this optimization enabled.
"""

import logging
import time
from typing import Any
from urllib.parse import unquote

from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import Counter, Histogram, Meter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler, LogRecordProcessor
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanProcessor
from opentelemetry.trace import Status, StatusCode, Tracer

from coding_agent.config import Config
from coding_agent.llm.base import LLMClient, LLMError, LLMResponse
from coding_agent.llm.messages import Message
from coding_agent.optimizations.bundle import OptimizationBundle
from coding_agent.tools.base import ToolResult
from coding_agent.tools.registry import ToolExecutor

_SERVICE_NAME = "coding-agent"
_INSTRUMENTATION_NAME = "coding_agent.observability_otel"


class MissingOtelEndpointError(RuntimeError):
    """Raised when --enable observability-otel is requested but there's
    nowhere configured to export to.

    Deliberately fails fast rather than silently exporting nowhere (or
    guessing a default) - same "no silent defaults" rule as the rest of
    this project. See optimizations/observability_stack.py for the local
    path, or the module docstring above for the Grafana Cloud path.
    """


def _parse_headers(raw: str | None) -> dict[str, str]:
    """Parse OTEL_EXPORTER_OTLP_HEADERS's format: comma-separated
    key=value pairs, values percent-encoded (the exact format Grafana
    Cloud's "Configure" button generates). Empty/None -> no headers, which
    is correct for the unauthenticated local Docker path."""
    if not raw:
        return {}
    headers: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        key, _, value = pair.partition("=")
        headers[key.strip()] = unquote(value.strip())
    return headers


def build_providers(
    *,
    span_processor: SpanProcessor,
    metric_reader: MetricReader,
    log_record_processor: LogRecordProcessor,
) -> tuple[TracerProvider, MeterProvider, LoggerProvider]:
    """The testable core: given processors/readers (real OTLP-backed ones
    from build(), or in-memory ones from a test), wire up one provider per
    signal, all tagged with the same service.name resource."""
    resource = Resource.create({"service.name": _SERVICE_NAME})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(span_processor)

    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(log_record_processor)

    return tracer_provider, meter_provider, logger_provider


def _make_error_logger(logger_provider: LoggerProvider) -> logging.Logger:
    """A stdlib logger bridged into OTel logs via the standard
    LoggingHandler - so failures get emitted as real, exportable log
    records without hand-building LogRecord objects. Handlers are cleared
    first so repeated build() calls (e.g. across tests) never accumulate
    duplicate handlers on this name; propagation is off so these errors
    don't also print via the root logger's own handlers."""
    logger = logging.getLogger(_INSTRUMENTATION_NAME)
    logger.setLevel(logging.ERROR)
    logger.handlers.clear()
    logger.addHandler(LoggingHandler(logger_provider=logger_provider))
    logger.propagate = False
    return logger


class ObservabilityOtelLLMClient(LLMClient):
    """Wraps every model call in a real span + metrics + (on failure) a
    real log record. Never swallows an error - always re-raised."""

    def __init__(
        self,
        *,
        inner: LLMClient,
        tracer: Tracer,
        call_counter: Counter,
        error_counter: Counter,
        latency_histogram: Histogram,
        error_logger: logging.Logger,
    ) -> None:
        self._inner = inner
        self._tracer = tracer
        self._call_counter = call_counter
        self._error_counter = error_counter
        self._latency_histogram = latency_histogram
        self._error_logger = error_logger

    def send(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        start = time.perf_counter()
        with self._tracer.start_as_current_span("llm.call") as span:
            attributes = {"kind": "llm"}
            try:
                response = self._inner.send(system=system, messages=messages, tools=tools)
            except LLMError as error:
                elapsed_ms = _elapsed_ms(start)
                span.set_status(Status(StatusCode.ERROR, str(error)))
                span.record_exception(error)
                self._error_counter.add(1, attributes)
                self._latency_histogram.record(elapsed_ms, attributes)
                self._error_logger.error("llm.call failed: %s", error)
                raise

            elapsed_ms = _elapsed_ms(start)
            span.set_attribute("llm.model", response.model)
            span.set_attribute("llm.input_tokens", response.usage.input_tokens)
            span.set_attribute("llm.output_tokens", response.usage.output_tokens)
            self._call_counter.add(1, attributes)
            self._latency_histogram.record(elapsed_ms, attributes)
            return response


class ObservabilityOtelToolRegistry:
    """Implements ToolExecutor: wraps every tool call in a real span +
    metrics + (on failure) a real log record. Never swallows an error."""

    def __init__(
        self,
        *,
        inner: ToolExecutor,
        tracer: Tracer,
        call_counter: Counter,
        error_counter: Counter,
        latency_histogram: Histogram,
        error_logger: logging.Logger,
    ) -> None:
        self._inner = inner
        self._tracer = tracer
        self._call_counter = call_counter
        self._error_counter = error_counter
        self._latency_histogram = latency_histogram
        self._error_logger = error_logger

    def definitions(self) -> list[dict[str, Any]]:
        return self._inner.definitions()

    def execute(self, name: str, tool_input: dict[str, Any]) -> ToolResult:
        start = time.perf_counter()
        with self._tracer.start_as_current_span("tool.call") as span:
            attributes = {"kind": "tool", "tool.name": name}
            span.set_attribute("tool.name", name)
            try:
                result = self._inner.execute(name, tool_input)
            except Exception as error:
                elapsed_ms = _elapsed_ms(start)
                span.set_status(Status(StatusCode.ERROR, str(error)))
                span.record_exception(error)
                self._error_counter.add(1, attributes)
                self._latency_histogram.record(elapsed_ms, attributes)
                self._error_logger.error("tool.call %s failed: %s", name, error)
                raise

            elapsed_ms = _elapsed_ms(start)
            self._call_counter.add(1, attributes)
            self._latency_histogram.record(elapsed_ms, attributes)
            if result.is_error:
                span.set_status(Status(StatusCode.ERROR, result.output))
                self._error_counter.add(1, attributes)
                self._error_logger.error("tool.call %s returned an error: %s", name, result.output)
            return result


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0


def _instruments(meter: Meter) -> tuple[Counter, Counter, Histogram]:
    call_counter = meter.create_counter(
        "coding_agent.calls", description="LLM and tool calls made this session"
    )
    error_counter = meter.create_counter(
        "coding_agent.errors", description="LLM and tool call failures this session"
    )
    latency_histogram = meter.create_histogram(
        "coding_agent.latency_ms",
        unit="ms",
        description="LLM and tool call latency",
    )
    return call_counter, error_counter, latency_histogram


def build() -> OptimizationBundle:
    config = Config.from_env()
    endpoint = config.otel_exporter_otlp_endpoint
    if not endpoint:
        raise MissingOtelEndpointError(
            "--enable observability-otel needs somewhere to export "
            "traces/metrics/logs to. Set OTEL_EXPORTER_OTLP_ENDPOINT "
            "(and OTEL_EXPORTER_OTLP_HEADERS if your backend needs auth) - "
            "either run optimizations.observability_stack."
            "start_local_observability_stack() for a local Docker Grafana, "
            "or paste the values your own Grafana Cloud stack generates "
            "under Connections > OpenTelemetry > Configure."
        )
    headers = _parse_headers(config.otel_exporter_otlp_headers)

    tracer_provider, meter_provider, logger_provider = build_providers(
        span_processor=BatchSpanProcessor(
            OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces", headers=headers)
        ),
        metric_reader=PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics", headers=headers),
            export_interval_millis=2000,
        ),
        log_record_processor=BatchLogRecordProcessor(
            OTLPLogExporter(endpoint=f"{endpoint}/v1/logs", headers=headers)
        ),
    )

    tracer = tracer_provider.get_tracer(_INSTRUMENTATION_NAME)
    meter = meter_provider.get_meter(_INSTRUMENTATION_NAME)
    error_logger = _make_error_logger(logger_provider)
    call_counter, error_counter, latency_histogram = _instruments(meter)

    _set_status(ObservabilityOtelStatus(endpoint=endpoint, active=True))

    def wrap_llm_client(inner: LLMClient) -> LLMClient:
        return ObservabilityOtelLLMClient(
            inner=inner,
            tracer=tracer,
            call_counter=call_counter,
            error_counter=error_counter,
            latency_histogram=latency_histogram,
            error_logger=error_logger,
        )

    def wrap_tool_registry(inner: ToolExecutor) -> ToolExecutor:
        return ObservabilityOtelToolRegistry(
            inner=inner,
            tracer=tracer,
            call_counter=call_counter,
            error_counter=error_counter,
            latency_histogram=latency_histogram,
            error_logger=error_logger,
        )

    return OptimizationBundle(
        wrap_llm_client=wrap_llm_client, wrap_tool_registry=wrap_tool_registry
    )


class ObservabilityOtelStatus:
    """What /observability-otel reports: where data is going, and whether
    that endpoint looks like the local Docker stack (so the command can
    print a clickable Grafana URL, not just the raw OTLP endpoint)."""

    def __init__(self, *, endpoint: str, active: bool) -> None:
        self.endpoint = endpoint
        self.active = active

    @property
    def is_local(self) -> bool:
        return "localhost" in self.endpoint or "127.0.0.1" in self.endpoint

    @property
    def grafana_url(self) -> str | None:
        return "http://localhost:3000" if self.is_local else None


_last_status: ObservabilityOtelStatus | None = None


def _set_status(status: ObservabilityOtelStatus) -> None:
    global _last_status
    _last_status = status


def get_status() -> ObservabilityOtelStatus | None:
    """The status from the most recent build(), or None if this
    optimization hasn't been built yet this session."""
    return _last_status
