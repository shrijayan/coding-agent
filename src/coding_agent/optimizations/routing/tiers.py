"""The model ladder: an ordered, configurable list of tiers to route across.

Loaded from the shared models.yaml (plain data, hand-maintained) rather
than being hardcoded, so changing which models are in the ladder - or how
many there are - is a data edit, not a code change. The ladder lives in
the same file as the model catalog and pricing, so a tier just names a
`model` and its provider is resolved from that catalog entry.

Two ideas do all the work:

- **difficulty_ceiling** - the hardest request this tier is trusted with.
  A request scored 0.0-1.0 starts at the first tier whose ceiling is at
  least that score, which is the pre-generation routing decision.
- **ladder order** - tiers are listed cheapest/weakest first. Escalation
  is simply "move one step right", which is the post-generation cascade.

Validation is fail-fast at startup (see AGENTS.md's configuration rule):
a malformed ladder raises InvalidTierConfigError immediately rather than
silently routing everything to one tier mid-demo.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coding_agent.models_config import ModelsConfigError, read_models_yaml

# Marks the tier that reuses whatever client the optimization wrapped
# (i.e. AGENT_PROVIDER / AGENT_MODEL), so the ladder never needs a
# parallel copy of the main provider settings.
INNER_PROVIDER = "inner"


class InvalidTierConfigError(RuntimeError):
    """Raised when the routing ladder in models.yaml isn't usable."""


@dataclass(frozen=True)
class RoutingTier:
    """One rung of the model ladder."""

    name: str
    provider: str
    model: str | None
    """None only for the 'inner' provider, whose model comes from Config."""
    difficulty_ceiling: float

    @property
    def uses_inner_client(self) -> bool:
        return self.provider == INNER_PROVIDER


def load_tiers(path: Path | None = None) -> list[RoutingTier]:
    """Load and validate the ladder from models.yaml, cheapest first."""
    try:
        raw = read_models_yaml(path)
    except ModelsConfigError as error:
        raise InvalidTierConfigError(str(error)) from error

    routing = raw.get("routing")
    if not isinstance(routing, dict):
        raise InvalidTierConfigError(
            "models.yaml must contain a 'routing' mapping with a 'tiers' list."
        )

    entries = routing.get("tiers")
    if not isinstance(entries, list) or not entries:
        raise InvalidTierConfigError(
            "models.yaml 'routing.tiers' must be a non-empty list, "
            "ordered cheapest/weakest first."
        )

    catalog = raw.get("models") if isinstance(raw.get("models"), dict) else {}
    tiers = [_parse_tier(entry, catalog, index) for index, entry in enumerate(entries)]
    _validate_ladder(tiers)
    return tiers


def _parse_tier(
    entry: object, catalog: dict[str, Any], index: int
) -> RoutingTier:
    if not isinstance(entry, dict):
        raise InvalidTierConfigError(f"routing tier #{index} must be a mapping.")

    for required in ("name", "difficulty_ceiling"):
        if required not in entry:
            raise InvalidTierConfigError(
                f"routing tier #{index} is missing required field '{required}'."
            )

    model = entry.get("model")
    # A tier may state its provider explicitly (e.g. 'inner'); otherwise it
    # is resolved from the named model's catalog entry, so the ladder stays
    # a list of model names and providers live in one place (the catalog).
    provider = entry.get("provider")
    if provider is None and model:
        catalog_entry = catalog.get(str(model))
        if isinstance(catalog_entry, dict):
            provider = catalog_entry.get("provider")

    if provider is None:
        raise InvalidTierConfigError(
            f"routing tier '{entry['name']}' has no provider: either set "
            "'provider' on the tier, or name a 'model' that exists in the "
            "'models:' catalog (whose entry carries the provider)."
        )
    provider = str(provider)

    if provider != INNER_PROVIDER and not model:
        raise InvalidTierConfigError(
            f"routing tier '{entry['name']}' uses provider '{provider}' and "
            "must name a 'model' (only the 'inner' provider may omit it, since "
            "it inherits AGENT_MODEL)."
        )

    ceiling = entry["difficulty_ceiling"]
    if not isinstance(ceiling, int | float) or not 0.0 < ceiling <= 1.0:
        raise InvalidTierConfigError(
            f"routing tier '{entry['name']}' has difficulty_ceiling "
            f"{ceiling!r}; it must be a number greater than 0.0 and at most 1.0."
        )

    return RoutingTier(
        name=str(entry["name"]),
        provider=provider,
        model=str(model) if model else None,
        difficulty_ceiling=float(ceiling),
    )


def _validate_ladder(tiers: list[RoutingTier]) -> None:
    names = [tier.name for tier in tiers]
    if len(set(names)) != len(names):
        raise InvalidTierConfigError(f"routing tier names must be unique, got {names}.")

    ceilings = [tier.difficulty_ceiling for tier in tiers]
    if ceilings != sorted(ceilings):
        raise InvalidTierConfigError(
            "difficulty_ceiling values must increase down the ladder "
            f"(cheapest/weakest first), got {ceilings}."
        )

    if tiers[-1].difficulty_ceiling != 1.0:
        raise InvalidTierConfigError(
            f"the last tier ('{tiers[-1].name}') is the catch-all and must "
            "have difficulty_ceiling 1.0, otherwise the hardest requests "
            f"would have nowhere to go (got {tiers[-1].difficulty_ceiling})."
        )


def starting_index(tiers: list[RoutingTier], difficulty: float) -> int:
    """The pre-generation routing decision, in one line.

    Return the index of the first tier trusted with this difficulty -
    i.e. skip every tier too weak for it. The ladder's last tier has
    ceiling 1.0 (enforced above), so this always finds one.
    """
    for index, tier in enumerate(tiers):
        if difficulty <= tier.difficulty_ceiling:
            return index
    return len(tiers) - 1
