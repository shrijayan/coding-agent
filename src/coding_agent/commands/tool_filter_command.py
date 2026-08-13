"""The /toolfilter command: shows tool-filtering metrics for this session.

Mirrors commands/cache_command.py's shape: it reads the shared
ToolFilterTracker the wrapper records into and reports how many tool
definitions were withheld per send, and which ones. No "tokens saved"
figure - a withheld definition genuinely shrinks the prompt, but guessing
its token size would be an estimate, and this project never shows one of
those. The real effect shows up in /usage's input tokens instead.
"""

from coding_agent.commands.base import SlashCommand
from coding_agent.optimizations.tool_filtering import ToolFilterTracker


class ToolFilterCommand(SlashCommand):
    """Prints per-session exposed/filtered tool counts for tool-filtering."""

    def __init__(self, tracker: ToolFilterTracker) -> None:
        self._tracker = tracker

    @property
    def name(self) -> str:
        return "toolfilter"

    @property
    def description(self) -> str:
        return (
            "Show tool-filtering metrics: how many tool definitions were "
            "withheld from sends this session, and which ones."
        )

    def run(self) -> str:
        records = self._tracker.records
        if not records:
            return (
                "--- Tool filter metrics (this session) ---\n"
                "No sends yet. Send a prompt first (and make sure you "
                "launched with --enable tool-filtering)."
            )

        latest = records[-1]
        sends_filtered = sum(1 for r in records if r.filtered_names)
        lines = [
            "--- Tool filter metrics (this session) ---",
            f"Total sends        : {self._tracker.total_sends}",
            f"Sends filtered     : {sends_filtered}",
            f"Definitions withheld: {self._tracker.total_filtered} (across all sends)",
            (
                "Latest send        : "
                f"{latest.tools_exposed} of {latest.tools_offered} tools exposed"
            ),
        ]
        counts = self._tracker.filtered_name_counts()
        if counts:
            breakdown = ", ".join(
                f"{name} x{count}" for name, count in sorted(counts.items())
            )
            lines.append(f"Withheld by name   : {breakdown}")
        return "\n".join(lines)
