"""Assembles the base agent's raw send() inputs into ordered prompt layers.

The base agent calls LLMClient.send(system, messages, tools). PromptBuilder
re-expresses those three inputs as an ordered list of PromptLayers, tagged by
volatility, with one hard invariant guaranteed by construction: every STABLE
layer comes before every SEMI_STABLE layer, which comes before every DYNAMIC
layer. That ordering is what makes a cacheable prefix possible at all.

It also produces the *normalized* system string and *canonically ordered* tool
list to actually forward to the inner client, so the bytes that hit the wire are
as deterministic as the bytes we hash for instrumentation. Conversation messages
are passed through untouched and in order - reordering them would corrupt the
transcript (and the real provider-side cache prefix) for no benefit.

Requirement it satisfies directly: "Reuse serialized stable sections whenever
their underlying content has not changed instead of regenerating them." The
stable section (system prompt + tool definitions) is identical on every send of
a session, so PromptBuilder memoizes it and only re-normalizes/re-sorts/re-hashes
when the raw system or tools actually differ from the last call.
"""

from dataclasses import dataclass
from typing import Any

from coding_agent.llm.messages import (
    Message,
    Part,
    TextPart,
    ToolResultPart,
    ToolUsePart,
)
from coding_agent.optimizations.prompt_cache.layers import (
    LAYER_CONVERSATION_CONTEXT,
    LAYER_LATEST_TURN,
    LAYER_SYSTEM,
    LAYER_TOOLS,
    LayerTier,
    PromptLayer,
)
from coding_agent.optimizations.prompt_cache.serializer import PromptSerializer


@dataclass(frozen=True)
class BuiltPrompt:
    """The deterministic, layered result of one PromptBuilder.build() call.

    Carries both what to *forward* (normalized system, canonical tools, the
    untouched messages) and what to *measure* (the canonical stream, the stable
    prefix's hash and size, and per-tier byte sizes). The stable-boundary
    metadata is also exactly what a future provider-specific adapter needs to
    place a cache breakpoint - without the core builder knowing that provider.
    """

    layers: list[PromptLayer]
    system: str
    tools: list[dict[str, Any]]
    messages: list[Message]
    canonical: str
    stable_serialized: str
    stable_hash: str
    stable_bytes: int
    semi_stable_bytes: int
    dynamic_bytes: int
    total_bytes: int

    @property
    def cache_friendly_ratio(self) -> float:
        """Stable share of the whole prompt: the structural cache-friendly floor.

        This is a byte ratio, not a token estimate - deterministic and provider
        independent, so it never pretends to be a real token count (those come
        only from the provider's usage response).
        """
        return self.stable_bytes / self.total_bytes if self.total_bytes else 0.0


@dataclass(frozen=True)
class _StableSection:
    """Memoized stable prefix, reused across sends until its inputs change."""

    system: str
    tools: list[dict[str, Any]]
    normalized_system: str
    canonical_tools: list[dict[str, Any]]
    layers: list[PromptLayer]
    serialized: str
    hash: str


