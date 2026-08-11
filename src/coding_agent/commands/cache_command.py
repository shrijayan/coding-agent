"""The /cache command: shows cache-friendly prompt metrics for this session.

Mirrors commands/usage_command.py and commands/metrics_command.py (same plain
`--- ... (this session) ---` style, no rich): it reads the shared
PromptCacheTracker the cache-friendly wrapper records into and reports how
cacheable the prompts it built were.

The one real token figure here - total input tokens - comes from the providers'
usage responses, same hard rule /usage and /metrics follow. Everything else
(stable-prefix size, reuse %, cache-friendly ratio) is a deterministic byte
measurement of the prompt we constructed, deliberately NOT a token estimate.
"""

from coding_agent.commands.base import SlashCommand
from coding_agent.optimizations.prompt_cache.metrics import PromptCacheTracker


class PromptCacheCommand(SlashCommand):
    """Prints per-session stable-prefix stability, reuse, and cache-friendly ratio."""

    def __init__(self, tracker: PromptCacheTracker) -> None:
        self._tracker = tracker

    @property
    def name(self) -> str:
        return "cache"

    @property
    def description(self) -> str:
        return (
            "Show cache-friendly prompt metrics: stable prefix, reuse, and "
            "cacheable ratio for this session."
        )

    def run(self) -> str:
        records = self._tracker.records
        if not records:
            return (
                "--- Prompt cache metrics (this session) ---\n"
                "No prompts built yet. Send a prompt first (and make sure you "
                "launched with --enable cache-friendly-prompts)."
            )

        latest = records[-1]
        distinct = self._tracker.distinct_stable_hashes()
        stability = (
            "unchanged across all sends"
            if distinct == 1
            else f"changed - {distinct} distinct prefixes seen"
        )

        lines = [
            "--- Prompt cache metrics (this session) ---",
            f"Total sends        : {self._tracker.total_sends}",
            f"Stable prefix hash : {latest.stable_hash[:12]} ({stability})",
            f"Stable prefix size : {latest.stable_bytes:,} bytes",
            f"Avg prefix reuse   : {_format_ratio(self._tracker.avg_reuse_pct())}",
            f"Avg cache-friendly : {_format_ratio(self._tracker.avg_cache_friendly_ratio())}",
            (
                "Latest prompt      : "
                f"stable {latest.stable_bytes:,}B \u00b7 "
                f"semi {latest.semi_stable_bytes:,}B \u00b7 "
                f"dynamic {latest.dynamic_bytes:,}B \u00b7 "
                f"total {latest.total_bytes:,}B"
            ),
            f"Real input tokens  : {self._tracker.total_input_tokens():,} (from provider usage)",
        ]
        return "\n".join(lines)


def _format_ratio(ratio: float | None) -> str:
    if ratio is None:
        return "n/a"
    return f"{ratio * 100:.1f}%"
