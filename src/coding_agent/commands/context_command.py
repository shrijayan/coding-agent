"""The /context command: shows context-window optimization metrics.

Mirrors commands/cache_command.py's shape: reads the shared
ContextWindowTracker that both halves of the optimization (pruning and
on-demand skill loading) record into. Chars-pruned is a deterministic fact
about the text that was dropped, never a token estimate.
"""

from coding_agent.commands.base import SlashCommand
from coding_agent.optimizations.context_window import ContextWindowTracker


class ContextWindowCommand(SlashCommand):
    """Prints per-session prune/skill-load counts for context-window."""

    def __init__(self, tracker: ContextWindowTracker) -> None:
        self._tracker = tracker

    @property
    def name(self) -> str:
        return "context"

    @property
    def description(self) -> str:
        return (
            "Show context-window optimization metrics: stale tool output "
            "pruned and skills loaded on demand this session."
        )

    def run(self) -> str:
        if not self._tracker.events:
            return (
                "--- Context window metrics (this session) ---\n"
                "No activity yet. Send a prompt first (and make sure you "
                "launched with --enable context-window)."
            )

        skills_loaded = self._tracker.skills_loaded
        lines = [
            "--- Context window metrics (this session) ---",
            f"Outputs pruned   : {self._tracker.total_prunes}",
            f"Chars removed    : {self._tracker.total_chars_pruned:,}",
            f"Skills loaded    : {', '.join(skills_loaded) or 'none'}",
        ]
        return "\n".join(lines)
