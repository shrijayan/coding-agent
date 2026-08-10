"""Cost calculation from token usage, using a hand-maintained pricing table.

Model pricing lives in the shared models.yaml catalog (plain data, not
Python constants) so adding or re-pricing a model is a one-line edit, not
a code change - same philosophy as .env for settings that vary over time.
We deliberately do NOT fetch live prices from providers: for a workshop
with a small, known set of models, a hand-maintained file is far simpler
than building and trusting a live-pricing integration.
"""

from dataclasses import dataclass
from pathlib import Path

from coding_agent.metrics.usage import Usage
from coding_agent.models_config import (
    MODELS_FILE,
    ModelsConfigError,
    read_models_yaml,
)


class MissingPricingError(RuntimeError):
    """Raised when a model has no entry in the models.yaml catalog.

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
    """Looks up cost-per-token for a model, loaded from models.yaml."""

    def __init__(self, prices: dict[str, ModelPrice]) -> None:
        self._prices = prices

    @classmethod
    def load(cls, path: Path | None = None) -> "PricingTable":
        raw = read_models_yaml(path)
        catalog = raw.get("models")
        if not isinstance(catalog, dict):
            raise ModelsConfigError(
                "models.yaml must contain a 'models' mapping of "
                "model -> {input_per_million_usd, output_per_million_usd}."
            )
        prices: dict[str, ModelPrice] = {}
        for model, entry in catalog.items():
            if not isinstance(entry, dict):
                raise ModelsConfigError(
                    f"models.yaml catalog entry for '{model}' must be a mapping."
                )
            try:
                prices[model] = ModelPrice(
                    input_per_million_usd=float(entry["input_per_million_usd"]),
                    output_per_million_usd=float(entry["output_per_million_usd"]),
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ModelsConfigError(
                    f"models.yaml catalog entry for '{model}' needs numeric "
                    "'input_per_million_usd' and 'output_per_million_usd'."
                ) from error
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
                f"to {MODELS_FILE.name}'s 'models:' catalog with "
                "input_per_million_usd and output_per_million_usd for this "
                "exact model string."
            )
        return price
