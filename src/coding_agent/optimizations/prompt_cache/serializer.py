"""Deterministic, canonical serialization of prompt layers.

The single rule this module exists to enforce: identical *content* must produce
byte-identical *output*, every time, in every process. That is the precondition
for any prompt cache - a provider reuses a prefix only when the bytes match
exactly, so a stray key reorder, a trailing space, or a non-deterministic dict
iteration silently defeats caching.

To guarantee it we:
  - serialize every payload as canonical JSON: keys sorted recursively, no
    incidental whitespace, real UTF-8 preserved (ensure_ascii=False);
  - normalize free text (the system prompt): unify newlines, strip trailing
    whitespace per line, drop a leading/trailing blank tail;
  - hash a section with SHA-256 so instrumentation can prove, call over call,
    that the cacheable prefix didn't move.

No timestamps, UUIDs, or wall-clock values ever enter this path - the whole
point is that the same logical prompt hashes the same tomorrow as today.
"""

import hashlib
import json
from typing import Any

from coding_agent.optimizations.prompt_cache.layers import LayerTier, PromptLayer


class PromptSerializer:
    """Turns PromptLayers into canonical bytes (and hashes of chosen sections)."""

    def canonical_json(self, payload: Any) -> str:
        """One canonical JSON string for any JSON-serializable payload.

        sort_keys makes dict order irrelevant; the compact separators strip the
        incidental spaces json.dumps adds by default; ensure_ascii=False keeps
        real UTF-8 rather than \\uXXXX escapes, so the bytes stay stable and
        compact regardless of the input's original key order.
        """
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def normalize_text(self, text: str) -> str:
        """Normalize free-form text so trivial whitespace never breaks a match."""
        unified = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.rstrip() for line in unified.split("\n")]
        return "\n".join(lines).strip()

    def serialize_layer(self, layer: PromptLayer) -> str:
        """One canonical block for a single layer: its name, then its payload."""
        if isinstance(layer.payload, str):
            body = self.normalize_text(layer.payload)
        else:
            body = self.canonical_json(layer.payload)
        return f"{layer.name}:{body}"

    def serialize(self, layers: list[PromptLayer]) -> str:
        """Canonical stream (as str) for an ordered list of layers.

        Layers are emitted in the order given; the builder is responsible for
        that order being stable -> semi-stable -> dynamic. Joining with a newline
        keeps each layer's bytes self-contained, so appending a later layer never
        disturbs an earlier one's bytes.
        """
        return "\n".join(self.serialize_layer(layer) for layer in layers)

    def serialize_stable(self, layers: list[PromptLayer]) -> str:
        """Canonical stream of only the STABLE layers (the cacheable prefix)."""
        return self.serialize(
            [layer for layer in layers if layer.tier == LayerTier.STABLE]
        )

    def digest(self, text: str) -> str:
        """SHA-256 hex of a canonical string - a stable fingerprint of content."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