class PromptBuilder:
    """Builds a deterministic, layered BuiltPrompt from raw send() inputs."""

    def __init__(self, serializer: PromptSerializer | None = None) -> None:
        self._serializer = serializer or PromptSerializer()
        self._stable_memo: _StableSection | None = None
        self.stable_recomputes = 0
        """How many times the stable section was actually re-serialized. Stays
        at 1 for a whole session when system + tools never change - visible
        proof the reuse-instead-of-regenerate path is working."""

    def build(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
    ) -> BuiltPrompt:
        stable = self._stable_section(system, tools)

        context_messages = list(messages[:-1])
        latest_messages = list(messages[-1:])

        layers = list(stable.layers)
        semi_serialized = ""
        dynamic_serialized = ""

        if context_messages:
            semi_layer = PromptLayer(
                name=LAYER_CONVERSATION_CONTEXT,
                tier=LayerTier.SEMI_STABLE,
                payload=_messages_payload(context_messages),
            )
            layers.append(semi_layer)
            semi_serialized = self._serializer.serialize_layer(semi_layer)

        if latest_messages:
            dynamic_layer = PromptLayer(
                name=LAYER_LATEST_TURN,
                tier=LayerTier.DYNAMIC,
                payload=_messages_payload(latest_messages),
            )
            layers.append(dynamic_layer)
            dynamic_serialized = self._serializer.serialize_layer(dynamic_layer)

        # Stable sort by tier makes the stable-before-dynamic invariant hold by
        # construction rather than by luck; within a tier, insertion order wins.
        layers.sort(key=lambda layer: layer.tier)

        canonical = self._canonical_stream(stable.serialized, messages)

        return BuiltPrompt(
            layers=layers,
            system=stable.normalized_system,
            tools=stable.canonical_tools,
            messages=messages,
            canonical=canonical,
            stable_serialized=stable.serialized,
            stable_hash=stable.hash,
            stable_bytes=_byte_len(stable.serialized),
            semi_stable_bytes=_byte_len(semi_serialized),
            dynamic_bytes=_byte_len(dynamic_serialized),
            total_bytes=_byte_len(canonical),
        )

    def _stable_section(
        self, system: str, tools: list[dict[str, Any]]
    ) -> _StableSection:
        """Return the stable prefix, recomputing only when its inputs changed.

        Equality (not identity) is the test: ToolRegistry hands back a fresh list
        each send, but with identical content, so a value compare correctly hits
        the memo and skips re-normalizing, re-sorting, and re-hashing.
        """
        memo = self._stable_memo
        if memo is not None and memo.system == system and memo.tools == tools:
            return memo

        normalized_system = self._serializer.normalize_text(system)
        canonical_tools = _canonical_tools(tools)
        layers = [
            PromptLayer(LAYER_SYSTEM, LayerTier.STABLE, normalized_system),
            PromptLayer(LAYER_TOOLS, LayerTier.STABLE, canonical_tools),
        ]
        serialized = self._serializer.serialize(layers)
        section = _StableSection(
            system=system,
            tools=tools,
            normalized_system=normalized_system,
            canonical_tools=canonical_tools,
            layers=layers,
            serialized=serialized,
            hash=self._serializer.digest(serialized),
        )
        self._stable_memo = section
        self.stable_recomputes += 1
        return section

    def _canonical_stream(self, stable_serialized: str, messages: list[Message]) -> str:
        """The byte stream used to measure prefix reuse across consecutive sends.

        Deliberately append-only: the stable prefix, then one canonical block per
        message in order. Because a new turn only appends messages, this call's
        stream extends the previous call's as a leading prefix - which is exactly
        what a provider cache reuses, so the longest-common-prefix measured on it
        reflects real cacheable overlap (not an artifact of layer boundaries).
        """
        parts = [stable_serialized]
        parts.extend(
            self._serializer.canonical_json(_message_payload(message))
            for message in messages
        )
        return "\n".join(parts)


def _canonical_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tools in a deterministic order with recursively key-sorted schemas.

    Tool order and JSON-schema key order carry no meaning to any provider, but
    they do change the bytes - so sorting both makes the stable prefix identical
    no matter what order tools were registered or schemas were authored in.
    """
    ordered = sorted(tools, key=lambda tool: str(tool.get("name", "")))
    return [_canonicalize(tool) for tool in ordered]


def _canonicalize(value: Any) -> Any:
    """Recursively sort dict keys so nested schemas serialize deterministically."""
    if isinstance(value, dict):
        return {key: _canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    return value


def _messages_payload(messages: list[Message]) -> list[dict[str, Any]]:
    return [_message_payload(message) for message in messages]


def _message_payload(message: Message) -> dict[str, Any]:
    """A neutral, JSON-serializable view of a Message for canonical hashing."""
    return {
        "role": message.role,
        "parts": [_part_payload(part) for part in message.parts],
    }


def _part_payload(part: Part) -> dict[str, Any]:
    if isinstance(part, TextPart):
        return {"type": "text", "text": part.text}
    if isinstance(part, ToolUsePart):
        return {
            "type": "tool_use",
            "id": part.id,
            "name": part.name,
            "input": part.input,
        }
    if isinstance(part, ToolResultPart):
        return {
            "type": "tool_result",
            "tool_use_id": part.tool_use_id,
            "output": part.output,
            "is_error": part.is_error,
        }
    raise TypeError(f"Unknown message part type: {type(part).__name__}")


def _byte_len(text: str) -> int:
    return len(text.encode("utf-8"))
