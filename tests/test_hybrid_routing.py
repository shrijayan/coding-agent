"""Tests for the hybrid pre-generation router + post-generation cascade.

These drive the routing wrapper's send(), the difficulty scorer, the
quality gate, and the tier-ladder loader directly with in-memory fake
LLMClients - no subprocess, no HTTP, no real Ollama. Assertions are on
the recorded RoutingTracker entries and on RoutingMetricsCommand.run().
"""

import pytest
import yaml

from coding_agent.commands.metrics_command import RoutingMetricsCommand
from coding_agent.llm.base import LLMClient, LLMError, LLMResponse
from coding_agent.llm.messages import Message, TextPart, ToolUsePart
from coding_agent.metrics.pricing import PricingTable
from coding_agent.metrics.usage import Usage, UsageTracker
from coding_agent.optimizations.hybrid_routing import (
    LiveTier,
    NoUsableTiersError,
    RoutingLLMClient,
)
from coding_agent.optimizations.routing import quality_gate
from coding_agent.optimizations.routing.features import extract_features
from coding_agent.optimizations.routing.metrics import (
    PATH_CHEAP,
    PATH_CHEAP_ESCALATED,
    PATH_DIRECT_POWERFUL,
    RoutingTracker,
)
from coding_agent.optimizations.routing.router import (
    CLAUSE_COMPLEXITY_WEIGHT,
    LENGTH_WEIGHT,
    TECHNICAL_DENSITY_WEIGHT,
    score_difficulty,
)
from coding_agent.optimizations.routing.tiers import (
    InvalidTierConfigError,
    RoutingTier,
    load_tiers,
    starting_index,
)

THRESHOLD = 0.55
CHEAP_MODEL = "ollama/qwen2.5-coder:7b"
POWERFUL_MODEL = "claude-sonnet-5"

EASY_PROMPT = "write a function that reverses a string"
HARD_PROMPT = (
    "design a multi-tenant rate limiter backed by Redis with failure-mode trade-offs"
)
# A genuinely hard request that uses NONE of the hardcoded hard keywords -
# the case the first version of the scorer could never route correctly.
NOVEL_HARD_PROMPT = (
    "Our GraphQL resolver fan-out is saturating the connection pool under burst "
    "traffic and the p99 tail is collapsing. Walk me through how you would "
    "restructure the dataloader batching and backpressure so the upstream service "
    "stops shedding requests, and explain what breaks if a shard goes cold "
    "mid-flight. Consider what happens during a rolling deploy as well as steady "
    "state operation here."
)

VALID_CODE = "Here you go:\n```python\ndef reverse(s):\n    return s[::-1]\n```"
INVALID_CODE = "Sure:\n```python\ndef broken(:\n    return\n```"


class FakeClient(LLMClient):
    """A canned LLMClient: returns a fixed response and counts its calls."""

    def __init__(
        self,
        text: str,
        usage: Usage | None = None,
        tool_calls: list[ToolUsePart] | None = None,
    ) -> None:
        self._text = text
        self._usage = usage or Usage(input_tokens=10, output_tokens=20)
        self._tool_calls = tool_calls or []
        self.calls = 0

    def send(self, *, system, messages, tools) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            text=self._text,
            tool_calls=self._tool_calls,
            wants_tool_use=bool(self._tool_calls),
            usage=self._usage,
        )


class ExplodingClient(LLMClient):
    """A tier that simulates its backend being unreachable."""

    def __init__(self) -> None:
        self.calls = 0

    def send(self, *, system, messages, tools) -> LLMResponse:
        self.calls += 1
        raise LLMError("Could not reach Ollama")


def _messages(text: str) -> list[Message]:
    return [Message(role="user", parts=[TextPart(text)])]


def _tier(name: str, ceiling: float) -> RoutingTier:
    return RoutingTier(
        name=name, provider="ollama", model=name, difficulty_ceiling=ceiling
    )


def _ladder(*pairs: tuple[str, float, LLMClient]) -> list[LiveTier]:
    """Build a live ladder from (name, ceiling, client) triples."""
    return [
        LiveTier(tier=_tier(name, ceiling), client=client, model=model_for(name))
        for name, ceiling, client in pairs
    ]


