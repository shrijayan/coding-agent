"""Loads and validates configuration from environment variables.

Rule of thumb used throughout this file: if required configuration is
missing or invalid, fail immediately with a clear message. We never
silently fall back to a made-up default - a wrong default that "just
works" is much harder to debug later than a loud error on startup.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Which env var holds the API key for each supported provider. This is
# fixed program wiring (which key belongs to which provider never
# changes), not an environment-specific setting - unlike the values
# those env vars hold, which is why it lives here as code and not in
# .env.
_PROVIDER_API_KEY_ENV_VARS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


class MissingConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    """All settings the agent needs, loaded once at startup."""

    provider: str
    api_key: str
    model: str
    max_tokens: int
    max_iterations: int
    bash_timeout_seconds: int

    @classmethod
    def from_env(cls) -> "Config":
        """Load settings from the environment (and a .env file, if present).

        Only the API key for the *selected* provider is required - e.g.
        if AGENT_PROVIDER=openrouter, ANTHROPIC_API_KEY is never checked
        and doesn't need to be set.
        """
        load_dotenv()
        provider = _require_provider()
        return cls(
            provider=provider,
            api_key=_require_str(_PROVIDER_API_KEY_ENV_VARS[provider]),
            model=_require_str("AGENT_MODEL"),
            max_tokens=_require_int("AGENT_MAX_TOKENS"),
            max_iterations=_require_int("AGENT_MAX_ITERATIONS"),
            bash_timeout_seconds=_require_int("AGENT_BASH_TIMEOUT_SECONDS"),
        )


def _require_provider() -> str:
    value = _require_str("AGENT_PROVIDER").lower()
    if value not in _PROVIDER_API_KEY_ENV_VARS:
        supported = ", ".join(sorted(_PROVIDER_API_KEY_ENV_VARS))
        raise MissingConfigError(
            f"AGENT_PROVIDER must be one of: {supported}. Got: '{value}'."
        )
    return value


def _require_str(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise MissingConfigError(
            f"Missing required environment variable '{name}'. "
            "Copy .env.example to .env and fill in your values."
        )
    return value


def _require_int(name: str) -> int:
    value = _require_str(name)
    try:
        return int(value)
    except ValueError as error:
        raise MissingConfigError(
            f"Environment variable '{name}' must be a whole number, got: '{value}'"
        ) from error
