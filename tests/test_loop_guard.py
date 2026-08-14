"""Tests for agent loop prevention (loop_guard.py).

Mirrors tests/test_prompt_cache.py's style: a local FakeClient, hand-built
Message/ToolUsePart/ToolResultPart sequences (no subprocess, no HTTP).
"""

from typing import Any

from coding_agent.commands.loop_guard_command import LoopGuardCommand
from coding_agent.llm.base import LLMClient, LLMResponse
from coding_agent.llm.messages import Message, TextPart, ToolResultPart, ToolUsePart
from coding_agent.metrics.usage import Usage
from coding_agent.optimizations import loop_guard
from coding_agent.optimizations.loop_guard import (
    InvalidLoopGuardConfigError,
    LoopGuardLLMClient,
    LoopGuardTracker,
)


class FakeClient(LLMClient):
    """Records every send() and returns a canned response; never actually
    fails, so tests control failure purely through the messages they hand in."""

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


def _failed_call_pair(name: str = "edit_file", tool_input: dict | None = None) -> list[Message]:
    """One assistant tool-use turn + its failing tool-result turn."""
    tool_input = tool_input if tool_input is not None else {"path": "config.py"}
    return [
        Message(
            role="assistant",
            parts=[ToolUsePart(id="call_1", name=name, input=tool_input)],
        ),
        Message(
            role="user",
            parts=[ToolResultPart(tool_use_id="call_1", output="error: bad edit", is_error=True)],
        ),
    ]


def _ok_call_pair(name: str = "read_file", tool_input: dict | None = None) -> list[Message]:
    tool_input = tool_input if tool_input is not None else {"path": "config.py"}
    return [
        Message(role="assistant", parts=[ToolUsePart(id="call_1", name=name, input=tool_input)]),
        Message(
            role="user",
            parts=[ToolResultPart(tool_use_id="call_1", output="file contents", is_error=False)],
        ),
    ]


def _history(*pairs: list[Message]) -> list[Message]:
    messages: list[Message] = [Message(role="user", parts=[TextPart("do it")])]
    for pair in pairs:
        messages.extend(pair)
    return messages


# --- Streak detection & passthrough -----------------------------------------


def test_no_tool_history_passes_through_unchanged() -> None:
    inner = FakeClient()
    tracker = LoopGuardTracker()
    client = LoopGuardLLMClient(inner=inner, tracker=tracker, nudge_after=2, halt_after=4)

    messages = _history()  # just the user's first message, no tool calls yet
    client.send(system="s", messages=messages, tools=[])

    assert inner.sends[-1] == messages
    assert tracker.records[-1].action == "sent"
    assert tracker.records[-1].repeat_count == 0


def test_repeated_successful_calls_never_trigger_anything() -> None:
    inner = FakeClient()
    tracker = LoopGuardTracker()
    client = LoopGuardLLMClient(inner=inner, tracker=tracker, nudge_after=2, halt_after=4)

    messages = _history(_ok_call_pair(), _ok_call_pair(), _ok_call_pair(), _ok_call_pair())
    client.send(system="s", messages=messages, tools=[])

    assert inner.sends[-1] == messages
    assert tracker.records[-1].action == "sent"


def test_streak_below_nudge_threshold_passes_through() -> None:
    inner = FakeClient()
    tracker = LoopGuardTracker()
    client = LoopGuardLLMClient(inner=inner, tracker=tracker, nudge_after=2, halt_after=4)

    messages = _history(_failed_call_pair())  # 1 identical failure so far
    client.send(system="s", messages=messages, tools=[])

    assert inner.sends[-1] == messages
    assert tracker.records[-1].action == "sent"
    assert tracker.records[-1].repeat_count == 1


# --- Nudge -------------------------------------------------------------------


def test_streak_at_nudge_threshold_injects_note_and_still_calls_inner() -> None:
    inner = FakeClient()
    tracker = LoopGuardTracker()
    client = LoopGuardLLMClient(inner=inner, tracker=tracker, nudge_after=2, halt_after=4)

    messages = _history(_failed_call_pair(), _failed_call_pair())  # 2 identical failures
    response = client.send(system="s", messages=messages, tools=[])

    assert response.text == "ok"  # inner was actually called
    assert len(inner.sends[-1]) == len(messages) + 1
    assert isinstance(inner.sends[-1][-1].parts[0], TextPart)
    assert tracker.records[-1].action == "nudged"
    assert tracker.records[-1].repeat_count == 2