def model_for(name: str) -> str:
    """Map a tier name onto a model string that exists in the models.yaml catalog."""
    return CHEAP_MODEL if name == "cheap" else POWERFUL_MODEL


def _two_tier(cheap: LLMClient, powerful: LLMClient) -> list[LiveTier]:
    return _ladder(("cheap", THRESHOLD, cheap), ("powerful", 1.0, powerful))


def _wrapper(tiers: list[LiveTier], tracker: RoutingTracker, *, gate: bool = True):
    return RoutingLLMClient(
        tiers=tiers, quality_gate_enabled=gate, tracker=tracker
    )


def _send(wrapper: RoutingLLMClient, text: str) -> LLMResponse:
    return wrapper.send(system="sys", messages=_messages(text), tools=[])


def _score(text: str) -> float:
    return score_difficulty(extract_features(_messages(text)))


# --- Difficulty scorer ---------------------------------------------------


def test_scorer_ranks_easy_below_and_hard_at_or_above_threshold():
    assert _score(EASY_PROMPT) < THRESHOLD
    assert _score(HARD_PROMPT) >= THRESHOLD


def test_scorer_detects_hard_request_using_no_known_keywords():
    """Regression test for the original scorer's structural flaw.

    A hard request phrased in vocabulary absent from HARD_KEYWORDS used to
    max out at 0.50 - below the 0.55 threshold - so it could NEVER be
    routed to the powerful tier no matter how hard it was.
    """
    features = extract_features(_messages(NOVEL_HARD_PROMPT))
    assert features.hard_keyword_hits == 0, "prompt must avoid all known keywords"
    assert _score(NOVEL_HARD_PROMPT) >= THRESHOLD


def test_vocabulary_independent_signals_can_exceed_any_sane_threshold():
    """The structural guarantee: keyword lists are a boost, not the foundation."""
    ceiling = LENGTH_WEIGHT + TECHNICAL_DENSITY_WEIGHT + CLAUSE_COMPLEXITY_WEIGHT
    assert ceiling > THRESHOLD


def test_easy_prompts_stay_easy():
    for prompt in (
        EASY_PROMPT,
        "fix the typo in the readme",
        "print hello world",
        "rename the variable foo to bar",
    ):
        assert _score(prompt) < THRESHOLD, prompt


# --- Tier ladder configuration ------------------------------------------


def test_shipped_models_yaml_ladder_is_valid():
    tiers = load_tiers()
    assert len(tiers) >= 2
    assert tiers[-1].difficulty_ceiling == 1.0
    assert [t.difficulty_ceiling for t in tiers] == sorted(
        t.difficulty_ceiling for t in tiers
    )


def test_starting_index_skips_tiers_too_weak_for_the_request():
    ladder = [_tier("cheap", 0.3), _tier("mid", 0.7), _tier("strong", 1.0)]
    assert starting_index(ladder, 0.1) == 0
    assert starting_index(ladder, 0.5) == 1
    assert starting_index(ladder, 0.95) == 2


@pytest.mark.parametrize(
    "bad,reason",
    [
        ({"routing": {"tiers": []}}, "empty ladder"),
        (
            {"routing": {"tiers": [{"name": "a", "provider": "ollama", "model": "m",
                        "difficulty_ceiling": 0.5}]}},
            "last ceiling must be 1.0",
        ),
        (
            {"routing": {"tiers": [
                {"name": "a", "provider": "ollama", "model": "m", "difficulty_ceiling": 0.9},
                {"name": "b", "provider": "ollama", "model": "m", "difficulty_ceiling": 1.0},
                {"name": "c", "provider": "ollama", "model": "m", "difficulty_ceiling": 0.4},
            ]}},
            "ceilings must ascend",
        ),
        (
            {"routing": {"tiers": [{"name": "a", "provider": "ollama",
                        "difficulty_ceiling": 1.0}]}},
            "non-inner tier needs a model",
        ),
        (
            {"routing": {"tiers": [{"name": "a", "model": "unknown-model",
                        "difficulty_ceiling": 1.0}]}},
            "model absent from catalog has no resolvable provider",
        ),
    ],
)
def test_invalid_ladders_fail_fast(tmp_path, bad, reason):
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump(bad))
    with pytest.raises(InvalidTierConfigError):
        load_tiers(path)


