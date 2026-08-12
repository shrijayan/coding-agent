"""The /loopguard command: shows agent-loop-prevention metrics for this session.

Mirrors commands/cache_command.py's shape: it reads the shared
LoopGuardTracker the wrapper records into and reports how often the guard
saw a repeated failing call, nudged, or halted. No token/cost "savings"
figure - a halt genuinely skips a call, but guessing what that call would
have cost is an estimate, and this project never shows one of those.
"""

from coding_agent.commands.base import SlashCommand
from coding_agent.optimizations.loop_guard import LoopGuardTracker


class LoopGuardCommand(SlashCommand):
    """Prints per-session repeat/nudge/halt counts for loop-guard."""

    def __init__(self, tracker: LoopGuardTracker) -> None:
        self._tracker = tracker

    @property
    def name(self) -> str:
        return "loopguard"

    @property
    def description(self) -> str:
        return (
            "Show agent-loop-prevention metrics: repeated failing calls "
            "seen, nudges issued, halts triggered this session."
        )

    def run(self) -> str:
        if not self._tracker.records:
            return (
                "--- Loop guard metrics (this session) ---\n"
                "No sends yet. Send a prompt first (and make sure you "
                "launched with --enable loop-guard)."
            )

        lines = [
            "--- Loop guard metrics (this session) ---",
            f"Total sends      : {self._tracker.total_sends}",
            f"Nudges issued    : {self._tracker.total_nudges}",
            f"Halts triggered  : {self._tracker.total_halts}",
            f"Current streak   : {self._tracker.current_streak}",
        ]
        return "\n".join(lines)
