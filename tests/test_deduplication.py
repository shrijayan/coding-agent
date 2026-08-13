"""Tests for deduplication (deduplication.py).

Mirrors tests/test_loop_guard.py's style: a local FakeClient, hand-built
Message sequences (no subprocess, no HTTP).
"""

from typing import Any

from coding_agent.commands.dedup_command import DedupCommand
from coding_agent.llm.base import LLMClient, LLMResponse
from coding_agent.llm.messages import Message, TextPart, ToolResultPart, ToolUsePart
from coding_agent.metrics.usage import Usage
from coding_agent.optimizations.deduplication import (
    DeduplicationLLMClient,
    DedupTracker,
)


class FakeClient(LLMClient):
    """Records the messages each send() actually put on the wire."""

    def __init__(self) -> None:
        self.sends: list[list[Message]] = []

    def send(
        self, *, system: str, messages: list[Message], tools: list[dict[str, Any]]
    ) -> LLMResponse:
        self.sends.append(messages)
        return LLMResponse(
            text="ok", tool_calls=[], wants_tool_use=False,
            usage=Usage(input_tokens=10, output_tokens=5), model="fake-model",
        )


def _client(min_chars: int = 50) -> tuple[DeduplicationLLMClient, FakeClient, DedupTracker]:
    inner = FakeClient()
    tracker = DedupTracker()
    return (
        DeduplicationLLMClient(inner=inner, tracker=tracker, min_chars=min_chars),
        inner,
        tracker,
    )


FILE_CONTENT = "def add(a, b):\n    return a + b\n" * 5  # > 50 chars


def _read_pair(call_id: str, output: str = FILE_CONTENT) -> list[Message]:
    return [
        Message(
            role="assistant",
            parts=[ToolUsePart(id=call_id, name="read_file", input={"path": "calc.py"})],
        ),
        Message(
            role="user",
            parts=[ToolResultPart(tool_use_id=call_id, output=output, is_error=False)],
        ),
    ]


# --- Duplicate replacement -------------------------------------------------------


def test_second_identical_tool_result_becomes_marker_first_survives() -> None:
    client, inner, tracker = _client()
    messages = [
        Message(role="user", parts=[TextPart("read calc.py")]),
        *_read_pair("c1"),
        Message(role="user", parts=[TextPart("read it again")]),
        *_read_pair("c2"),
    ]

    client.send(system="s", messages=messages, tools=[])

    sent = inner.sends[-1]
    first = sent[2].parts[0]
    second = sent[5].parts[0]
    assert isinstance(first, ToolResultPart) and first.output == FILE_CONTENT
    assert isinstance(second, ToolResultPart)
    assert "duplicate removed" in second.output
    assert second.tool_use_id == "c2"  # pairing untouched
    assert tracker.total_duplicates == 1
    assert tracker.total_chars_removed > 0


def test_no_messages_are_ever_removed() -> None:
    client, inner, _ = _client()
    messages = [
        Message(role="user", parts=[TextPart("read calc.py")]),
        *_read_pair("c1"),
        *_read_pair("c2"),
    ]

    client.send(system="s", messages=messages, tools=[])

    assert len(inner.sends[-1]) == len(messages)


def test_duplicate_user_text_blocks_are_replaced_too() -> None:
    client, inner, tracker = _client()
    pasted = "Please follow these instructions exactly. " * 3
    messages = [
        Message(role="user", parts=[TextPart(pasted)]),
        Message(role="assistant", parts=[TextPart("done")]),
        Message(role="user", parts=[TextPart(pasted)]),
    ]

    client.send(system="s", messages=messages, tools=[])

    sent = inner.sends[-1]
    assert sent[0].parts[0].text == pasted
    assert "duplicate removed" in sent[2].parts[0].text
    assert tracker.records[-1].kind == "text"


# --- Safety rules -----------------------------------------------------------------


def test_short_blocks_below_min_chars_are_never_touched() -> None:
    client, inner, tracker = _client(min_chars=50)
    messages = [
        Message(role="user", parts=[TextPart("ok")]),
        Message(role="assistant", parts=[TextPart("done")]),
        Message(role="user", parts=[TextPart("ok")]),
    ]

    client.send(system="s", messages=messages, tools=[])

    assert inner.sends[-1] == messages
    assert tracker.total_duplicates == 0


def test_near_duplicates_are_not_replaced() -> None:
    client, inner, tracker = _client()
    messages = [
        *_read_pair("c1", FILE_CONTENT),
        *_read_pair("c2", FILE_CONTENT + "# changed"),
    ]

    client.send(system="s", messages=messages, tools=[])

    assert inner.sends[-1] == messages
    assert tracker.total_duplicates == 0


def test_error_flag_survives_replacement() -> None:
    client, inner, _ = _client()
    error_text = "Traceback (most recent call last): everything is broken " * 3
    messages = [
        Message(
            role="user",
            parts=[ToolResultPart(tool_use_id="c1", output=error_text, is_error=True)],
        ),
        Message(
            role="user",
            parts=[ToolResultPart(tool_use_id="c2", output=error_text, is_error=True)],
        ),
    ]

    client.send(system="s", messages=messages, tools=[])

    replaced = inner.sends[-1][1].parts[0]
    assert isinstance(replaced, ToolResultPart)
    assert replaced.is_error is True


def test_agent_loops_own_history_is_untouched() -> None:
    client, _, _ = _client()
    messages = [
        Message(role="user", parts=[TextPart("read calc.py")]),
        *_read_pair("c1"),
        *_read_pair("c2"),
    ]

    client.send(system="s", messages=messages, tools=[])

    # The caller's list still holds two full copies - only the sent copy changed.
    assert messages[2].parts[0].output == FILE_CONTENT
    assert messages[4].parts[0].output == FILE_CONTENT


# --- Tracker & command ---------------------------------------------------------------


def test_command_reports_counts_by_kind() -> None:
    client, _, tracker = _client()
    messages = [
        Message(role="user", parts=[TextPart("read calc.py")]),
        *_read_pair("c1"),
        *_read_pair("c2"),
    ]
    client.send(system="s", messages=messages, tools=[])

    report = DedupCommand(tracker=tracker).run()
    assert "Total sends        : 1" in report
    assert "Duplicates replaced: 1" in report
    assert "tool_result x1" in report


def test_command_with_no_sends_explains_itself() -> None:
    report = DedupCommand(tracker=DedupTracker()).run()
    assert "--enable deduplication" in report
