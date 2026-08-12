"""Tests for the unified models.yaml config: catalog pricing, per-model
metadata, the routing ladder loader, and the session cost guard."""

import pytest
import yaml

from coding_agent.metrics.cost_guard import CostGuard
from coding_agent.metrics.pricing import MissingPricingError, PricingTable
from coding_agent.metrics.usage import Usage, UsageTracker
from coding_agent.models_config import (
    ModelsConfigError,
    load_catalog_metadata,
    load_defaults,
    load_routing_settings,
    load_session_cost_cap,
    read_models_yaml,
)
from coding_agent.optimizations.routing.tiers import load_tiers

# --- Shipped models.yaml is internally consistent -------------------------


def test_shipped_yaml_prices_every_ladder_model():
    """Every routing tier's model must have a catalog price - the startup
    contract the whole cost-tracking design depends on."""
    pricing = PricingTable.load()
    for tier in load_tiers():
        if tier.model is not None:
            pricing.require(tier.model)  # raises if missing


def test_shipped_yaml_default_model_is_priced():
    raw = read_models_yaml()
    defaults = load_defaults(raw)
    PricingTable.load().require(defaults.model)


def test_ladder_resolves_provider_from_catalog():
    """A tier names only a model; its provider comes from the catalog."""
    tiers = {t.name: t for t in load_tiers()}
    assert tiers["cheap"].provider == "openrouter"
    assert tiers["cheap"].model == "google/gemma-3.4b"


def test_catalog_metadata_is_exposed():
    meta = load_catalog_metadata(read_models_yaml())
    cheap = meta["google/gemma-3.4b"]
    assert "description" in cheap
    assert isinstance(cheap["strengths"], list)


def test_defaults_and_cap_load():
    raw = read_models_yaml()
    defaults = load_defaults(raw)
    assert defaults.provider == "openrouter"
    assert defaults.max_tokens > 0
    assert load_session_cost_cap(raw) == 1.00
    gate_enabled, base_url = load_routing_settings(raw)
    assert gate_enabled is True
    assert base_url.startswith("http")


# --- Pricing loads from YAML ----------------------------------------------


def test_pricing_cost_for_known_model():
    pricing = PricingTable.load()
    # deepseek high tier: $0.08/M in, $0.252/M out.
    cost = pricing.cost_for(
        Usage(input_tokens=1_000_000, output_tokens=1_000_000),
        "deepseek/deepseek-v4-flash-0731",
    )
    assert cost == pytest.approx(0.08 + 0.252)


def test_pricing_missing_model_raises():
    with pytest.raises(MissingPricingError):
        PricingTable.load().require("no/such-model")


def test_pricing_malformed_catalog_raises(tmp_path):
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump({"models": {"m": {"input_per_million_usd": 1.0}}}))
    with pytest.raises(ModelsConfigError):
        PricingTable.load(path)


# --- Session cost guard ---------------------------------------------------


def test_cost_guard_not_exceeded_below_cap():
    guard = CostGuard(PricingTable.load(), cap_usd=1.00)
    tracker = UsageTracker()
    tracker.record_llm_call(
        Usage(input_tokens=1000, output_tokens=1000),
        "deepseek/deepseek-v4-flash-0731",
    )
    assert not guard.exceeded(tracker)


def test_cost_guard_exceeded_at_cap():
    guard = CostGuard(PricingTable.load(), cap_usd=0.10)
    tracker = UsageTracker()
    # 1M in + 1M out on the high tier ($0.08 + $0.252 = $0.332) blows a $0.10 cap.
    tracker.record_llm_call(
        Usage(input_tokens=1_000_000, output_tokens=1_000_000),
        "deepseek/deepseek-v4-flash-0731",
    )
    assert guard.exceeded(tracker)
    assert "cap of $0.10 reached" in guard.notice(tracker)


def test_agent_loop_stops_when_cap_already_exceeded():
    """The loop refuses to make another call once the cap is crossed,
    returning a notice instead of spending more of a shared budget."""
    from coding_agent.agent.loop import AgentLoop
    from coding_agent.llm.base import LLMClient
    from coding_agent.optimizations.history_policy import DefaultHistoryPolicy
    from coding_agent.tools.registry import ToolRegistry

    class ExplodingClient(LLMClient):
        def send(self, *, system, messages, tools):
            raise AssertionError("should not be called once the cap is hit")

    tracker = UsageTracker()
    tracker.record_llm_call(
        Usage(input_tokens=1_000_000, output_tokens=1_000_000), "deepseek/deepseek-v4-flash-0731"
    )
    loop = AgentLoop(
        llm_client=ExplodingClient(),
        tool_registry=ToolRegistry(tools=[]),
        system_prompt="sys",
        max_iterations=5,
        usage_tracker=tracker,
        history_policy=DefaultHistoryPolicy(),
        cost_guard=CostGuard(PricingTable.load(), cap_usd=0.10),
    )

    answer = loop.run_turn("do something")
    assert "session cost cap" in answer


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
