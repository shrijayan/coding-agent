"""Picks which LLMClient implementation to use, based on Config.

This is the one place in the app that needs to know every provider's
concrete class - everything else (AgentLoop, cli.py) only ever sees the
LLMClient interface. Adding a third provider means adding one branch
here, nowhere else.
"""

from coding_agent.config import Config
from coding_agent.llm.anthropic_client import AnthropicClient
from coding_agent.llm.base import LLMClient
from coding_agent.llm.openrouter_client import OpenRouterClient

_BUILDERS = {
    "anthropic": AnthropicClient,
    "openrouter": OpenRouterClient,
}


def build_llm_client(config: Config) -> LLMClient:
    """Construct the LLMClient for whichever provider Config selected.

    config.provider is already validated by Config.from_env() to be one
    of the keys below, so a lookup failure here would mean a real bug
    (a provider added to Config but not here) - let it raise loudly
    rather than silently falling back to some default provider.
    """
    client_class = _BUILDERS[config.provider]
    return client_class(
        api_key=config.api_key,
        model=config.model,
        max_tokens=config.max_tokens,
    )
