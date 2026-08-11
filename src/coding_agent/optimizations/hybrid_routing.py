"""Hybrid pre-generation router + post-generation cascade, as one optimization.

This is the whole feature, wired into the repo's first-class extension
point: an OptimizationBundle(wrap_llm_client=...), enabled at runtime with
`--enable hybrid-routing` (and, for free, `--benchmark --enable
hybrid-routing`). It implements two of the survey's six paradigms working
together, across a **configurable ladder of N model tiers**:

  1. Difficulty-aware PRE-generation routing: every outgoing model call is
     scored 0.0-1.0 (free, local - routing/features.py + routing/router.py)
     and starts at the cheapest tier whose difficulty_ceiling covers that
     score, skipping tiers too weak for it entirely.
  2. Post-generation CASCADE: the chosen tier answers, a deterministic
     quality gate (routing/quality_gate.py) checks that output, and on
     failure the request escalates one rung up the ladder and retries -
     repeating until the gate passes or the ladder is exhausted.

Hybrid beats either alone: pure pre-routing wastes the strongest model on
requests that merely *looked* hard; pure cascading always pays for a
cheap generation first even on obviously-hard requests. Scoring first and
gating second spends the expensive model only when it's actually needed.

The ladder itself lives in models.yaml (routing.tiers) - adding a mid
tier, or swapping providers, is a data edit, not a code change. This
module knows only "there is an ordered list of tiers", never how many or
which.

IMPORTANT boundary: the routing decision happens per LLMClient.send(),
which is NOT once per user turn - the agent's tool loop makes many
send()s per turn. So this wrapper never print()s; it records one
RoutingRecord per send() into a shared RoutingTracker, and the CLI prints
a compact per-turn summary from those records (and /metrics prints the
session aggregate).
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from coding_agent.config import Config
from coding_agent.llm.base import LLMClient, LLMError, LLMResponse
from coding_agent.llm.factory import (
    MissingProviderKeyError,
    UnknownProviderError,
    build_provider_client,
)
from coding_agent.llm.messages import Message
from coding_agent.optimizations.bundle import OptimizationBundle
from coding_agent.optimizations.routing.features import extract_features
from coding_agent.optimizations.routing.metrics import (
    PATH_CHEAP,
    PATH_CHEAP_ESCALATED,
    PATH_DIRECT_POWERFUL,
    RoutingRecord,
    RoutingTracker,
)
from coding_agent.optimizations.routing.quality_gate import check
from coding_agent.optimizations.routing.router import score_difficulty
from coding_agent.optimizations.routing.tiers import (
    RoutingTier,
    load_tiers,
    starting_index,
)


class NoUsableTiersError(RuntimeError):
    """Raised when every tier in the ladder is unavailable (no keys set)."""


@dataclass(frozen=True)
class LiveTier:
    """A ladder rung that's actually usable: its config plus a built client."""

    tier: RoutingTier
    client: LLMClient
    model: str
    """The concrete model string, with 'inner' resolved to AGENT_MODEL, so
    /metrics and pricing lookups always have a real name."""


