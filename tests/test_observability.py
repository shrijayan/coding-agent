"""Tests for the lightweight observability tier (observability.py).

Mirrors tests/test_loop_guard.py's style: local fakes for LLMClient and
ToolExecutor, no subprocess, no HTTP, no real API calls.
"""

from typing import Any

from coding_agent.commands.observability_command import ObservabilityCommand
from coding_agent.llm.base import LLMClient, LLMError, LLMResponse
from coding_agent.llm.messages import Message
from coding_agent.metrics.usage import Usage
from coding_agent.optimizations import observability
from coding_agent.optimizations.observability import (
    CallRecord,
    ObservabilityLLMClient,
    ObservabilityToolRegistry,
    ObservabilityTracker,
)
from coding_agent.tools.base import ToolResult


class FakeClient(LLMClient):
    """Returns a canned response, or raises LLMError if told to."""

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
            usage=Usage(input_tokens=10, output_tokens=5), model=self._model,
        )


class FakeToolExecutor:
    """Implements ToolExecutor: returns a canned ToolResult, or raises if told to."""

    def __init__(
        self, *, result: ToolResult | None = None, raises: Exception | None = None
    ) -> None:
        self._result = result or ToolResult.ok("done")
        self._raises = raises
        self.calls: list[tuple[str, dict]] = []

    def definitions(self) -> list[dict[str, Any]]:
        return [{"name": "fake_tool"}]

    def execute(self, name: str, tool_input: dict[str, Any]) -> ToolResult:
        self.calls.append((name, tool_input))
        if self._raises is not None:
            raise self._raises
        return self._result


# --- ObservabilityLLMClient ---------------------------------------------------


def test_llm_client_records_latency_and_success_on_normal_response() -> None:
    tracker = ObservabilityTracker()
    client = ObservabilityLLMClient(inner=FakeClient(model="my-model"), tracker=tracker)

    response = client.send(system="s", messages=[], tools=[])

    assert response.text == "ok"
    assert len(tracker.records) == 1
    record = tracker.records[0]
    assert record.kind == "llm"
    assert record.name == "my-model"
    assert record.success is True
    assert record.error is None
    assert record.latency_ms >= 0


def test_llm_client_records_and_reraises_on_llm_error() -> None:
    tracker = ObservabilityTracker()
    client = ObservabilityLLMClient(
        inner=FakeClient(error=LLMError("rate limited")), tracker=tracker
    )

    try:
        client.send(system="s", messages=[], tools=[])
        assert False, "expected LLMError to propagate"
    except LLMError as error:
        assert str(error) == "rate limited"

    assert len(tracker.records) == 1
    record = tracker.records[0]
    assert record.kind == "llm"
    assert record.success is False
    assert record.error == "rate limited"


# --- ObservabilityToolRegistry -------------------------------------------------


def test_tool_registry_records_success_from_tool_result() -> None:
    tracker = ObservabilityTracker()
    registry = ObservabilityToolRegistry(inner=FakeToolExecutor(), tracker=tracker)

    result = registry.execute("read_file", {"path": "a.py"})

    assert result.output == "done"
    assert registry.definitions() == [{"name": "fake_tool"}]
    assert len(tracker.records) == 1
    record = tracker.records[0]
    assert record.kind == "tool"
    assert record.name == "read_file"
    assert record.success is True


def test_tool_registry_records_failure_from_tool_result_error() -> None:
    tracker = ObservabilityTracker()
    inner = FakeToolExecutor(result=ToolResult.error("file not found"))
    registry = ObservabilityToolRegistry(inner=inner, tracker=tracker)

    result = registry.execute("read_file", {"path": "missing.py"})

    assert result.is_error
    record = tracker.records[0]
    assert record.success is False
    assert record.error == "file not found"


def test_tool_registry_records_and_reraises_on_unexpected_exception() -> None:
    tracker = ObservabilityTracker()
    inner = FakeToolExecutor(raises=RuntimeError("boom"))
    registry = ObservabilityToolRegistry(inner=inner, tracker=tracker)

    try:
        registry.execute("bash", {"command": "explode"})
        assert False, "expected RuntimeError to propagate"
    except RuntimeError as error:
        assert str(error) == "boom"

    record = tracker.records[0]
    assert record.kind == "tool"
    assert record.name == "bash"
    assert record.success is False
    assert record.error == "boom"


# --- ObservabilityTracker derived properties -----------------------------------


def test_tracker_derived_properties() -> None:
    tracker = ObservabilityTracker(slow_call_ms=100.0)
    tracker.record(CallRecord(kind="llm", name="m1", latency_ms=50.0, success=True))
    tracker.record(CallRecord(kind="tool", name="read_file", latency_ms=150.0, success=True))
    tracker.record(
        CallRecord(kind="tool", name="read_file", latency_ms=10.0, success=False, error="nope")
    )

    assert len(tracker.llm_records) == 1
    assert len(tracker.tool_records) == 2
    assert tracker.error_count == 1
    assert tracker.error_rate == 1 / 3
    assert tracker.avg_latency_ms == (50.0 + 150.0 + 10.0) / 3
    assert tracker.max_latency_ms == 150.0
    assert [r.latency_ms for r in tracker.slow_calls] == [150.0]
    assert len(tracker.recent_errors) == 1

    stats = tracker.by_tool["read_file"]
    assert stats.count == 2
    assert stats.errors == 1
    assert stats.avg_latency_ms == (150.0 + 10.0) / 2


def test_tracker_with_no_records_has_zeroed_properties() -> None:
    tracker = ObservabilityTracker()
    assert tracker.error_rate == 0.0
    assert tracker.avg_latency_ms == 0.0
    assert tracker.max_latency_ms == 0.0
    assert tracker.slow_calls == []
    assert tracker.by_tool == {}


# --- build() -------------------------------------------------------------------


def test_build_returns_bundle_with_both_wrappers() -> None:
    bundle = observability.build()

    assert bundle.wrap_llm_client is not None
    assert bundle.wrap_tool_registry is not None

    wrapped_client = bundle.wrap_llm_client(FakeClient())
    assert isinstance(wrapped_client, ObservabilityLLMClient)
    wrapped_client.send(system="s", messages=[], tools=[])

    wrapped_tools = bundle.wrap_tool_registry(FakeToolExecutor())
    assert isinstance(wrapped_tools, ObservabilityToolRegistry)
    wrapped_tools.execute("read_file", {})

    tracker = observability.get_tracker()
    assert len(tracker.records) == 2


# --- Command --------------------------------------------------------------------


def test_command_handles_empty_and_populated() -> None:
    tracker = ObservabilityTracker()
    command = ObservabilityCommand(tracker=tracker)
    assert "No calls yet" in command.run()

    tracker.record(CallRecord(kind="llm", name="m1", latency_ms=50.0, success=True))
    tracker.record(
        CallRecord(kind="tool", name="bash", latency_ms=10.0, success=False, error="boom")
    )

    output = command.run()
    assert "Observability" in output
    assert "Errors           : 1 (50%)" in output
    assert "bash: boom" in output
