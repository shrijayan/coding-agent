"""A soft per-session spend cap.

Protects a shared, fixed token budget (e.g. a workshop's $100 across many
participants): once a session's estimated cost crosses the cap, the agent
stops making further LLM calls instead of quietly running the budget
down. It's a *soft* cap - checked before each model call - so a session
can overshoot by at most the one call already in flight, which for
cent-scale calls against a dollar-scale cap is negligible.

Cost is summed per model from the same real token counts /usage reports
(never estimated - see LLMResponse.usage), so the number the cap enforces
is the number the user sees.
"""

from coding_agent.metrics.pricing import PricingTable
from coding_agent.metrics.usage import UsageTracker


class CostGuard:
    """Decides when a session has spent enough to stop."""

    def __init__(self, pricing: PricingTable, cap_usd: float) -> None:
        self._pricing = pricing
        self._cap_usd = cap_usd

    def session_cost(self, tracker: UsageTracker) -> float:
        return sum(
            self._pricing.cost_for(usage, model)
            for model, usage in tracker.by_model.items()
        )

    def exceeded(self, tracker: UsageTracker) -> bool:
        return self.session_cost(tracker) >= self._cap_usd

    def notice(self, tracker: UsageTracker) -> str:
        return (
            f"[stopped: session cost cap of ${self._cap_usd:.2f} reached "
            f"(estimated ${self.session_cost(tracker):.4f} spent). Start a new "
            "session to continue, or raise AGENT_SESSION_COST_CAP_USD / the cap "
            "in models.yaml.]"
        )
