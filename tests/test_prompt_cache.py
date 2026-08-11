"""Tests for the cache-friendly prompt construction pipeline.

These drive the builder, serializer, tracker, provider-adapter seam, and the
CacheFriendlyLLMClient wrapper directly with in-memory fakes - no subprocess, no
HTTP. The assertions focus on the two properties the whole feature exists to
guarantee: identical content -> byte-identical stable prefix (determinism), and
a growing conversation -> a stable, reusable prefix (cache-friendliness).
"""

from typing import Any

from coding_agent.commands.cache_command import PromptCacheCommand
from coding_agent.llm.base import LLMClient, LLMResponse
from coding_agent.llm.messages import Message, TextPart, ToolResultPart, ToolUsePart
from coding_agent.metrics.usage import Usage
from coding_agent.optimizations import cache_friendly
from coding_agent.optimizations.cache_friendly import CacheFriendlyLLMClient
from coding_agent.optimizations.prompt_cache.builder import PromptBuilder
from coding_agent.optimizations.prompt_cache.layers import (
    LayerTier,
    PromptLayer,
    is_stable_before_dynamic,
)
from coding_agent.optimizations.prompt_cache.metrics import PromptCacheTracker
from coding_agent.optimizations.prompt_cache.provider_adapter import (
    NoOpProviderCacheAdapter,
    PreparedRequest,
)
from coding_agent.optimizations.prompt_cache.serializer import PromptSerializer

SYSTEM = "You are a coding agent.\nBe concise."

TOOLS: list[dict[str, Any]] = [
    {
        "name": "read_file",
        "description": "Read a file.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
        },
    },
    {
        "name": "bash",
        "description": "Run a shell command.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
        },
    },
]


def _user(text: str) -> Message:
    return Message(role="user", parts=[TextPart(text)])


def _assistant(text: str) -> Message:
    return Message(role="assistant", parts=[TextPart(text)])


