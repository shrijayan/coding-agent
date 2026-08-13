"""The /compression command: shows prompt-compression metrics for this session.

Mirrors commands/cache_command.py's shape: it reads the shared
CompressionTracker the wrapper records into and reports how much smaller the
system prompt and tool descriptions were on the wire. All figures here are
deterministic character counts of text we swapped ourselves - the real token
effect shows up in /usage's provider-reported input tokens, never estimated.
"""

from coding_agent.commands.base import SlashCommand
from coding_agent.optimizations.prompt_compression import CompressionTracker


class CompressionCommand(SlashCommand):
    """Prints per-session before/after prompt sizes for prompt-compression."""

    def __init__(self, tracker: CompressionTracker) -> None:
        self._tracker = tracker

    @property
    def name(self) -> str:
        return "compression"

    @property
    def description(self) -> str:
        return (
            "Show prompt-compression metrics: system prompt and tool "
            "description sizes before/after, per send and session total."
        )

    def run(self) -> str:
        records = self._tracker.records
        if not records:
            return (
                "--- Prompt compression metrics (this session) ---\n"
                "No sends yet. Send a prompt first (and make sure you "
                "launched with --enable prompt-compression)."
            )

        latest = records[-1]
        lines = [
            "--- Prompt compression metrics (this session) ---",
            f"Total sends        : {self._tracker.total_sends}",
            (
                "System prompt      : "
                f"{latest.system_chars_before:,} -> {latest.system_chars_after:,} chars"
            ),
            (
                "Tool descriptions  : "
                f"{latest.tool_chars_before:,} -> {latest.tool_chars_after:,} chars"
            ),
            (
                "Chars saved        : "
                f"{latest.chars_saved:,} per send \u00b7 "
                f"{self._tracker.total_chars_saved:,} across all sends"
            ),
            "Token effect       : see /usage (real provider counts, never estimated)",
        ]
        return "\n".join(lines)