class RoutingLLMClient(LLMClient):
    """Routes each send() across an ordered ladder of model tiers.

    Implements LLMClient itself, so AgentLoop can't tell it apart from a
    plain client - that's what lets routing plug in with zero loop changes.
    """

    def __init__(
        self,
        *,
        tiers: list[LiveTier],
        quality_gate_enabled: bool,
        tracker: RoutingTracker,
    ) -> None:
        if not tiers:
            raise NoUsableTiersError(
                "The hybrid-routing ladder has no usable tiers - check "
                "models.yaml (routing.tiers) and that the needed API keys are set."
            )
        self._tiers = tiers
        self._quality_gate_enabled = quality_gate_enabled
        self._tracker = tracker

    def send(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        difficulty = score_difficulty(extract_features(messages))
        start = starting_index([live.tier for live in self._tiers], difficulty)

        response, index, gate_passed, failed_checks, latency_ms = self._climb(
            start, difficulty, system=system, messages=messages, tools=tools
        )

        self._tracker.record(
            RoutingRecord(
                path=_path_for(start, index),
                difficulty=difficulty,
                model=self._tiers[index].model,
                tier=self._tiers[index].tier.name,
                hops=index - start,
                latency_ms=latency_ms,
                usage=response.usage,
                gate_passed=gate_passed,
                gate_failed_checks=failed_checks,
            )
        )
        # Stamp the answering tier's model so UsageTracker (and /usage)
        # attribute this call's tokens to the model that actually ran.
        return replace(response, model=self._tiers[index].model)

    def _climb(
        self,
        start: int,
        difficulty: float,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
    ) -> tuple[LLMResponse, int, bool | None, list[str], float]:
        """Walk up the ladder from `start` until the gate passes or we run out.

        Returns the accepted response plus the index that produced it, so
        the caller can record which tier actually answered.

        The gate outcome reported back is always the **first** attempt's,
        not the winning tier's. That's deliberate: "did the tier we routed
        to produce acceptable output?" is the question the routing metrics
        exist to answer, and it's also what preserves the reason a request
        escalated. Reporting the winning tier's (clean) result instead
        would silently erase why the escalation happened at all.

        Latency is cumulative: it includes every failed attempt the user
        waited through, not just the successful one.
        """
        total_latency_ms = 0.0
        first_gate_passed: bool | None = None
        first_failed_checks: list[str] = []
        recorded_first = False
        last_error: LLMError | None = None

        for index in range(start, len(self._tiers)):
            is_last = index == len(self._tiers) - 1

            try:
                response, latency_ms = _timed(
                    lambda live=self._tiers[index]: live.client.send(
                        system=system, messages=messages, tools=tools
                    )
                )
            except LLMError as error:
                # This tier is unreachable (e.g. Ollama not running).
                # Recover gracefully by trying the next rung; only give up
                # if there is none, so a demo never dies mid-workshop.
                last_error = error
                if not recorded_first:
                    first_gate_passed, first_failed_checks = False, ["tier_error"]
                    recorded_first = True
                if is_last:
                    raise
                continue

            total_latency_ms += latency_ms

            if not self._quality_gate_enabled:
                return response, index, None, [], total_latency_ms

            gate = check(response, tools)
            if not recorded_first:
                first_gate_passed = gate.passed
                first_failed_checks = gate.failed_checks
                recorded_first = True

            if gate.passed or is_last:
                # The top rung's answer is accepted even if the gate fails -
                # there is nothing better to escalate to, and returning the
                # best available answer beats returning nothing.
                return (
                    response,
                    index,
                    first_gate_passed,
                    first_failed_checks,
                    total_latency_ms,
                )

        # Unreachable in practice: the loop above either returns or raises
        # on the last rung. Kept explicit rather than falling off the end.
        raise last_error or NoUsableTiersError("Routing ladder produced no response.")


def _path_for(start: int, answered: int) -> str:
    """Map a (start, answered) pair onto the three canonical path names.

    These names predate the N-tier ladder and are kept because they're
    what /metrics and the workshop narrative talk about:
      cheap            - started at the bottom and it worked
      cheap_escalated  - had to climb at least one rung
      direct_powerful  - pre-router skipped the cheap tier(s) entirely
    """
    if answered > start:
        return PATH_CHEAP_ESCALATED
    if start == 0:
        return PATH_CHEAP
    return PATH_DIRECT_POWERFUL


def _timed(call: Callable[[], LLMResponse]) -> tuple[LLMResponse, float]:
    start = time.perf_counter()
    response = call()
    latency_ms = (time.perf_counter() - start) * 1000.0
    return response, latency_ms


def build_live_tiers(
    config: Config, inner: LLMClient, tiers: list[RoutingTier] | None = None
) -> tuple[list[LiveTier], list[str]]:
    """Turn the configured ladder into usable tiers, skipping what we can't build.

    Returns (live_tiers, warnings). A tier whose provider key isn't set is
    skipped with a warning rather than failing startup - a partially
    configured ladder (e.g. no paid key yet) still runs on whatever rungs
    are available, which is the graceful-degradation rule from AGENTS.md.
    """
    ladder = tiers if tiers is not None else load_tiers(provider=config.provider)
    live: list[LiveTier] = []
    warnings: list[str] = []

    for tier in ladder:
        if tier.uses_inner_client:
            live.append(LiveTier(tier=tier, client=inner, model=config.model))
            continue
        try:
            client = build_provider_client(
                provider=tier.provider,
                model=tier.model or "",
                max_tokens=config.max_tokens,
                api_key=config.available_provider_keys.get(tier.provider),
                ollama_base_url=config.routing_ollama_base_url,
            )
        except (MissingProviderKeyError, UnknownProviderError) as error:
            warnings.append(f"routing: skipping tier '{tier.name}' - {error}")
            continue
        live.append(LiveTier(tier=tier, client=client, model=tier.model or ""))

    return live, warnings


# The RoutingTracker must be shared between the wrapper (which records into
# it) and the /metrics command (which reads it). build() runs first during
# startup, so it creates the session's tracker and stashes it here; cli.py
# then retrieves the same instance via get_tracker() to wire /metrics. A
# fresh one per build() keeps benchmark tasks isolated (each resolves its
# own bundle), matching how the reference optimization stays per-session.
_last_tracker: RoutingTracker | None = None
_last_warnings: list[str] = []


def get_tracker() -> RoutingTracker:
    """Return the tracker from the most recent build() (creating one if the
    optimization hasn't been built yet, so callers never get None)."""
    global _last_tracker
    if _last_tracker is None:
        _last_tracker = RoutingTracker()
    return _last_tracker


def get_warnings() -> list[str]:
    """Any tiers skipped while building the ladder, for the CLI to show once."""
    return list(_last_warnings)


def build() -> OptimizationBundle:
    global _last_tracker, _last_warnings
    config = Config.from_env()
    tracker = RoutingTracker()
    _last_tracker = tracker
    _last_warnings = []

    def wrap(inner: LLMClient) -> LLMClient:
        global _last_warnings
        live_tiers, warnings = build_live_tiers(config, inner)
        _last_warnings = warnings
        return RoutingLLMClient(
            tiers=live_tiers,
            quality_gate_enabled=config.routing_quality_gate_enabled,
            tracker=tracker,
        )

    return OptimizationBundle(wrap_llm_client=wrap)
