"""Tests for the advanced observability tier (observability_otel.py).

Uses the OTel SDK's own in-memory testing exporters (standard, documented
pattern) wired via build_providers() - no network, no Docker. Mirrors the
rest of this project's style: local fakes for LLMClient/ToolExecutor, no
subprocess, no HTTP, hand-built inputs.
"""

from typing import Any

from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from coding_agent.commands.observability_otel_command import ObservabilityOtelCommand
from coding_agent.llm.base import LLMClient, LLMError, LLMResponse
from coding_agent.llm.messages import Message
from coding_agent.metrics.usage import Usage
from coding_agent.optimizations import observability_otel
from coding_agent.optimizations.observability_otel import (
    MissingOtelEndpointError,
    ObservabilityOtelLLMClient,
    ObservabilityOtelStatus,
    ObservabilityOtelToolRegistry,
    _instruments,
    _make_error_logger,
    _parse_headers,
    build_providers,
)
from coding_agent.tools.base import ToolResult


class FakeClient(LLMClient):
    def __init__(self, *, error: LLMError | None = None, model: str = "fake-model") -> None:
        self._error = error
        self._model = model

    def send(
        self, *, system: str, messages: list[Message], tools: list[dict[str, Any]]
    ) -> LLMResponse:
        if self._error is not None:
            raise self._error
        return LLMResponse(
            text="ok", tool_calls=[], wants_tool_use=False,
            usage=Usage(input_tokens=7, output_tokens=3), model=self._model,
        )


class FakeToolExecutor:
    def __init__(
        self, *, result: ToolResult | None = None, raises: Exception | None = None
    ) -> None:
        self._result = result or ToolResult.ok("done")
        self._raises = raises

    def definitions(self) -> list[dict[str, Any]]:
        return [{"name": "fake_tool"}]

    def execute(self, name: str, tool_input: dict[str, Any]) -> ToolResult:
        if self._raises is not None:
            raise self._raises
        return self._result


def _wired() -> tuple:
    """One fully in-memory OTel setup: providers + instruments + fakes to
    hand to the wrapper classes under test, plus the exporters to inspect
    afterward."""
    span_exporter = InMemorySpanExporter()
    metric_reader = InMemoryMetricReader()
    log_exporter = InMemoryLogRecordExporter()

    tracer_provider, meter_provider, logger_provider = build_providers(
        span_processor=SimpleSpanProcessor(span_exporter),
        metric_reader=metric_reader,
        log_record_processor=SimpleLogRecordProcessor(log_exporter),
    )
    tracer = tracer_provider.get_tracer("test")
    meter = meter_provider.get_meter("test")
    call_counter, error_counter, latency_histogram = _instruments(meter)
    error_logger = _make_error_logger(logger_provider)
    return (
        tracer, call_counter, error_counter, latency_histogram, error_logger,
        span_exporter, metric_reader, log_exporter, logger_provider,
    )


# --- _parse_headers -------------------------------------------------------------


def test_parse_headers_empty_or_none() -> None:
    assert _parse_headers(None) == {}
    assert _parse_headers("") == {}


def test_parse_headers_single_and_multiple_pairs_with_url_decoding() -> None:
    assert _parse_headers("Authorization=Basic%20abc123") == {
        "Authorization": "Basic abc123"
    }
    assert _parse_headers("a=1,b=2") == {"a": "1", "b": "2"}


# --- ObservabilityOtelLLMClient --------------------------------------------------


def test_llm_client_emits_span_and_metrics_on_success() -> None:
    (tracer, call_counter, error_counter, latency_histogram, error_logger,
     span_exporter, metric_reader, log_exporter, _) = _wired()
    client = ObservabilityOtelLLMClient(
        inner=FakeClient(model="my-model"), tracer=tracer, call_counter=call_counter,
        error_counter=error_counter, latency_histogram=latency_histogram,
        error_logger=error_logger,
    )

    response = client.send(system="s", messages=[], tools=[])

    assert response.text == "ok"
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "llm.call"
    assert spans[0].attributes["llm.model"] == "my-model"
    assert spans[0].status.status_code == StatusCode.UNSET

    metric_names = _metric_names(metric_reader)
    assert "coding_agent.calls" in metric_names
    assert len(log_exporter.get_finished_logs()) == 0


def test_llm_client_marks_span_error_and_logs_and_reraises_on_llm_error() -> None:
    (tracer, call_counter, error_counter, latency_histogram, error_logger,
     span_exporter, metric_reader, log_exporter, _) = _wired()
    client = ObservabilityOtelLLMClient(
        inner=FakeClient(error=LLMError("rate limited")), tracer=tracer,
        call_counter=call_counter, error_counter=error_counter,
        latency_histogram=latency_histogram, error_logger=error_logger,
    )

    try:
        client.send(system="s", messages=[], tools=[])
        assert False, "expected LLMError to propagate"
    except LLMError as error:
        assert str(error) == "rate limited"

    spans = span_exporter.get_finished_spans()
    assert spans[0].status.status_code == StatusCode.ERROR
    logs = log_exporter.get_finished_logs()
    assert len(logs) == 1
    assert "rate limited" in str(logs[0].log_record.body)
    assert "coding_agent.errors" in _metric_names(metric_reader)


# --- ObservabilityOtelToolRegistry -----------------------------------------------


def test_tool_registry_emits_span_with_tool_name_on_success() -> None:
    (tracer, call_counter, error_counter, latency_histogram, error_logger,
     span_exporter, _metric_reader, log_exporter, _) = _wired()
    registry = ObservabilityOtelToolRegistry(
        inner=FakeToolExecutor(), tracer=tracer, call_counter=call_counter,
        error_counter=error_counter, latency_histogram=latency_histogram,
        error_logger=error_logger,
    )

    result = registry.execute("read_file", {"path": "a.py"})

    assert result.output == "done"
    assert registry.definitions() == [{"name": "fake_tool"}]
    spans = span_exporter.get_finished_spans()
    assert spans[0].name == "tool.call"
    assert spans[0].attributes["tool.name"] == "read_file"
    assert spans[0].status.status_code == StatusCode.UNSET
    assert len(log_exporter.get_finished_logs()) == 0


