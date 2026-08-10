"""Picks which LLMClient implementation to use, based on Config.

This is the one place in the app that needs to know every provider's
concrete class - everything else (AgentLoop, cli.py, the routing tier
ladder) only ever sees the LLMClient interface. Adding a third provider
means adding one entry here, nowhere else.

Two entry points, for two different callers:

- build_llm_client(config) - the agent's single configured client, built
  from AGENT_PROVIDER / AGENT_MODEL. Unchanged behavior.
- build_provider_client(...) - a client for an *arbitrary* provider/model
  pair, used by the hybrid-routing ladder (optimizations/routing/tiers.py)
  where several models from different providers are live at once.
"""

from coding_agent.config import Config
from coding_agent.llm.anthropic_client import AnthropicClient
from coding_agent.llm.base import LLMClient
from coding_agent.llm.ollama_client import OllamaClient
from coding_agent.llm.openrouter_client import OpenRouterClient

# Providers reached over the internet with an API key.
_API_KEY_BUILDERS = {
    "anthropic": AnthropicClient,
    "openrouter": OpenRouterClient,
}

# Providers reached at a base URL with no key (local inference servers).
_LOCAL_PROVIDERS = {"ollama"}

SUPPORTED_PROVIDERS = frozenset(_API_KEY_BUILDERS) | _LOCAL_PROVIDERS


class UnknownProviderError(RuntimeError):
    """Raised when a configured provider has no client implementation."""


class MissingProviderKeyError(RuntimeError):
    """Raised when a provider needs an API key that isn't set.

    Recoverable for the routing ladder (it skips that tier and carries
    on), unlike Config's startup validation which is fatal.
    """


def build_llm_client(config: Config) -> LLMClient:
    """Construct the LLMClient for whichever provider Config selected.

    config.provider is already validated by Config.from_env() to be one
    of the API-key providers, so a lookup failure here would mean a real
    bug (a provider added to Config but not here) - let it raise loudly
    rather than silently falling back to some default provider.
    """
    client_class = _API_KEY_BUILDERS[config.provider]
    return client_class(
        api_key=config.api_key,
        model=config.model,
        max_tokens=config.max_tokens,
    )


def build_provider_client(
    *,
    provider: str,
    model: str,
    max_tokens: int,
    api_key: str | None = None,
    ollama_base_url: str | None = None,
) -> LLMClient:
    """Build a client for an arbitrary provider/model pair.

    Used by the hybrid-routing ladder, where models.yaml may name several
    providers at once. Raises MissingProviderKeyError (recoverable - the
    ladder skips that tier) rather than assuming a key exists.
    """
    if provider in _LOCAL_PROVIDERS:
        if not ollama_base_url:
            raise UnknownProviderError(
                f"Provider '{provider}' needs a base URL "
                "(AGENT_ROUTING_OLLAMA_BASE_URL) but none was given."
            )
        return OllamaClient(
            base_url=ollama_base_url, model=model, max_tokens=max_tokens
        )

    client_class = _API_KEY_BUILDERS.get(provider)
    if client_class is None:
        supported = ", ".join(sorted(SUPPORTED_PROVIDERS))
        raise UnknownProviderError(
            f"Unknown provider '{provider}'. Supported providers: {supported}."
        )

    if not api_key:
        raise MissingProviderKeyError(
            f"Provider '{provider}' requires an API key, but the matching "
            "environment variable is not set."
        )

    return client_class(api_key=api_key, model=model, max_tokens=max_tokens)
