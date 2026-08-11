"""Explicit prompt layers, categorized by how often they change.

The base agent hands the model three things every send(): a system string,
the conversation messages, and the tool definitions. This module re-expresses
that raw material as an ordered list of named PromptLayers, each tagged with a
LayerTier saying how volatile it is.

That categorization is the whole point of a cache-friendly builder: a provider
(or a future provider-specific adapter) can only reuse a prefix that is
byte-identical across calls, so the builder's job is to put everything that
rarely changes (STABLE) first, the occasionally-changing middle (SEMI_STABLE)
next, and the per-turn churn (DYNAMIC) last - never interleaved.

These types are provider-agnostic: they describe *what* a chunk of the prompt
is and *how stable* it is, never how any specific API serializes it.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

# Canonical layer names. Kept as constants so the builder, serializer, and
# tests all refer to the same identifiers instead of loose string literals.
LAYER_SYSTEM = "system_prompt"
LAYER_TOOLS = "tool_definitions"
LAYER_CONVERSATION_CONTEXT = "conversation_context"
LAYER_LATEST_TURN = "latest_turn"


class LayerTier(IntEnum):
    """How often a layer's content changes across consecutive sends.

    Ordered so a plain sort puts a cacheable prefix first: STABLE <
    SEMI_STABLE < DYNAMIC. A lower value means "changes less often", which
    means "safer to place early where a cache can reuse it".

    Per the brief's categories:
      STABLE      - system prompt, tool/MCP definitions, coding guidelines,
                    repository metadata.
      SEMI_STABLE - conversation summary, active files, current task context.
      DYNAMIC     - latest user message, terminal output, tool results, logs.
    """

    STABLE = 0
    SEMI_STABLE = 1
    DYNAMIC = 2


@dataclass(frozen=True)
class PromptLayer:
    """One named, self-contained slice of the prompt.

    `payload` is plain JSON-serializable data (str / dict / list), never a
    provider wire object - the PromptSerializer is what turns it into canonical
    bytes. Keeping the payload neutral is what lets the same layer feed both the
    outgoing request and the instrumentation hash.
    """

    name: str
    tier: LayerTier
    payload: Any


def is_stable_before_dynamic(layers: list[PromptLayer]) -> bool:
    """True if no layer is followed by a strictly more-stable one.

    This is the invariant the builder guarantees (stable first, dynamic last).
    Exposed as a pure predicate so it can be asserted in tests against a
    hand-built, deliberately out-of-order list - not just trusted implicitly.
    """
    tiers = [layer.tier for layer in layers]
    return tiers == sorted(tiers)
