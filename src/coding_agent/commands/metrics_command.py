"""The /metrics command: shows hybrid-routing decisions for this session.

Mirrors commands/usage_command.py (and prints in the same
`--- ... (this session) ---` plain-text style, no rich): it reads the
shared RoutingTracker the routing wrapper records into and reports the
numbers the survey says actually matter for a routing layer - not just
accuracy, but escalation rate, latency by tier, cost, and how often the
cheap tier's output passed the quality gate.

Cost is derived here from each record's real token counts times the
models.yaml catalog (never a stored estimate - same hard rule /usage
follows), so cheap-tier sends show $0.00 (local, priced at $0) and
escalations show the powerful tier's real cost.
"""

from coding_agent.commands.base import SlashCommand
from coding_agent.metrics.pricing import PricingTable
from coding_agent.optimizations.routing.metrics import RoutingTracker


class RoutingMetricsCommand(SlashCommand):
    """Prints per-session routing paths, escalation rate, latency, and cost."""

    def __init__(self, tracker: RoutingTracker, pricing: PricingTable) -> None:
        self._tracker = tracker
        self._pricing = pricing

    @property
    def name(self) -> str:
        return "metrics"

    @property
    def description(self) -> str:
        return "Show hybrid-routing decisions, escalation rate, and cost for this session."

    def run(self) -> str:
        records = self._tracker.records
        if not records:
            return (
                "--- Routing metrics (this session) ---\n"
                "No routed model calls yet. Send a prompt first "
                "(and make sure you launched with --enable hybrid-routing)."
            )

        counts = self._tracker.counts_by_path()
        latency = self._tracker.avg_latency_ms_by_path()
        total_cost = sum(
            self._pricing.cost_for(record.usage, record.model) for record in records
        )
        pass_rate = self._tracker.gate_pass_rate()

        lines = [
            "--- Routing metrics (this session) ---",
            f"Total routed calls : {self._tracker.total_sends}",
            f"  direct_powerful  : {counts.get('direct_powerful', 0)}",
            f"  cheap            : {counts.get('cheap', 0)}",
            f"  cheap_escalated  : {counts.get('cheap_escalated', 0)}",
            (
                f"Escalation rate    : {self._tracker.escalation_rate() * 100:.1f}% "
                "(of cheap-tier attempts)"
            ),
            f"Quality-gate pass  : {_format_rate(pass_rate)}",
        ]

        tier_counts = self._tracker.counts_by_tier()
        if tier_counts:
            lines.append("Answered by tier:")
            lines.extend(
                f"  {tier:<16} : {count}" for tier, count in tier_counts.items()
            )

        lines.append("Avg latency by path:")
        for path in ("direct_powerful", "cheap", "cheap_escalated"):
            if path in latency:
                lines.append(f"  {path:<16} : {latency[path]:.0f}ms")

        lines.append(f"Total routed cost  : ${total_cost:.4f}")
        lines.append(
            f"Avg cost per call  : ${total_cost / self._tracker.total_sends:.4f}"
        )
        return "\n".join(lines)


def _format_rate(rate: float | None) -> str:
    if rate is None:
        return "n/a (gate did not run)"
    return f"{rate * 100:.1f}%"
