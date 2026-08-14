"""Loads and validates configuration from environment variables and the
shared models.yaml.

Two sources, on purpose:

- **models.yaml** is the source of truth for WHICH model the base agent
  uses (provider/model/max_tokens), the per-session cost cap, and routing
  settings - the things a workshop wants everyone to share by default.
- **.env** holds secrets (API keys) and per-person behavior knobs
  (iteration caps, timeouts, summary thresholds). Any of the model
  defaults can still be overridden per-person via the matching AGENT_*
  env var, so nobody has to edit the shared file to point at their own
  model.

Rule of thumb used throughout: if required configuration is missing or
invalid, fail immediately with a clear message. We never silently fall
back to a made-up default - a wrong default that "just works" is much
harder to debug later than a loud error on startup.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from coding_agent.models_config import (
    load_defaults,
    load_provider_models,
    load_routing_settings,
    load_session_cost_cap,
    read_models_yaml,
)

# Which env var holds the API key for each supported provider. This is
# fixed program wiring (which key belongs to which provider never
# changes), not an environment-specific setting - unlike the values
# those env vars hold, which is why it lives here as code and not in
# .env.
_PROVIDER_API_KEY_ENV_VARS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

# Providers reached at a base URL with no API key (local inference servers).
# Selectable as the base provider (e.g. AGENT_PROVIDER=ollama) so prompt
# caching and routing can be tested fully offline, with no paid key at all.
_LOCAL_PROVIDERS = {"ollama"}

_SUPPORTED_PROVIDERS = set(_PROVIDER_API_KEY_ENV_VARS) | _LOCAL_PROVIDERS


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
    summary_token_threshold: int
    summary_keep_recent_messages: int
    loop_guard_nudge_after: int
    loop_guard_halt_after: int
    context_prune_keep_recent_messages: int
    context_prune_min_chars_to_prune: int
    context_window_skills_enabled: bool
    """Whether --enable context-window also registers the on-demand skills
    menu/load_skill tool, on top of pruning. Skills add a fixed per-call
    cost (system-prompt menu + tool schema) regardless of whether pruning
    ever fires - set to false to measure pruning's savings in isolation."""
    dedup_min_chars: int
    routing_ollama_base_url: str
    routing_quality_gate_enabled: bool
    otel_exporter_otlp_endpoint: str | None
    """Only used with --enable observability-otel: where to export real OTel
    traces/metrics/logs (OTLP/HTTP). Point it at a local Docker stack
    (http://localhost:4318, see optimizations/observability_stack.py) or
    your own Grafana Cloud OTLP gateway. None means the optimization fails
    fast rather than silently not exporting anywhere - see its build()."""
    otel_exporter_otlp_headers: str | None
    """Comma-separated key=value pairs (the exact format Grafana Cloud's
    "Configure" button generates for OTEL_EXPORTER_OTLP_HEADERS) - e.g. an
    Authorization header for a cloud backend. None/blank for the local
    Docker path, which needs no auth."""
    session_cost_cap_usd: float | None
    """Stop making LLM calls once a session's estimated cost crosses this
    (USD), or None to disable the cap. Sourced from models.yaml so the
    shared workshop budget guardrail lives with the model config; an
    individual can override with AGENT_SESSION_COST_CAP_USD."""
    available_provider_keys: dict[str, str]
    """Every provider API key that happens to be set, by provider name.

    Only the *selected* provider's key is required (see from_env); this
    map exists for the hybrid-routing ladder, whose models.yaml may name a
    second paid provider alongside the main one. Keeping the lookup here
    means no module outside config.py reads os.environ directly."""

    @classmethod
    def from_env(cls) -> "Config":
        """Load settings from models.yaml + the environment (and a .env
        file, if present).

        Model provider/model/max_tokens, the cost cap, and routing
        settings default from models.yaml; the matching AGENT_* env var
        overrides any of them if set. Only the API key for the *selected*
        provider is required - e.g. if the provider resolves to
        openrouter, ANTHROPIC_API_KEY is never checked.
        """
        load_dotenv()
        raw = read_models_yaml()
        defaults = load_defaults(raw)
        gate_enabled, ollama_base_url = load_routing_settings(raw)

        provider = _resolve_provider(defaults.provider)
        return cls(
            provider=provider,
            api_key=_resolve_api_key(provider),
            model=(
                _optional_str("AGENT_MODEL")
                or load_provider_models(raw).get(provider)
                or defaults.model
            ),
            max_tokens=_optional_int("AGENT_MAX_TOKENS", defaults.max_tokens),
            max_iterations=_require_int("AGENT_MAX_ITERATIONS"),
            bash_timeout_seconds=_require_int("AGENT_BASH_TIMEOUT_SECONDS"),
            summary_token_threshold=_require_int("AGENT_SUMMARY_TOKEN_THRESHOLD"),
            summary_keep_recent_messages=_require_int("AGENT_SUMMARY_KEEP_RECENT_MESSAGES"),
            loop_guard_nudge_after=_require_int("AGENT_LOOP_GUARD_NUDGE_AFTER"),
            loop_guard_halt_after=_require_int("AGENT_LOOP_GUARD_HALT_AFTER"),
            context_prune_keep_recent_messages=_require_int(
                "AGENT_CONTEXT_PRUNE_KEEP_RECENT_MESSAGES"
            ),
            context_prune_min_chars_to_prune=_require_int(
                "AGENT_CONTEXT_PRUNE_MIN_CHARS_TO_PRUNE"
            ),
            context_window_skills_enabled=_require_bool(
                "AGENT_CONTEXT_WINDOW_SKILLS_ENABLED"
            ),
            dedup_min_chars=_require_int("AGENT_DEDUP_MIN_CHARS"),
            routing_ollama_base_url=(
                _optional_str("AGENT_ROUTING_OLLAMA_BASE_URL") or ollama_base_url
            ),
            routing_quality_gate_enabled=_optional_bool(
                "AGENT_ROUTING_QUALITY_GATE_ENABLED", gate_enabled
            ),
            otel_exporter_otlp_endpoint=_optional_str("OTEL_EXPORTER_OTLP_ENDPOINT"),
            otel_exporter_otlp_headers=_optional_str("OTEL_EXPORTER_OTLP_HEADERS"),
            session_cost_cap_usd=_resolve_cost_cap(load_session_cost_cap(raw)),
            available_provider_keys=_available_provider_keys(),
        )


