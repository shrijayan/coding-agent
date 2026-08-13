"""Tests for prompt compression (prompt_compression.py).

Mirrors tests/test_loop_guard.py's style: a local FakeClient, hand-built
inputs (no subprocess, no HTTP).
"""

from typing import Any

from coding_agent.commands.compression_command import CompressionCommand
from coding_agent.llm.base import LLMClient, LLMResponse
from coding_agent.llm.messages import Message, TextPart
from coding_agent.metrics.usage import Usage
from coding_agent.optimizations.prompt_compression import (
    COMPACT_TOOL_DESCRIPTIONS,
    CompressionTracker,
    PromptCompressionLLMClient,
)
from coding_agent.system_prompt import SYSTEM_PROMPT, SYSTEM_PROMPT_COMPACT


class FakeClient(LLMClient):
    """Records what each send() actually put on the wire."""

    def __init__(self) -> None:
        self.sent_systems: list[str] = []
        self.sent_tools: list[list[dict[str, Any]]] = []

    def send(
        self, *, system: str, messages: list[Message], tools: list[dict[str, Any]]
    ) -> LLMResponse:
        self.sent_systems.append(system)
        self.sent_tools.append(tools)
        return LLMResponse(
            text="ok", tool_calls=[], wants_tool_use=False,
            usage=Usage(input_tokens=10, output_tokens=5), model="fake-model",
        )


def _client() -> tuple[PromptCompressionLLMClient, FakeClient, CompressionTracker]:
    inner = FakeClient()
    tracker = CompressionTracker()
    return (
        PromptCompressionLLMClient(inner=inner, tracker=tracker),
        inner,
        tracker,
    )


MESSAGES = [Message(role="user", parts=[TextPart("hi")])]


# --- System prompt -------------------------------------------------------------


def test_replaces_base_system_prompt_with_compact_variant() -> None:
    client, inner, _ = _client()

    client.send(system=SYSTEM_PROMPT, messages=MESSAGES, tools=[])

    assert inner.sent_systems[-1] == SYSTEM_PROMPT_COMPACT
    assert len(SYSTEM_PROMPT_COMPACT) < len(SYSTEM_PROMPT)


def test_preserves_suffix_appended_after_base_prompt() -> None:
    client, inner, _ = _client()
    suffix = "\n\nSkills menu:\n- pytest-conventions: how tests are written"

    client.send(system=SYSTEM_PROMPT + suffix, messages=MESSAGES, tools=[])

    assert inner.sent_systems[-1] == SYSTEM_PROMPT_COMPACT + suffix


def test_unrecognized_system_prompt_passes_through_unchanged() -> None:
    client, inner, _ = _client()

    client.send(system="Reply with the single word: ok", messages=MESSAGES, tools=[])

    assert inner.sent_systems[-1] == "Reply with the single word: ok"


# --- Tool descriptions -----------------------------------------------------------


def test_swaps_known_tool_descriptions_only() -> None:
    client, inner, _ = _client()
    tools = [
        {"name": "read_file", "description": "a long verbose description " * 5,
         "input_schema": {"type": "object"}},
        {"name": "load_skill", "description": "extra tool from another optimization",
         "input_schema": {"type": "object"}},
    ]

    client.send(system=SYSTEM_PROMPT, messages=MESSAGES, tools=tools)

    sent = {tool["name"]: tool for tool in inner.sent_tools[-1]}
    assert sent["read_file"]["description"] == COMPACT_TOOL_DESCRIPTIONS["read_file"]
    assert sent["load_skill"]["description"] == "extra tool from another optimization"
    # Names and schemas are never touched - only the prose.
    assert sent["read_file"]["input_schema"] == {"type": "object"}


def test_original_tool_dicts_are_not_mutated() -> None:
    client, _, _ = _client()
    original = {"name": "bash", "description": "long original words",
                "input_schema": {}}

    client.send(system=SYSTEM_PROMPT, messages=MESSAGES, tools=[original])

    assert original["description"] == "long original words"


# --- Tracker & command ------------------------------------------------------------


def test_tracker_records_deterministic_char_savings() -> None:
    client, _, tracker = _client()
    tools = [{"name": "bash", "description": "x" * 500, "input_schema": {}}]

    client.send(system=SYSTEM_PROMPT, messages=MESSAGES, tools=tools)

    record = tracker.records[-1]
    assert record.system_chars_before == len(SYSTEM_PROMPT)
    assert record.system_chars_after == len(SYSTEM_PROMPT_COMPACT)
    assert record.tool_chars_before == 500
    assert record.tool_chars_after == len(COMPACT_TOOL_DESCRIPTIONS["bash"])
    assert record.chars_saved > 0
    assert tracker.total_chars_saved == record.chars_saved


def test_command_reports_latest_and_total() -> None:
    client, _, tracker = _client()
    client.send(system=SYSTEM_PROMPT, messages=MESSAGES, tools=[])
    client.send(system=SYSTEM_PROMPT, messages=MESSAGES, tools=[])

    report = CompressionCommand(tracker=tracker).run()
    assert "Total sends        : 2" in report
    assert "System prompt" in report


def test_command_with_no_records_explains_itself() -> None:
    report = CompressionCommand(tracker=CompressionTracker()).run()
    assert "--enable prompt-compression" in report
