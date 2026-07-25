"""Loads and validates configuration from environment variables.

Rule of thumb used throughout this file: if required configuration is
missing or invalid, fail immediately with a clear message. We never
silently fall back to a made-up default - a wrong default that "just
works" is much harder to debug later than a loud error on startup.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


class MissingConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    """All settings the agent needs, loaded once at startup."""

    api_key: str
    model: str
    max_tokens: int
    max_iterations: int
    bash_timeout_seconds: int

    @classmethod
    def from_env(cls) -> "Config":
        """Load settings from the environment (and a .env file, if present)."""
        load_dotenv()
        return cls(
            api_key=_require_str("ANTHROPIC_API_KEY"),
            model=_require_str("AGENT_MODEL"),
            max_tokens=_require_int("AGENT_MAX_TOKENS"),
            max_iterations=_require_int("AGENT_MAX_ITERATIONS"),
            bash_timeout_seconds=_require_int("AGENT_BASH_TIMEOUT_SECONDS"),
        )


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