def _available_provider_keys() -> dict[str, str]:
    """Collect whichever provider API keys are actually set.

    Deliberately does NOT require any of them - Config already enforces
    that the selected provider's key exists. This is best-effort extra
    information for the routing ladder, so an unset key means "that tier
    is unavailable", not "fail to start".
    """
    found = {}
    for provider, env_var in _PROVIDER_API_KEY_ENV_VARS.items():
        value = os.environ.get(env_var)
        if value:
            found[provider] = value
    return found


def _resolve_provider(default: str) -> str:
    """The selected provider: AGENT_PROVIDER if set, else models.yaml's."""
    value = (_optional_str("AGENT_PROVIDER") or default).lower()
    if value not in _SUPPORTED_PROVIDERS:
        supported = ", ".join(sorted(_SUPPORTED_PROVIDERS))
        raise MissingConfigError(
            f"Provider must be one of: {supported}. Got: '{value}' "
            "(from AGENT_PROVIDER or models.yaml 'default.provider')."
        )
    return value


def _resolve_api_key(provider: str) -> str:
    """The API key for the selected provider - required for paid providers,
    but empty (and never checked) for keyless local ones like Ollama, so
    `AGENT_PROVIDER=ollama` starts with no key set at all."""
    if provider in _LOCAL_PROVIDERS:
        return ""
    return _require_str(_PROVIDER_API_KEY_ENV_VARS[provider])


def _resolve_cost_cap(yaml_cap: float | None) -> float | None:
    """The session cost cap: AGENT_SESSION_COST_CAP_USD if set (a number,
    or 'none'/'off' to disable), else the models.yaml value."""
    raw = _optional_str("AGENT_SESSION_COST_CAP_USD")
    if raw is None:
        return yaml_cap
    if raw.lower() in {"none", "off", "disabled"}:
        return None
    try:
        cap = float(raw)
    except ValueError as error:
        raise MissingConfigError(
            "AGENT_SESSION_COST_CAP_USD must be a number or 'none', "
            f"got: '{raw}'"
        ) from error
    if cap <= 0:
        raise MissingConfigError(
            f"AGENT_SESSION_COST_CAP_USD must be positive (or 'none'), got: {cap}"
        )
    return cap


def _optional_str(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None


def _optional_int(name: str, default: int) -> int:
    value = _optional_str(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as error:
        raise MissingConfigError(
            f"Environment variable '{name}' must be a whole number, got: '{value}'"
        ) from error


def _optional_bool(name: str, default: bool) -> bool:
    value = _optional_str(name)
    if value is None:
        return default
    return _parse_bool(name, value)


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


def _require_bool(name: str) -> bool:
    return _parse_bool(name, _require_str(name))


# The exact strings we accept for a boolean env var, kept explicit rather
# than relying on Python's truthiness (which would treat "false" as True).
_TRUE_VALUES = {"true", "1", "yes", "on"}
_FALSE_VALUES = {"false", "0", "no", "off"}


def _parse_bool(name: str, value: str) -> bool:
    lowered = value.lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    raise MissingConfigError(
        f"Environment variable '{name}' must be a boolean "
        f"(one of: {', '.join(sorted(_TRUE_VALUES | _FALSE_VALUES))}), got: '{value}'"
    )
