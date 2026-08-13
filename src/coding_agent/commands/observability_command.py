"""The /observability command: shows latency, tool-call, and error
monitoring for this session (the lightweight, zero-setup tier - see
optimizations/observability.py).

Mirrors commands/loop_guard_command.py's shape: reads the shared
ObservabilityTracker that both wrappers (LLM calls and tool calls) record
into. The point of this report is the debugging payoff other reports
don't give - which specific call was slow, and which specific call
failed and why - not just an aggregate cost/token number.
"""

from coding_agent.commands.base import SlashCommand
from coding_agent.optimizations.observability import ObservabilityTracker

_ERROR_PREVIEW_CHARS = 100


class ObservabilityCommand(SlashCommand):
    """Prints per-session latency/error/tool-call metrics for observability."""

    def __init__(self, tracker: ObservabilityTracker) -> None:
        self._tracker = tracker

    @property
    def name(self) -> str:
        return "observability"

    @property
    def description(self) -> str:
        return (
            "Show latency, tool-call, and error monitoring: call counts, "
            "slow calls, and recent failures this session."
        )

    def run(self) -> str:
        tracker = self._tracker
        if not tracker.records:
            return (
                "--- Observability (this session) ---\n"
                "No calls yet. Send a prompt first (and make sure you "
                "launched with --enable observability)."
            )

        llm_records = tracker.llm_records
        tool_records = tracker.tool_records
        lines = [
            "--- Observability (this session) ---",
            f"LLM calls        : {len(llm_records)}",
            f"Tool calls       : {len(tool_records)}",
            f"Errors           : {tracker.error_count} ({tracker.error_rate * 100:.0f}%)",
            f"Avg latency      : {tracker.avg_latency_ms:.0f}ms",
            f"Max latency      : {tracker.max_latency_ms:.0f}ms",
        ]

        by_tool = tracker.by_tool
        if by_tool:
            lines.append("Per-tool breakdown:")
            for tool_name, stats in sorted(by_tool.items()):
                lines.append(
                    f"  {tool_name:<20} {stats.count} calls · "
                    f"avg {stats.avg_latency_ms:.0f}ms · {stats.errors} errors"
                )

        slow_calls = tracker.slow_calls
        if slow_calls:
            lines.append(f"Slow calls (≥{tracker.slow_call_ms:.0f}ms):")
            for record in slow_calls:
                label = record.name or "(no model - call failed)"
                lines.append(f"  [{record.kind}] {label} · {record.latency_ms:.0f}ms")

        recent_errors = tracker.recent_errors
        if recent_errors:
            lines.append("Recent errors:")
            for record in recent_errors:
                label = record.name or "(no model - call failed)"
                message = (record.error or "")[:_ERROR_PREVIEW_CHARS]
                lines.append(f"  [{record.kind}] {label}: {message}")

        return "\n".join(lines)
