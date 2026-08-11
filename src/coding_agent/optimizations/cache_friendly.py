"""Cache-friendly prompt construction, wired as one optimization.

Enabled with `--enable cache-friendly-prompts`. It plugs into the repo's
first-class extension point - OptimizationBundle(wrap_llm_client=...) - so the
agent loop and every provider client stay untouched: the whole feature is a
decorator around LLMClient.

What it does on every send():
  1. Rebuild the outgoing prompt through a deterministic, layered pipeline
     (PromptBuilder + PromptSerializer): stable layers first (system prompt,
     tool definitions), then the established conversation, then the latest turn -
     with tools sorted by name and all JSON canonicalized, so the bytes that hit
     the wire are identical whenever the underlying content is.
  2. Forward the normalized system string and canonically-ordered tools to the
     wrapped client; conversation messages pass through untouched and in order.
     An optional, constructor-injected ProviderCacheAdapter gets the last word,
     so a provider-specific cache API can be added later without touching core.
  3. Record cache instrumentation (stable-prefix hash + size, reuse vs the
     previous request, cache-friendly ratio, real input tokens) into a shared
     PromptCacheTracker that /cache reads.

It never estimates tokens: "prompt tokens" comes from the provider's real usage
on the response; every structural figure (prefix size, reuse %) is measured in
canonical bytes, which is deterministic, not a guess.

Boundary note (same as hybrid_routing): a send() happens many times per user
turn (the tool loop), so this wrapper never prints; it records one row per
send() and the CLI prints a compact per-turn roll-up (and /cache the aggregate).
"""

from typing import Any

from coding_agent.llm.base import LLMClient, LLMResponse
from coding_agent.llm.messages import Message
from coding_agent.optimizations.bundle import OptimizationBundle
from coding_agent.optimizations.prompt_cache.builder import PromptBuilder
from coding_agent.optimizations.prompt_cache.metrics import PromptCacheTracker
from coding_agent.optimizations.prompt_cache.provider_adapter import (
    NoOpProviderCacheAdapter,
    PreparedRequest,
    ProviderCacheAdapter,
)


class CacheFriendlyLLMClient(LLMClient):
    """Runs each send() through the deterministic prompt pipeline, then delegates.

    Implements LLMClient itself, so AgentLoop can't tell it apart from a plain
    client - that's what lets cache-friendly construction plug in with zero loop
    changes.
    """

    def __init__(
        self,
        *,
        inner: LLMClient,
        builder: PromptBuilder,
        tracker: PromptCacheTracker,
        adapter: ProviderCacheAdapter | None = None,
    ) -> None:
        self._inner = inner
        self._builder = builder
        self._tracker = tracker
        self._adapter = adapter or NoOpProviderCacheAdapter()

    def send(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        built = self._builder.build(system=system, messages=messages, tools=tools)

        request = PreparedRequest(
            system=built.system, messages=messages, tools=built.tools
        )
        request = self._adapter.apply(built, request)

        response = self._inner.send(
            system=request.system, messages=request.messages, tools=request.tools
        )

        # Real prompt tokens straight off the provider's response - never
        # estimated. Everything else on the record is a deterministic byte fact.
        self._tracker.record(
            built=built,
            input_tokens=response.usage.input_tokens,
            model=response.model,
        )
        return response


# The PromptCacheTracker must be shared between the wrapper (which records into
# it) and the /cache command (which reads it). build() runs first during
# startup, creates the session's tracker, and stashes it here; cli.py retrieves
# the same instance via get_tracker() to wire /cache. A fresh one per build()
# keeps benchmark tasks isolated, matching how hybrid_routing does it.
_last_tracker: PromptCacheTracker | None = None


def get_tracker() -> PromptCacheTracker:
    """Return the tracker from the most recent build() (creating one if the
    optimization hasn't been built yet, so callers never get None)."""
    global _last_tracker
    if _last_tracker is None:
        _last_tracker = PromptCacheTracker()
    return _last_tracker


def build() -> OptimizationBundle:
    global _last_tracker
    tracker = PromptCacheTracker()
    _last_tracker = tracker

    def wrap(inner: LLMClient) -> LLMClient:
        return CacheFriendlyLLMClient(
            inner=inner,
            builder=PromptBuilder(),
            tracker=tracker,
        )

    return OptimizationBundle(wrap_llm_client=wrap)