def test_three_tier_ladder_escalates_stepwise():
    """The N-tier capability: cheap -> mid -> strong, one rung at a time."""
    cheap = FakeClient(INVALID_CODE)   # fails the gate
    mid = FakeClient(INVALID_CODE)     # also fails
    strong = FakeClient(VALID_CODE)    # finally passes
    tracker = RoutingTracker()
    ladder = _ladder(("cheap", 0.3, cheap), ("mid", 0.7, mid), ("strong", 1.0, strong))

    response = _send(_wrapper(ladder, tracker), EASY_PROMPT)

    assert response.text == VALID_CODE
    assert (cheap.calls, mid.calls, strong.calls) == (1, 1, 1)
    record = tracker.records[0]
    assert record.path == PATH_CHEAP_ESCALATED
    assert record.tier == "strong"
    assert record.hops == 2


def test_hard_request_skips_lower_rungs_entirely():
    cheap = FakeClient("never called")
    mid = FakeClient("never called")
    strong = FakeClient("strong answer")
    tracker = RoutingTracker()
    ladder = _ladder(("cheap", 0.3, cheap), ("mid", 0.5, mid), ("strong", 1.0, strong))

    response = _send(_wrapper(ladder, tracker), HARD_PROMPT)

    assert response.text == "strong answer"
    assert cheap.calls == 0 and mid.calls == 0
    record = tracker.records[0]
    assert record.path == PATH_DIRECT_POWERFUL
    assert record.tier == "strong"
    assert record.hops == 0


# --- Core routing behavior ----------------------------------------------


def test_easy_prompt_routes_cheap_and_passes_gate():
    cheap = FakeClient(VALID_CODE)
    powerful = FakeClient("should not be called")
    tracker = RoutingTracker()

    response = _send(_wrapper(_two_tier(cheap, powerful), tracker), EASY_PROMPT)

    assert response.text == VALID_CODE
    assert response.model == CHEAP_MODEL
    assert cheap.calls == 1
    assert powerful.calls == 0
    record = tracker.records[0]
    assert record.path == PATH_CHEAP
    assert record.model == CHEAP_MODEL
    assert record.gate_passed is True
    assert record.difficulty < THRESHOLD
    assert PricingTable.load().cost_for(record.usage, record.model) == 0.0


def test_hard_prompt_routes_direct_to_powerful():
    cheap = FakeClient("should not be called")
    powerful = FakeClient("powerful answer")
    tracker = RoutingTracker()

    response = _send(_wrapper(_two_tier(cheap, powerful), tracker), HARD_PROMPT)

    assert response.text == "powerful answer"
    assert cheap.calls == 0
    assert powerful.calls == 1
    record = tracker.records[0]
    assert record.path == PATH_DIRECT_POWERFUL
    assert record.difficulty >= THRESHOLD


def test_cheap_invalid_code_escalates_to_powerful():
    cheap = FakeClient(INVALID_CODE)
    powerful = FakeClient("corrected powerful answer")
    tracker = RoutingTracker()

    response = _send(_wrapper(_two_tier(cheap, powerful), tracker), EASY_PROMPT)

    assert response.text == "corrected powerful answer"
    assert response.model == POWERFUL_MODEL
    assert cheap.calls == 1 and powerful.calls == 1
    record = tracker.records[0]
    assert record.path == PATH_CHEAP_ESCALATED
    assert "ast_valid=false" in record.gate_failed_checks
    assert record.model == POWERFUL_MODEL


def test_unreachable_tier_falls_through_to_next_rung():
    cheap = ExplodingClient()
    powerful = FakeClient("powerful fallback")
    tracker = RoutingTracker()

    response = _send(_wrapper(_two_tier(cheap, powerful), tracker), EASY_PROMPT)

    assert response.text == "powerful fallback"
    assert powerful.calls == 1
    assert tracker.records[0].path == PATH_CHEAP_ESCALATED


