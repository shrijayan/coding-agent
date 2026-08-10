"""The /usage command: shows token usage and estimated cost for this session."""

from typing import Any

from coding_agent.commands.base import SlashCommand
from coding_agent.config import Config
from coding_agent.metrics.pricing import PricingTable
from coding_agent.metrics.usage import Usage, UsageTracker


class UsageCommand(SlashCommand):
    """Prints token counts, call counts, and estimated cost so far.

    Cost is computed per model actually used (UsageTracker.by_model),
    not from the configured model alone - with hybrid routing enabled a
    session can span several models with very different prices, and
    pricing everything at the configured model's rate would misstate
    the very number every optimization is judged by.
    """

    def __init__(
        self,
        tracker: UsageTracker,
        pricing: PricingTable,
        config: Config,
        enabled_optimizations: list[str],
        configured_models: list[str] | None = None,
        model_metadata: dict[str, dict[str, Any]] | None = None,
        cost_cap_usd: float | None = None,
    ) -> None:
        self._tracker = tracker
        self._pricing = pricing
        self._config = config
        self._enabled_optimizations = enabled_optimizations
        self._configured_models = configured_models
        self._model_metadata = model_metadata or {}
        self._cost_cap_usd = cost_cap_usd

    @property
    def name(self) -> str:
        return "usage"

    @property
    def description(self) -> str:
        return "Show token usage and estimated cost for this session."

    def run(self) -> str:
        by_model = self._by_model()
        total_cost = sum(
            self._pricing.cost_for(usage, model) for model, usage in by_model.items()
        )
        models_used = ", ".join(by_model) or "none yet"
        optimizations = ", ".join(self._enabled_optimizations) or "none enabled"

        lines = [
            "--- Usage (this session) ---",
            f"Configured     : {self._configured_label()}",
            f"Models used    : {models_used}",
            f"User messages  : {self._tracker.user_messages}",
            f"LLM calls      : {self._tracker.llm_calls}",
            f"Tool calls     : {self._tracker.tool_calls}",
            f"Input tokens   : {self._tracker.total.input_tokens:,}",
            f"Output tokens  : {self._tracker.total.output_tokens:,}",
            f"Total tokens   : {self._tracker.total.total_tokens:,}",
            *self._per_model_lines(by_model),
            f"Estimated cost : {self._cost_label(total_cost)}",
            f"Optimizations  : {optimizations}",
        ]
        return "\n".join(lines)

    def _configured_label(self) -> str:
        """Single configured model normally; the whole ladder (cheapest
        first) when a routing optimization made more models reachable."""
        if self._configured_models:
            return " -> ".join(self._configured_models) + " (routing ladder)"
        return f"{self._config.provider} / {self._config.model}"

    def _cost_label(self, total_cost: float) -> str:
        if self._cost_cap_usd is None:
            return f"${total_cost:.4f}"
        return f"${total_cost:.4f} / ${self._cost_cap_usd:.2f} cap"

    def _by_model(self) -> dict[str, Usage]:
        """Per-model usage, with the defensive ""-bucket (a client that
        didn't report its model) attributed to the configured model."""
        by_model: dict[str, Usage] = {}
        for model, usage in self._tracker.by_model.items():
            key = model or self._config.model
            by_model[key] = by_model.get(key, Usage()) + usage
        return by_model

    def _per_model_lines(self, by_model: dict[str, Usage]) -> list[str]:
        if len(by_model) < 2:
            return []
        width = max(len(model) for model in by_model)
        lines = ["Per model:"]
        for model, usage in by_model.items():
            calls = self._calls_for(model)
            cost = self._pricing.cost_for(usage, model)
            lines.append(
                f"  {model:<{width}} : {calls} call{'s' if calls != 1 else ''}, "
                f"{usage.total_tokens:,} tokens, ${cost:.4f}"
            )
            note = self._metadata_note(model)
            if note:
                lines.append(f"  {'':<{width}}   {note}")
        return lines

    def _metadata_note(self, model: str) -> str:
        """A short capability hint for a model, from the models.yaml
        catalog - context for why routing sent work to this tier."""
        meta = self._model_metadata.get(model)
        if not meta:
            return ""
        strengths = meta.get("strengths")
        if isinstance(strengths, list) and strengths:
            return "strengths: " + ", ".join(str(s) for s in strengths)
        description = meta.get("description")
        return str(description).strip() if description else ""

    def _calls_for(self, model: str) -> int:
        calls = self._tracker.calls_by_model.get(model, 0)
        if model == self._config.model:
            # Fold in calls whose client didn't report a model (see _by_model).
            calls += self._tracker.calls_by_model.get("", 0)
        return calls
