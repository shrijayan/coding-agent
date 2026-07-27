"""Cost calculation from token usage, using a hand-maintained pricing table.

Model pricing lives in pricing.json (plain data, not Python constants) so
adding a new model is a one-line edit, not a code change - same
philosophy as .env for settings that vary and change over time. We
deliberately do NOT try to fetch live prices from providers: for a
workshop with a small, known set of models, a hand-maintained file is
far simpler than building and trusting a live-pricing integration.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from coding_agent.metrics.usage import Usage

_PRICING_FILE = Path(__file__).parent / "pricing.json"


class MissingPricingError(RuntimeError):
    """Raised when a model has no entry in pricing.json.

    Raised at agent startup (see cli.py), not lazily when /usage is
    first checked - the same "fail fast, no silent wrong numbers"
    philosophy as Config. A cost dashboard that might quietly show
    $0.00 for an unpriced model is worse than one that refuses to start.
    """


@dataclass(frozen=True)
class ModelPrice:
    input_per_million_usd: float
    output_per_million_usd: float


class PricingTable:
    """Looks up cost-per-token for a model, loaded from pricing.json."""

    def __init__(self, prices: dict[str, ModelPrice]) -> None:
        self._prices = prices

    @classmethod
    def load(cls) -> "PricingTable":
        raw = json.loads(_PRICING_FILE.read_text())
        prices = {
            model: ModelPrice(
                input_per_million_usd=entry["input_per_million_usd"],
                output_per_million_usd=entry["output_per_million_usd"],
            )
            for model, entry in raw.items()
            if not model.startswith("_")  # "_note"-style keys are metadata, not a model
        }
        return cls(prices)

    def require(self, model: str) -> None:
        """Fail fast if this model has no configured price.

        Call this once at startup so a missing entry is discovered
        immediately, never mid-conversation or mid-workshop-demo.
        """
        self._price_for(model)

    def cost_for(self, usage: Usage, model: str) -> float:
        """Estimated USD cost for the given token usage on this model."""
        price = self._price_for(model)
        input_cost = (usage.input_tokens / 1_000_000) * price.input_per_million_usd
        output_cost = (usage.output_tokens / 1_000_000) * price.output_per_million_usd
        return input_cost + output_cost

    def _price_for(self, model: str) -> ModelPrice:
        price = self._prices.get(model)
        if price is None:
            raise MissingPricingError(
                f"No pricing configured for model '{model}'. Add an entry "
                f"to {_PRICING_FILE.name} with input_per_million_usd and "
                "output_per_million_usd for this exact model string."
            )
        return price