def test_last_rung_answer_is_kept_even_if_gate_fails():
    """Nothing better to escalate to - returning the best available answer
    beats returning nothing."""
    cheap = FakeClient(INVALID_CODE)
    tracker = RoutingTracker()
    ladder = _ladder(("cheap", 1.0, cheap))

    response = _send(_wrapper(ladder, tracker), EASY_PROMPT)

    assert response.text == INVALID_CODE
    record = tracker.records[0]
    assert record.path == PATH_CHEAP
    assert record.gate_passed is False


def test_empty_ladder_is_rejected():
    with pytest.raises(NoUsableTiersError):
        RoutingLLMClient(tiers=[], quality_gate_enabled=True, tracker=RoutingTracker())


def test_gate_disabled_keeps_cheap_output():
    cheap = FakeClient(INVALID_CODE)
    powerful = FakeClient("not called")
    tracker = RoutingTracker()

    response = _send(
        _wrapper(_two_tier(cheap, powerful), tracker, gate=False), EASY_PROMPT
    )

    assert response.text == INVALID_CODE
    assert powerful.calls == 0
    assert tracker.records[0].gate_passed is None


# --- Quality gate checks -------------------------------------------------


def _response(text: str, tool_calls: list[ToolUsePart] | None = None) -> LLMResponse:
    return LLMResponse(
        text=text,
        tool_calls=tool_calls or [],
        wants_tool_use=bool(tool_calls),
        usage=Usage(),
    )


def test_gate_passes_clean_output():
    assert quality_gate.check(_response(VALID_CODE)).passed


def test_gate_catches_broken_python():
    result = quality_gate.check(_response(INVALID_CODE))
    assert not result.passed
    assert result.ast_valid is False


def test_gate_catches_truncated_code_fence():
    result = quality_gate.check(_response("Here:\n```python\ndef f():\n    return 1\n"))
    assert not result.passed
    assert "unterminated_code_fence" in result.failed_checks


def test_gate_catches_empty_response():
    result = quality_gate.check(_response("   "))
    assert not result.passed
    assert "empty_response" in result.failed_checks


def test_gate_catches_refusal():
    result = quality_gate.check(_response("I'm sorry, I cannot help with that."))
    assert not result.passed
    assert "refusal" in result.failed_checks


def test_gate_ignores_hedging_when_work_was_actually_done():
    """A refusal phrase alongside real output is harmless - don't pay to escalate."""
    text = "I'm not sure how idiomatic this is, but:\n```python\nx = 1\n```"
    assert quality_gate.check(_response(text)).passed


def test_gate_catches_placeholder_code():
    text = "```python\ndef solve():\n    # TODO: implement\n    pass\n```"
    result = quality_gate.check(_response(text))
    assert not result.passed
    assert "placeholder_code" in result.failed_checks


def test_gate_catches_tool_call_missing_required_argument():
    tools = [
        {
            "name": "write_file",
            "description": "write",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        }
    ]
    call = ToolUsePart(id="1", name="write_file", input={"path": "a.py"})
    result = quality_gate.check(_response("", [call]), tools)
    assert not result.passed
    assert any("missing_tool_arguments" in check for check in result.failed_checks)


def test_gate_accepts_complete_tool_call():
    tools = [
        {
            "name": "write_file",
            "description": "write",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        }
    ]
    call = ToolUsePart(id="1", name="write_file", input={"path": "a.py", "content": "x"})
    assert quality_gate.check(_response("", [call]), tools).passed


# --- /metrics -------------------------------------------------------------


