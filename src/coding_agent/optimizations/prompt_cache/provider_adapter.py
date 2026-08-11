"""The extension point for provider-specific cache optimizations.

This whole optimization is deliberately provider-agnostic: it never emits
Anthropic `cache_control`, an OpenAI prefix hint, or any other vendor field. But
some providers *do* expose an explicit cache API, and a future optimization may
want to use one - so instead of baking that into the shared builder, we expose a
single seam here.

A ProviderCacheAdapter receives the finished, provider-agnostic BuiltPrompt
(including exactly where the stable prefix ends) plus the request about to be
sent, and may return a modified request carrying provider-specific hints. The
default adapter changes nothing, so the base agent stays vendor-neutral; a
provider-specific adapter can be dropped in later - constructor-injected into the
wrapper - without touching PromptBuilder, PromptSerializer, or the core clients.
"""

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from coding_agent.llm.messages import Message
from coding_agent.optimizations.prompt_cache.builder import BuiltPrompt


@dataclass(frozen=True)
class PreparedRequest:
    """The exact arguments about to be handed to the wrapped LLMClient.send()."""

    system: str
    messages: list[Message]
    tools: list[dict[str, Any]]


@runtime_checkable
class ProviderCacheAdapter(Protocol):
    """Optional hook that maps a BuiltPrompt onto one provider's cache API."""

    def apply(self, built: BuiltPrompt, request: PreparedRequest) -> PreparedRequest:
        """Return the request to send - unchanged, or with provider hints added."""
        ...


class NoOpProviderCacheAdapter:
    """The default: stays fully provider-agnostic by passing the request through."""

    def apply(self, built: BuiltPrompt, request: PreparedRequest) -> PreparedRequest:
        return request
