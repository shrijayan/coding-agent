"""The /usage command: shows token usage and estimated cost for this session."""

from coding_agent.commands.base import SlashCommand
from coding_agent.config import Config
from coding_agent.metrics.pricing import PricingTable
from coding_agent.metrics.usage import UsageTracker


class UsageCommand(SlashCommand):
    """Prints token counts, call counts, and estimated cost so far."""

    def __init__(
        self,
        tracker: UsageTracker,
        pricing: PricingTable,
        config: Config,
        enabled_optimizations: list[str],
    ) -> None:
        self._tracker = tracker
        self._pricing = pricing
        self._config = config
        self._enabled_optimizations = enabled_optimizations

    @property
    def name(self) -> str:
        return "usage"

    @property
    def description(self) -> str:
        return "Show token usage and estimated cost for this session."

    def run(self) -> str:
        cost = self._pricing.cost_for(self._tracker.total, self._config.model)
        optimizations = ", ".join(self._enabled_optimizations) or "none enabled"

        return (
            "--- Usage (this session) ---\n"
            f"Provider/model : {self._config.provider} / {self._config.model}\n"
            f"User messages  : {self._tracker.user_messages}\n"
            f"LLM calls      : {self._tracker.llm_calls}\n"
            f"Tool calls     : {self._tracker.tool_calls}\n"
            f"Input tokens   : {self._tracker.total.input_tokens:,}\n"
            f"Output tokens  : {self._tracker.total.output_tokens:,}\n"
            f"Total tokens   : {self._tracker.total.total_tokens:,}\n"
            f"Estimated cost : ${cost:.4f}\n"
            f"Optimizations  : {optimizations}"
        )
