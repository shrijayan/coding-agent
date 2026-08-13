"""Lightweight observability: latency, tool-call visibility, and error
monitoring - zero setup, in-memory, this session only.

The other optimizations answer "how much did this cost" - this one answers
"how long did each call take, which tool calls failed, and where exactly?"
That's the gap between "the agent gave a wrong/slow answer" and "here's
exactly which LLM call or tool call was the problem."

This is the *lightweight* tier: no external dependency, no setup, works the
instant you pass --enable observability. For a heavier tier with real
traces/metrics/logs in an actual Grafana UI (local Docker or your own
Grafana Cloud account), see optimizations/observability_otel.py - the two
compose (neither owns history_policy), so both can be enabled together.

Two decorators, one shared tracker:
  - ObservabilityLLMClient wraps the LLMClient (wrap_llm_client) to time
    every model call and record LLMError failures.
  - ObservabilityToolRegistry wraps the ToolExecutor (wrap_tool_registry,
    tools/registry.py's Protocol) to time every tool call and record
    ToolResult.is_error failures - and any unexpected exception, since
    fail-fast (tools/base.py's rule) means "don't hide it", not "don't
    observe it" before it propagates.

Neither wrapper swallows an error: they record it, then re-raise/return
exactly what the inner call would have, so behavior is unchanged whether
or not this optimization is enabled - only what /observability can see
about a session changes.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Literal

from coding_agent.llm.base import LLMClient, LLMError, LLMResponse
from coding_agent.llm.messages import Message
from coding_agent.optimizations.bundle import OptimizationBundle
from coding_agent.tools.base import ToolResult
from coding_agent.tools.registry import ToolExecutor

Kind = Literal["llm", "tool"]


@dataclass(frozen=True)
class CallRecord:
    """One timed call, LLM or tool, success or failure."""

    kind: Kind
    name: str
    """The model string for an "llm" record, the tool name for a "tool"
    record. Empty for an "llm" record that failed before any model
    answered (LLMError - there's no model string to attribute it to)."""
    latency_ms: float
    success: bool
    error: str | None = None


@dataclass
class ObservabilityTracker:
    """Accumulates call records across a session, read by /observability."""

    records: list[CallRecord] = field(default_factory=list)
    slow_call_ms: float = 3000.0

    def record(self, call_record: CallRecord) -> None:
        self.records.append(call_record)

    @property
    def llm_records(self) -> list[CallRecord]:
        return [r for r in self.records if r.kind == "llm"]

    @property
    def tool_records(self) -> list[CallRecord]:
        return [r for r in self.records if r.kind == "tool"]

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.records if not r.success)

    @property
    def error_rate(self) -> float:
        return 0.0 if not self.records else self.error_count / len(self.records)

    @property
    def avg_latency_ms(self) -> float:
        return _avg(r.latency_ms for r in self.records)

    @property
    def max_latency_ms(self) -> float:
        return max((r.latency_ms for r in self.records), default=0.0)

    @property
    def slow_calls(self) -> list[CallRecord]:
        return [r for r in self.records if r.latency_ms >= self.slow_call_ms]

    @property
    def recent_errors(self) -> list[CallRecord]:
        """The last 5 failed calls - recent enough to still be relevant to
        whatever the user just watched happen, not a full error log."""
        return [r for r in self.records if not r.success][-5:]

    @property
    def by_tool(self) -> dict[str, "ToolStats"]:
        """Per-tool-name breakdown (tool calls only): count, average
        latency, and how many of that tool's calls failed."""
        grouped: dict[str, list[CallRecord]] = {}
        for record in self.tool_records:
            grouped.setdefault(record.name, []).append(record)
        return {
            name: ToolStats(
                count=len(records),
                avg_latency_ms=_avg(r.latency_ms for r in records),
                errors=sum(1 for r in records if not r.success),
            )
            for name, records in grouped.items()
        }


@dataclass(frozen=True)
class ToolStats:
    count: int
    avg_latency_ms: float
    errors: int


def _avg(values: Any) -> float:
    values = list(values)
    return 0.0 if not values else sum(values) / len(values)


class ObservabilityLLMClient(LLMClient):
    """Times every model call and records LLMError failures, without
    changing what's sent or swallowing the error."""

    def __init__(self, *, inner: LLMClient, tracker: ObservabilityTracker) -> None:
        self._inner = inner
        self._tracker = tracker

    def send(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        start = time.perf_counter()
        try:
            response = self._inner.send(system=system, messages=messages, tools=tools)
        except LLMError as error:
            self._tracker.record(
                CallRecord(
                    kind="llm",
                    name="",
                    latency_ms=_elapsed_ms(start),
                    success=False,
                    error=str(error),
                )
            )
            raise
        self._tracker.record(
            CallRecord(
                kind="llm",
                name=response.model,
                latency_ms=_elapsed_ms(start),
                success=True,
            )
        )
        return response


class ObservabilityToolRegistry:
    """Implements ToolExecutor: times and records every tool call the inner
    executor runs, without changing what the model sees."""

    def __init__(self, *, inner: ToolExecutor, tracker: ObservabilityTracker) -> None:
        self._inner = inner
        self._tracker = tracker

    def definitions(self) -> list[dict[str, Any]]:
        return self._inner.definitions()

    def execute(self, name: str, tool_input: dict[str, Any]) -> ToolResult:
        start = time.perf_counter()
        try:
            result = self._inner.execute(name, tool_input)
        except Exception as error:
            self._tracker.record(
                CallRecord(
                    kind="tool",
                    name=name,
                    latency_ms=_elapsed_ms(start),
                    success=False,
                    error=str(error),
                )
            )
            raise
        self._tracker.record(
            CallRecord(
                kind="tool",
                name=name,
                latency_ms=_elapsed_ms(start),
                success=not result.is_error,
                error=result.output if result.is_error else None,
            )
        )
        return result


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0


_last_tracker: ObservabilityTracker | None = None


def get_tracker() -> ObservabilityTracker:
    """Return the tracker from the most recent build() (creating one if the
    optimization hasn't been built yet, so callers never get None)."""
    global _last_tracker
    if _last_tracker is None:
        _last_tracker = ObservabilityTracker()
    return _last_tracker


def build() -> OptimizationBundle:
    global _last_tracker
    tracker = ObservabilityTracker()
    _last_tracker = tracker

    def wrap_llm_client(inner: LLMClient) -> LLMClient:
        return ObservabilityLLMClient(inner=inner, tracker=tracker)

    def wrap_tool_registry(inner: ToolExecutor) -> ToolExecutor:
        return ObservabilityToolRegistry(inner=inner, tracker=tracker)

    return OptimizationBundle(
        wrap_llm_client=wrap_llm_client, wrap_tool_registry=wrap_tool_registry
    )
