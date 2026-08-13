"""The /dedup command: shows deduplication metrics for this session.

Mirrors commands/cache_command.py's shape: it reads the shared DedupTracker
the wrapper records into and reports how many exact-duplicate blocks were
replaced with markers, and their total size. All figures are deterministic
character counts of text we replaced ourselves - the real token effect
shows up in /usage's provider-reported input tokens, never estimated.
"""

from coding_agent.commands.base import SlashCommand
from coding_agent.optimizations.deduplication import DedupTracker


class DedupCommand(SlashCommand):
    """Prints per-session duplicate-replacement counts for deduplication."""

    def __init__(self, tracker: DedupTracker) -> None:
        self._tracker = tracker

    @property
    def name(self) -> str:
        return "dedup"

    @property
    def description(self) -> str:
        return (
            "Show deduplication metrics: exact-duplicate blocks replaced "
            "with markers this session, and the size removed."
        )

    def run(self) -> str:
        if self._tracker.total_sends == 0:
            return (
                "--- Deduplication metrics (this session) ---\n"
                "No sends yet. Send a prompt first (and make sure you "
                "launched with --enable deduplication)."
            )

        by_kind: dict[str, int] = {}
        for record in self._tracker.records:
            by_kind[record.kind] = by_kind.get(record.kind, 0) + 1
        kinds = (
            ", ".join(f"{kind} x{count}" for kind, count in sorted(by_kind.items()))
            or "none"
        )

        lines = [
            "--- Deduplication metrics (this session) ---",
            f"Total sends        : {self._tracker.total_sends}",
            f"Duplicates replaced: {self._tracker.total_duplicates}",
            f"By kind            : {kinds}",
            (
                "Chars removed      : "
                f"{self._tracker.total_chars_removed:,} (deterministic count, "
                "token effect in /usage)"
            ),
        ]
        return "\n".join(lines)
