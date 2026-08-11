"""Loads the unified model config (models.yaml) - the single source of
truth for model defaults, pricing, per-model metadata, and the routing
ladder.

This module only reads and lightly validates the raw YAML; the three
consumers each pull the slice they need so there's no circular import:

- metrics/pricing.py            -> the `models:` catalog (prices)
- optimizations/routing/tiers.py -> the `routing.tiers` ladder
- config.py                     -> the `default:` block + cost cap

Keeping the file read here (not duplicated in each consumer) means the
YAML path and parse-error handling live in exactly one place. Same
fail-fast rule as the rest of the project: a malformed file raises
immediately at startup with a clear message, never a silent default.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

MODELS_FILE = Path(__file__).parent / "models.yaml"


class ModelsConfigError(RuntimeError):
    """Raised when models.yaml is missing, unparseable, or malformed."""


@dataclass(frozen=True)
class ModelDefaults:
    """The base agent's model settings when routing is off."""

    provider: str
    model: str
    max_tokens: int


def read_models_yaml(path: Path | None = None) -> dict[str, Any]:
    """Read and parse models.yaml into a plain dict."""
    source = path or MODELS_FILE
    try:
        raw = yaml.safe_load(source.read_text())
    except (OSError, yaml.YAMLError) as error:
        raise ModelsConfigError(f"Could not read {source.name}: {error}") from error
    if not isinstance(raw, dict):
        raise ModelsConfigError(f"{source.name} must be a mapping at the top level.")
    return raw


def load_defaults(raw: dict[str, Any]) -> ModelDefaults:
    """Pull the base-agent defaults from a parsed models.yaml."""
    block = raw.get("default")
    if not isinstance(block, dict):
        raise ModelsConfigError("models.yaml must contain a 'default' mapping.")
    for field in ("provider", "model", "max_tokens"):
        if field not in block:
            raise ModelsConfigError(f"models.yaml 'default' is missing '{field}'.")
    try:
        max_tokens = int(block["max_tokens"])
    except (TypeError, ValueError) as error:
        raise ModelsConfigError(
            f"models.yaml 'default.max_tokens' must be a whole number, "
            f"got {block['max_tokens']!r}."
        ) from error
    return ModelDefaults(
        provider=str(block["provider"]).lower(),
        model=str(block["model"]),
        max_tokens=max_tokens,
    )


def load_provider_models(raw: dict[str, Any]) -> dict[str, str]:
    """Per-provider base-model overrides (provider name -> model string).

    Optional block: absent means an empty map. Lets `AGENT_PROVIDER=<name>`
    pick the right base model without also setting AGENT_MODEL (e.g. selecting
    ollama for local testing), while `default:` still owns the committed
    default provider/model.
    """
    block = raw.get("provider_models")
    if block is None:
        return {}
    if not isinstance(block, dict):
        raise ModelsConfigError("models.yaml 'provider_models' must be a mapping.")
    return {str(provider).lower(): str(model) for provider, model in block.items()}


def load_session_cost_cap(raw: dict[str, Any]) -> float | None:
    """The per-session spend cap in USD, or None if disabled/absent."""
    value = raw.get("session_cost_cap_usd")
    if value is None:
        return None
    try:
        cap = float(value)
    except (TypeError, ValueError) as error:
        raise ModelsConfigError(
            f"models.yaml 'session_cost_cap_usd' must be a number or null, "
            f"got {value!r}."
        ) from error
    if cap <= 0:
        raise ModelsConfigError(
            "models.yaml 'session_cost_cap_usd' must be positive (or null to "
            f"disable), got {cap}."
        )
    return cap


def load_routing_settings(raw: dict[str, Any]) -> tuple[bool, str]:
    """(quality_gate_enabled, ollama_base_url) from the routing block."""
    block = raw.get("routing")
    if not isinstance(block, dict):
        raise ModelsConfigError("models.yaml must contain a 'routing' mapping.")
    gate = block.get("quality_gate_enabled", True)
    base_url = block.get("ollama_base_url", "http://localhost:11434/v1")
    return bool(gate), str(base_url)


def load_catalog_metadata(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """model string -> its `metadata` mapping (empty dict if none).

    Used by /usage to annotate which models a session touched. Returns a
    plain dict rather than a typed object because metadata is free-form,
    human-facing context whose shape is expected to grow.
    """
    catalog = raw.get("models")
    if not isinstance(catalog, dict):
        raise ModelsConfigError("models.yaml must contain a 'models' mapping.")
    metadata: dict[str, dict[str, Any]] = {}
    for model, entry in catalog.items():
        if isinstance(entry, dict) and isinstance(entry.get("metadata"), dict):
            metadata[model] = entry["metadata"]
        else:
            metadata[model] = {}
    return metadata