class FakeClient(LLMClient):
    """Records the last send() arguments and returns a canned response."""

    def __init__(self, input_tokens: int = 100, model: str = "fake-model") -> None:
        self.last_system: str | None = None
        self.last_messages: list[Message] | None = None
        self.last_tools: list[dict[str, Any]] | None = None
        self._input_tokens = input_tokens
        self._model = model

    def send(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        self.last_system = system
        self.last_messages = messages
        self.last_tools = tools
        return LLMResponse(
            text="ok",
            tool_calls=[],
            wants_tool_use=False,
            usage=Usage(input_tokens=self._input_tokens, output_tokens=5),
            model=self._model,
        )


# --- Determinism -----------------------------------------------------------


def test_stable_hash_is_identical_across_builders() -> None:
    a = PromptBuilder().build(system=SYSTEM, messages=[_user("hi")], tools=TOOLS)
    b = PromptBuilder().build(system=SYSTEM, messages=[_user("hi")], tools=TOOLS)
    assert a.stable_hash == b.stable_hash
    assert a.stable_serialized == b.stable_serialized


def test_tool_order_does_not_change_stable_prefix() -> None:
    forward = PromptBuilder().build(system=SYSTEM, messages=[_user("hi")], tools=TOOLS)
    reversed_tools = list(reversed(TOOLS))
    backward = PromptBuilder().build(
        system=SYSTEM, messages=[_user("hi")], tools=reversed_tools
    )
    assert forward.stable_hash == backward.stable_hash


def test_dict_key_order_does_not_change_stable_prefix() -> None:
    shuffled = [
        {
            "input_schema": {
                "properties": {"path": {"type": "string"}},
                "type": "object",
            },
            "description": "Read a file.",
            "name": "read_file",
        },
        {
            "input_schema": {
                "properties": {"command": {"type": "string"}},
                "type": "object",
            },
            "description": "Run a shell command.",
            "name": "bash",
        },
    ]
    baseline = PromptBuilder().build(system=SYSTEM, messages=[_user("hi")], tools=TOOLS)
    reshaped = PromptBuilder().build(
        system=SYSTEM, messages=[_user("hi")], tools=shuffled
    )
    assert baseline.stable_hash == reshaped.stable_hash


def test_forwarded_tools_are_sorted_by_name() -> None:
    built = PromptBuilder().build(system=SYSTEM, messages=[_user("hi")], tools=TOOLS)
    names = [tool["name"] for tool in built.tools]
    assert names == sorted(names)


def test_whitespace_only_differences_do_not_change_stable_hash() -> None:
    messy = "You are a coding agent.   \r\nBe concise.\n\n"
    clean = PromptBuilder().build(system=SYSTEM, messages=[_user("hi")], tools=TOOLS)
    normalized = PromptBuilder().build(system=messy, messages=[_user("hi")], tools=TOOLS)
    assert clean.stable_hash == normalized.stable_hash


def test_forwarded_system_is_normalized() -> None:
    built = PromptBuilder().build(
        system="line one   \r\n\n", messages=[_user("hi")], tools=TOOLS
    )
    assert built.system == "line one"


# --- Layering & ordering ---------------------------------------------------


def test_layers_are_stable_before_dynamic() -> None:
    built = PromptBuilder().build(
        system=SYSTEM,
        messages=[_user("first"), _assistant("reply"), _user("second")],
        tools=TOOLS,
    )
    assert is_stable_before_dynamic(built.layers)
    tiers = [layer.tier for layer in built.layers]
    assert LayerTier.STABLE in tiers
    assert LayerTier.DYNAMIC in tiers


def test_is_stable_before_dynamic_rejects_out_of_order() -> None:
    out_of_order = [
        PromptLayer("late", LayerTier.DYNAMIC, "x"),
        PromptLayer("early", LayerTier.STABLE, "y"),
    ]
    assert not is_stable_before_dynamic(out_of_order)


def test_stable_hash_unaffected_by_conversation_growth() -> None:
    """Growing the conversation must never move the cacheable stable prefix."""
    builder = PromptBuilder()
    short = builder.build(system=SYSTEM, messages=[_user("hi")], tools=TOOLS)
    long = builder.build(
        system=SYSTEM,
        messages=[_user("hi"), _assistant("hello"), _user("more")],
        tools=TOOLS,
    )
    assert short.stable_hash == long.stable_hash


def test_stable_prefix_excludes_dynamic_ids() -> None:
    """A tool_use id (dynamic, non-deterministic) must not leak into the prefix."""
    messages = [
        _user("run it"),
        Message(
            role="assistant",
            parts=[ToolUsePart(id="call_abc123", name="bash", input={"command": "ls"})],
        ),
        Message(
            role="user",
            parts=[ToolResultPart(tool_use_id="call_abc123", output="ok", is_error=False)],
        ),
    ]
    built = PromptBuilder().build(system=SYSTEM, messages=messages, tools=TOOLS)
    assert "call_abc123" not in built.stable_serialized


# --- Stable-section reuse (requirement 5) ----------------------------------


def test_stable_section_reused_across_sends() -> None:
    builder = PromptBuilder()
    builder.build(system=SYSTEM, messages=[_user("a")], tools=TOOLS)
    builder.build(system=SYSTEM, messages=[_user("a"), _assistant("b")], tools=TOOLS)
    builder.build(system=SYSTEM, messages=[_user("a")], tools=TOOLS)
    assert builder.stable_recomputes == 1


def test_stable_section_recomputed_when_system_changes() -> None:
    builder = PromptBuilder()
    builder.build(system=SYSTEM, messages=[_user("a")], tools=TOOLS)
    builder.build(system="A different system prompt.", messages=[_user("a")], tools=TOOLS)
    assert builder.stable_recomputes == 2


# --- Reuse & ratios --------------------------------------------------------


def test_cache_friendly_ratio_between_zero_and_one() -> None:
    built = PromptBuilder().build(system=SYSTEM, messages=[_user("hi")], tools=TOOLS)
    assert 0.0 < built.cache_friendly_ratio <= 1.0


def test_prefix_reuse_grows_as_conversation_extends() -> None:
    builder = PromptBuilder()
    tracker = PromptCacheTracker()

    first = builder.build(system=SYSTEM, messages=[_user("hi")], tools=TOOLS)
    tracker.record(built=first, input_tokens=100, model="m")

    second = builder.build(
        system=SYSTEM,
        messages=[_user("hi"), _assistant("hello"), _user("again")],
        tools=TOOLS,
    )
    tracker.record(built=second, input_tokens=140, model="m")

    assert tracker.records[0].reuse_pct == 0.0
    assert tracker.records[1].reuse_pct > 0.0
    # The stable prefix + the first message are re-sent verbatim, so a large
    # leading share of the second request is reusable.
    assert tracker.records[1].reuse_pct > built_stable_share(second)


def built_stable_share(built: Any) -> float:
    return built.stable_bytes / built.total_bytes


# --- Tracker aggregates ----------------------------------------------------


def test_tracker_reports_single_stable_hash_when_prefix_unchanged() -> None:
    builder = PromptBuilder()
    tracker = PromptCacheTracker()
    for i in range(3):
        built = builder.build(
            system=SYSTEM, messages=[_user(f"turn {i}")], tools=TOOLS
        )
        tracker.record(built=built, input_tokens=100, model="m")
    assert tracker.distinct_stable_hashes() == 1
    assert tracker.total_input_tokens() == 300


# --- Provider adapter seam -------------------------------------------------


def test_noop_adapter_passes_request_through_unchanged() -> None:
    built = PromptBuilder().build(system=SYSTEM, messages=[_user("hi")], tools=TOOLS)
    request = PreparedRequest(system="s", messages=[_user("hi")], tools=TOOLS)
    result = NoOpProviderCacheAdapter().apply(built, request)
    assert result is request


# --- Wrapper end-to-end ----------------------------------------------------


def test_wrapper_forwards_normalized_prompt_and_records_real_tokens() -> None:
    inner = FakeClient(input_tokens=123, model="fake-model")
    tracker = PromptCacheTracker()
    client = CacheFriendlyLLMClient(
        inner=inner, builder=PromptBuilder(), tracker=tracker
    )

    response = client.send(
        system="hi there   \n", messages=[_user("do it")], tools=list(reversed(TOOLS))
    )

    assert response.text == "ok"
    # Forwarded system is normalized and tools are sorted by name.
    assert inner.last_system == "hi there"
    assert inner.last_tools is not None
    assert [tool["name"] for tool in inner.last_tools] == sorted(
        tool["name"] for tool in TOOLS
    )
    # The recorded token count is the provider's real number, not an estimate.
    assert tracker.records[-1].input_tokens == 123


def test_build_returns_bundle_that_wraps_client() -> None:
    bundle = cache_friendly.build()
    assert bundle.wrap_llm_client is not None
    wrapped = bundle.wrap_llm_client(FakeClient())
    assert isinstance(wrapped, CacheFriendlyLLMClient)
    # get_tracker() returns the same tracker the wrapper records into.
    wrapped.send(system=SYSTEM, messages=[_user("hi")], tools=TOOLS)
    assert cache_friendly.get_tracker().total_sends >= 1


# --- Command ---------------------------------------------------------------


def test_cache_command_handles_empty_and_populated() -> None:
    tracker = PromptCacheTracker()
    command = PromptCacheCommand(tracker=tracker)
    assert "No prompts built yet" in command.run()

    built = PromptBuilder().build(system=SYSTEM, messages=[_user("hi")], tools=TOOLS)
    tracker.record(built=built, input_tokens=100, model="m")
    output = command.run()
    assert "Prompt cache metrics" in output
    assert "Stable prefix hash" in output


# --- Serializer ------------------------------------------------------------


def test_canonical_json_sorts_keys() -> None:
    serializer = PromptSerializer()
    assert serializer.canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_normalize_text_strips_trailing_whitespace_and_unifies_newlines() -> None:
    serializer = PromptSerializer()
    assert serializer.normalize_text("a  \r\nb\n\n") == "a\nb"