def test_metrics_command_reports_aggregated_values():
    tracker = RoutingTracker()
    pricing = PricingTable.load()

    _send(_wrapper(_two_tier(FakeClient(VALID_CODE), FakeClient("p")), tracker), EASY_PROMPT)
    _send(_wrapper(_two_tier(FakeClient("x"), FakeClient("p")), tracker), HARD_PROMPT)
    _send(_wrapper(_two_tier(FakeClient(INVALID_CODE), FakeClient("p")), tracker), EASY_PROMPT)

    output = RoutingMetricsCommand(tracker=tracker, pricing=pricing).run()

    assert "Total routed calls : 3" in output
    assert "direct_powerful  : 1" in output
    assert "cheap            : 1" in output
    assert "cheap_escalated  : 1" in output
    assert "Escalation rate    : 50.0%" in output
    # Gate pass rate counts every send where the gate ran, on whichever tier
    # the pre-router chose: the cheap VALID send passed, the direct_powerful
    # send passed, the cheap INVALID send failed (and escalated) = 2/3.
    assert "Quality-gate pass  : 66.7%" in output
    assert "Answered by tier:" in output
    assert "Total routed cost" in output


def test_metrics_command_handles_empty_session():
    output = RoutingMetricsCommand(
        tracker=RoutingTracker(), pricing=PricingTable.load()
    ).run()
    assert "No routed model calls yet" in output


# --- Per-model usage tracking (/usage) ------------------------------------


def test_usage_tracker_accumulates_per_model():
    tracker = UsageTracker()
    tracker.record_llm_call(Usage(input_tokens=10, output_tokens=20), CHEAP_MODEL)
    tracker.record_llm_call(Usage(input_tokens=100, output_tokens=200), POWERFUL_MODEL)
    tracker.record_llm_call(Usage(input_tokens=1, output_tokens=2), CHEAP_MODEL)

    assert tracker.total == Usage(input_tokens=111, output_tokens=222)
    assert tracker.by_model[CHEAP_MODEL] == Usage(input_tokens=11, output_tokens=22)
    assert tracker.by_model[POWERFUL_MODEL] == Usage(input_tokens=100, output_tokens=200)
    assert tracker.calls_by_model == {CHEAP_MODEL: 2, POWERFUL_MODEL: 1}


def test_usage_command_prices_each_model_at_its_own_rate():
    from coding_agent.commands.usage_command import UsageCommand

    class _Cfg:
        provider = "anthropic"
        model = POWERFUL_MODEL

    tracker = UsageTracker()
    # 1M cheap tokens are free; powerful tokens are not - pricing the
    # merged total at the powerful rate would be off by dollars.
    tracker.record_llm_call(
        Usage(input_tokens=1_000_000, output_tokens=1_000_000), CHEAP_MODEL
    )
    tracker.record_llm_call(
        Usage(input_tokens=1_000_000, output_tokens=0), POWERFUL_MODEL
    )

    output = UsageCommand(
        tracker=tracker,
        pricing=PricingTable.load(),
        config=_Cfg(),
        enabled_optimizations=["hybrid-routing"],
    ).run()

    assert f"Models used    : {CHEAP_MODEL}, {POWERFUL_MODEL}" in output
    assert "Per model:" in output
    # $2/M input for claude-sonnet-5, cheap tier free = $2.0000 total.
    assert "Estimated cost : $2.0000" in output


# --- Nothing pre-existing broke ------------------------------------------


def test_hybrid_routing_registered_alongside_existing_optimizations():
    from coding_agent.optimizations.available import AVAILABLE_OPTIMIZATIONS

    assert "hybrid-routing" in AVAILABLE_OPTIMIZATIONS
    assert "conversation-summary" in AVAILABLE_OPTIMIZATIONS


def test_existing_usage_command_still_constructs():
    from coding_agent.commands.registry import SlashCommandRegistry
    from coding_agent.commands.usage_command import UsageCommand
    from coding_agent.metrics.usage import UsageTracker

    class _Cfg:
        provider = "anthropic"
        model = POWERFUL_MODEL

    registry = SlashCommandRegistry(
        commands=[
            UsageCommand(
                tracker=UsageTracker(),
                pricing=PricingTable.load(),
                config=_Cfg(),
                enabled_optimizations=[],
            )
        ]
    )
    assert registry.is_command("/usage")
    assert "Usage (this session)" in registry.run("/usage")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