def test_tool_registry_marks_error_and_logs_on_tool_result_error_without_raising() -> None:
    (tracer, call_counter, error_counter, latency_histogram, error_logger,
     span_exporter, _metric_reader, log_exporter, _) = _wired()
    inner = FakeToolExecutor(result=ToolResult.error("file not found"))
    registry = ObservabilityOtelToolRegistry(
        inner=inner, tracer=tracer, call_counter=call_counter,
        error_counter=error_counter, latency_histogram=latency_histogram,
        error_logger=error_logger,
    )

    result = registry.execute("read_file", {"path": "missing.py"})

    assert result.is_error  # returned normally, not raised
    spans = span_exporter.get_finished_spans()
    assert spans[0].status.status_code == StatusCode.ERROR
    logs = log_exporter.get_finished_logs()
    assert len(logs) == 1
    assert "file not found" in str(logs[0].log_record.body)


def test_tool_registry_marks_error_and_reraises_on_unexpected_exception() -> None:
    (tracer, call_counter, error_counter, latency_histogram, error_logger,
     span_exporter, _metric_reader, log_exporter, _) = _wired()
    inner = FakeToolExecutor(raises=RuntimeError("boom"))
    registry = ObservabilityOtelToolRegistry(
        inner=inner, tracer=tracer, call_counter=call_counter,
        error_counter=error_counter, latency_histogram=latency_histogram,
        error_logger=error_logger,
    )

    try:
        registry.execute("bash", {"command": "explode"})
        assert False, "expected RuntimeError to propagate"
    except RuntimeError as error:
        assert str(error) == "boom"

    spans = span_exporter.get_finished_spans()
    assert spans[0].status.status_code == StatusCode.ERROR
    assert len(log_exporter.get_finished_logs()) == 1


def _metric_names(reader: InMemoryMetricReader) -> set[str]:
    data = reader.get_metrics_data()
    names: set[str] = set()
    if data is None:
        return names
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                names.add(metric.name)
    return names


# --- build() ----------------------------------------------------------------------


def _set_base_config_env(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "25")
    monkeypatch.setenv("AGENT_BASH_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("AGENT_SUMMARY_THRESHOLD_MESSAGES", "10")
    monkeypatch.setenv("AGENT_SUMMARY_KEEP_RECENT_MESSAGES", "4")
    monkeypatch.setenv("AGENT_LOOP_GUARD_NUDGE_AFTER", "2")
    monkeypatch.setenv("AGENT_LOOP_GUARD_HALT_AFTER", "4")
    monkeypatch.setenv("AGENT_CONTEXT_PRUNE_KEEP_RECENT_MESSAGES", "6")
    monkeypatch.setenv("AGENT_CONTEXT_PRUNE_MIN_CHARS_TO_PRUNE", "400")
    monkeypatch.setenv("AGENT_CONTEXT_WINDOW_SKILLS_ENABLED", "true")
    monkeypatch.setenv("AGENT_DEDUP_MIN_CHARS", "200")


def test_build_fails_fast_without_an_endpoint_configured(monkeypatch) -> None:
    _set_base_config_env(monkeypatch)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    try:
        observability_otel.build()
        assert False, "expected MissingOtelEndpointError"
    except MissingOtelEndpointError:
        pass


def test_build_returns_bundle_with_both_wrappers_and_sets_status(monkeypatch) -> None:
    _set_base_config_env(monkeypatch)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:1")

    bundle = observability_otel.build()

    assert bundle.wrap_llm_client is not None
    assert bundle.wrap_tool_registry is not None
    assert isinstance(bundle.wrap_llm_client(FakeClient()), ObservabilityOtelLLMClient)
    assert isinstance(
        bundle.wrap_tool_registry(FakeToolExecutor()), ObservabilityOtelToolRegistry
    )

    status = observability_otel.get_status()
    assert status is not None
    assert status.active is True
    assert status.endpoint == "http://localhost:1"


# --- ObservabilityOtelStatus ------------------------------------------------------


def test_status_is_local_and_grafana_url_for_localhost_endpoint() -> None:
    status = ObservabilityOtelStatus(endpoint="http://localhost:4318", active=True)
    assert status.is_local is True
    assert status.grafana_url == "http://localhost:3000"


def test_status_is_not_local_for_a_remote_endpoint() -> None:
    status = ObservabilityOtelStatus(
        endpoint="https://otlp-gateway-prod.grafana.net/otlp", active=True
    )
    assert status.is_local is False
    assert status.grafana_url is None


# --- Command --------------------------------------------------------------------


def test_command_reports_not_active_when_status_is_none() -> None:
    command = ObservabilityOtelCommand(status=None)
    assert "Not active" in command.run()


def test_command_reports_local_endpoint_and_grafana_url() -> None:
    status = ObservabilityOtelStatus(endpoint="http://localhost:4318", active=True)
    output = ObservabilityOtelCommand(status=status).run()
    assert "active" in output
    assert "http://localhost:4318" in output
    assert "http://localhost:3000" in output


def test_command_reports_cloud_endpoint_without_a_grafana_url() -> None:
    status = ObservabilityOtelStatus(endpoint="https://otlp-gateway.grafana.net/otlp", active=True)
    output = ObservabilityOtelCommand(status=status).run()
    assert "otlp-gateway.grafana.net" in output
    assert "Open your own Grafana Cloud stack" in output