def test_different_failing_calls_do_not_count_as_a_streak() -> None:
    inner = FakeClient()
    tracker = LoopGuardTracker()
    client = LoopGuardLLMClient(inner=inner, tracker=tracker, nudge_after=2, halt_after=4)

    messages = _history(
        _failed_call_pair(tool_input={"path": "a.py"}),
        _failed_call_pair(tool_input={"path": "b.py"}),
    )
    client.send(system="s", messages=messages, tools=[])

    # The most recent failure still counts as a streak of 1 on its own, but a
    # *different* call before it must not extend that streak to 2.
    assert tracker.records[-1].action == "sent"
    assert tracker.records[-1].repeat_count == 1


# --- Halt --------------------------------------------------------------------


def test_streak_at_halt_threshold_skips_inner_and_returns_zero_usage() -> None:
    inner = FakeClient()
    tracker = LoopGuardTracker()
    client = LoopGuardLLMClient(inner=inner, tracker=tracker, nudge_after=2, halt_after=4)

    messages = _history(*([_failed_call_pair()] * 4))  # 4 identical failures
    response = client.send(system="s", messages=messages, tools=[])

    assert inner.sends == []  # inner never called
    assert response.usage == Usage()
    assert response.model == ""
    assert not response.wants_tool_use
    assert "edit_file" in response.text
    assert tracker.records[-1].action == "halted"


# --- build() -----------------------------------------------------------------


def _set_base_config_env(monkeypatch) -> None:
    """build() calls Config.from_env(), which needs the whole config, not
    just this optimization's two knobs - same as every other build()."""
    monkeypatch.setenv("AGENT_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "25")
    monkeypatch.setenv("AGENT_BASH_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("AGENT_SUMMARY_TOKEN_THRESHOLD", "8000")
    monkeypatch.setenv("AGENT_SUMMARY_KEEP_RECENT_MESSAGES", "4")
    monkeypatch.setenv("AGENT_CONTEXT_PRUNE_KEEP_RECENT_MESSAGES", "6")
    monkeypatch.setenv("AGENT_CONTEXT_PRUNE_MIN_CHARS_TO_PRUNE", "400")
    monkeypatch.setenv("AGENT_CONTEXT_WINDOW_SKILLS_ENABLED", "true")
    monkeypatch.setenv("AGENT_DEDUP_MIN_CHARS", "200")


def test_build_returns_bundle_that_wraps_client(monkeypatch) -> None:
    _set_base_config_env(monkeypatch)
    monkeypatch.setenv("AGENT_LOOP_GUARD_NUDGE_AFTER", "2")
    monkeypatch.setenv("AGENT_LOOP_GUARD_HALT_AFTER", "4")
    bundle = loop_guard.build()
    assert bundle.wrap_llm_client is not None
    wrapped = bundle.wrap_llm_client(FakeClient())
    assert isinstance(wrapped, LoopGuardLLMClient)
    wrapped.send(system="s", messages=_history(), tools=[])
    assert loop_guard.get_tracker().total_sends >= 1


def test_build_rejects_halt_at_or_below_nudge(monkeypatch) -> None:
    _set_base_config_env(monkeypatch)
    monkeypatch.setenv("AGENT_LOOP_GUARD_NUDGE_AFTER", "3")
    monkeypatch.setenv("AGENT_LOOP_GUARD_HALT_AFTER", "3")
    try:
        loop_guard.build()
        assert False, "expected InvalidLoopGuardConfigError"
    except InvalidLoopGuardConfigError:
        pass


# --- Command -----------------------------------------------------------------


def test_command_handles_empty_and_populated() -> None:
    tracker = LoopGuardTracker()
    command = LoopGuardCommand(tracker=tracker)
    assert "No sends yet" in command.run()

    tracker.record(2, "nudged")
    output = command.run()
    assert "Loop guard metrics" in output
    assert "Nudges issued    : 1" in output
