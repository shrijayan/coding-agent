"""In-memory routing metrics, mirroring metrics/usage.py's UsageTracker.

The repo tracks token usage per session in memory and surfaces it via
/usage; this is the same shape for routing decisions, surfaced via
/metrics. One RoutingRecord is appended per LLMClient.send() (NOT per
user turn - a turn can span many sends across the tool loop, see
implementation note 2), capturing which tier handled it and why.

Cost is deliberately NOT stored here as a number: per the project's hard
rule, cost is always derived from the real token counts in `usage` times
the models.yaml catalog at read time (RoutingMetricsCommand does this), so
there is never a second, estimated cost path to drift from /usage.

This is intentionally in-memory only (no SQLite): metrics are per-session
just like UsageTracker, and cross-session persistence isn't needed for
the workshop's before/after comparison.
"""

from dataclasses import dataclass, field

from coding_agent.metrics.usage import Usage

# The three paths a send() can take through the router.
PATH_DIRECT_POWERFUL = "direct_powerful"
PATH_CHEAP = "cheap"
PATH_CHEAP_ESCALATED = "cheap_escalated"


@dataclass(frozen=True)
class RoutingRecord:
    """Everything worth knowing about one routed send()."""

    path: str
    difficulty: float
    model: str
    latency_ms: float
    usage: Usage
    tier: str = ""
    """Name of the ladder rung that actually answered (see models.yaml).
    With more than two tiers, `path` alone no longer identifies the model,
    so this is what /metrics groups by."""
    hops: int = 0
    """How many rungs it had to climb before the gate passed. 0 means the
    first tier tried succeeded."""
    gate_passed: bool | None = None
    """None when the gate didn't run (gate disabled)."""
    gate_failed_checks: list[str] = field(default_factory=list)


@dataclass
class RoutingTracker:
    """Accumulates routing records across a session.

    One instance is shared (constructor injection) between the routing
    wrapper that records into it and the /metrics command that reads it -
    exactly how UsageTracker is shared with /usage.
    """

    records: list[RoutingRecord] = field(default_factory=list)

    def record(self, record: RoutingRecord) -> None:
        self.records.append(record)

    @property
    def total_sends(self) -> int:
        return len(self.records)

    @property
    def escalations(self) -> int:
        return sum(1 for r in self.records if r.path == PATH_CHEAP_ESCALATED)

    def escalation_rate(self) -> float:
        """Fraction of cheap-tier attempts that ended up escalating.

        Denominator is cheap attempts (cheap + cheap_escalated), not all
        sends - a direct_powerful send never had a chance to escalate, so
        counting it would understate how often the cheap tier fell short.
        """
        cheap_attempts = sum(
            1 for r in self.records if r.path in (PATH_CHEAP, PATH_CHEAP_ESCALATED)
        )
        if cheap_attempts == 0:
            return 0.0
        return self.escalations / cheap_attempts

    def avg_latency_ms_by_path(self) -> dict[str, float]:
        sums: dict[str, float] = {}
        counts: dict[str, int] = {}
        for record in self.records:
            sums[record.path] = sums.get(record.path, 0.0) + record.latency_ms
            counts[record.path] = counts.get(record.path, 0) + 1
        return {path: sums[path] / counts[path] for path in sums}

    def gate_pass_rate(self) -> float | None:
        """Pass rate among sends where the gate actually ran.

        Semantics: "of the sends where the gate ran, how often did the tier
        the pre-router chose produce acceptable output?" It counts the
        *first* tier attempted on each send (see RoutingLLMClient._climb),
        including sends routed straight to the top tier - so it measures
        the quality of the routing decision, not just of the cheap model.
        Use escalation_rate() for the narrower "how often was the cheap
        tier not enough" question.

        None when the gate never ran (e.g. gate disabled) - reported as
        'n/a' rather than a misleading 0%.
        """
        ran = [r for r in self.records if r.gate_passed is not None]
        if not ran:
            return None
        passed = sum(1 for r in ran if r.gate_passed)
        return passed / len(ran)

    def counts_by_tier(self) -> dict[str, int]:
        """How many sends each ladder rung ultimately answered.

        With an N-tier ladder this is the more informative breakdown than
        the three path names - it shows exactly where the work landed.
        """
        counts: dict[str, int] = {}
        for record in self.records:
            key = record.tier or record.model
            counts[key] = counts.get(key, 0) + 1
        return counts

    def counts_by_path(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.records:
            counts[record.path] = counts.get(record.path, 0) + 1
        return counts
