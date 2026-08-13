"""Tests for tool filtering (tool_filtering.py).

Mirrors tests/test_loop_guard.py's style: a local FakeClient, hand-built
Message sequences (no subprocess, no HTTP).
"""

from typing import Any

from coding_agent.commands.tool_filter_command import ToolFilterCommand
from coding_agent.llm.base import LLMClient, LLMResponse
from coding_agent.llm.messages import Message, TextPart, ToolResultPart, ToolUsePart
from coding_agent.metrics.usage import Usage
from coding_agent.optimizations.tool_filtering import (
    ToolFilteringLLMClient,
    ToolFilterTracker,
)


class FakeClient(LLMClient):
    """Records the tools each send() actually exposed."""

    def __init__(self) -> None:
        self.sent_tools: list[list[dict[str, Any]]] = []

    def send(
        self, *, system: str, messages: list[Message], tools: list[dict[str, Any]]
    ) -> LLMResponse:
        self.sent_tools.append(tools)
        return LLMResponse(
            text="ok", tool_calls=[], wants_tool_use=False,
            usage=Usage(input_tokens=10, output_tokens=5), model="fake-model",
        )


def _tool(name: str) -> dict[str, Any]:
    return {"name": name, "description": f"{name} tool", "input_schema": {}}


ALL_TOOLS = [
    _tool("read_file"),
    _tool("write_file"),
    _tool("edit_file"),
    _tool("bash"),
    _tool("list_files"),
]


def _client() -> tuple[ToolFilteringLLMClient, FakeClient, ToolFilterTracker]:
    inner = FakeClient()
    tracker = ToolFilterTracker()
    return (
        ToolFilteringLLMClient(inner=inner, tracker=tracker),
        inner,
        tracker,
    )


def _user(text: str) -> Message:
    return Message(role="user", parts=[TextPart(text)])


def _sent_names(inner: FakeClient) -> set[str]:
    return {tool["name"] for tool in inner.sent_tools[-1]}


# --- Filtering ---------------------------------------------------------------


def test_read_only_request_withholds_action_tools() -> None:
    client, inner, tracker = _client()

    client.send(
        system="s",
        messages=[_user("Show me the contents of calculator.py")],
        tools=ALL_TOOLS,
    )

    assert _sent_names(inner) == {"read_file", "list_files"}
    assert tracker.records[-1].filtered_names == ("bash", "edit_file", "write_file")


def test_edit_request_keeps_edit_but_withholds_bash() -> None:
    client, inner, _ = _client()

    client.send(
        system="s",
        messages=[_user("Add a subtract function to calculator.py")],
        tools=ALL_TOOLS,
    )

    names = _sent_names(inner)
    assert "edit_file" in names
    assert "bash" not in names


def test_exploration_tools_are_never_withheld() -> None:
    client, inner, _ = _client()

    # A purely action-flavored request still keeps read_file/list_files -
    # the system prompt tells the model to explore before acting.
    client.send(
        system="s",
        messages=[_user("Fix the divide function")],
        tools=ALL_TOOLS,
    )

    names = _sent_names(inner)
    assert {"read_file", "list_files"} <= names


# --- Safety fallbacks ---------------------------------------------------------


def test_no_keyword_evidence_keeps_all_tools() -> None:
    client, inner, tracker = _client()

    client.send(
        system="s",
        messages=[_user("Why is the sky blue?")],
        tools=ALL_TOOLS,
    )

    assert inner.sent_tools[-1] == ALL_TOOLS
    assert tracker.records[-1].filtered_names == ()


def test_unknown_extra_tools_are_always_kept() -> None:
    client, inner, _ = _client()
    tools = [*ALL_TOOLS, _tool("load_skill")]

    client.send(
        system="s",
        messages=[_user("Show me the contents of calculator.py")],
        tools=tools,
    )

    assert "load_skill" in _sent_names(inner)


def test_tool_used_this_turn_stays_exposed_mid_loop() -> None:
    client, inner, _ = _client()

    # Read-only request, but the model already called bash this turn -
    # hiding it mid-loop would break the in-flight plan.
    messages = [
        _user("Show me the test results summary"),
        Message(
            role="assistant",
            parts=[ToolUsePart(id="c1", name="bash", input={"command": "pytest"})],
        ),
        Message(
            role="user",
            parts=[ToolResultPart(tool_use_id="c1", output="3 passed", is_error=False)],
        ),
    ]
    client.send(system="s", messages=messages, tools=ALL_TOOLS)

    assert "bash" in _sent_names(inner)


def test_tools_from_previous_turns_do_not_pin_exposure() -> None:
    client, inner, _ = _client()

    # bash was used in a PREVIOUS turn (before the latest user text), so a
    # new read-only request may still withhold it.
    messages = [
        _user("Run the tests"),
        Message(
            role="assistant",
            parts=[ToolUsePart(id="c1", name="bash", input={"command": "pytest"})],
        ),
        Message(
            role="user",
            parts=[ToolResultPart(tool_use_id="c1", output="3 passed", is_error=False)],
        ),
        _user("Show me the contents of calculator.py"),
    ]
    client.send(system="s", messages=messages, tools=ALL_TOOLS)

    assert "bash" not in _sent_names(inner)


def test_no_user_text_keeps_all_tools() -> None:
    client, inner, _ = _client()

    client.send(system="s", messages=[], tools=ALL_TOOLS)

    assert inner.sent_tools[-1] == ALL_TOOLS


# --- Tracker & command ---------------------------------------------------------


def test_tracker_counts_and_command_report() -> None:
    client, _, tracker = _client()

    client.send(
        system="s",
        messages=[_user("Show me the contents of calculator.py")],
        tools=ALL_TOOLS,
    )
    client.send(system="s", messages=[_user("Why is the sky blue?")], tools=ALL_TOOLS)

    assert tracker.total_sends == 2
    assert tracker.total_filtered == 3
    assert tracker.filtered_name_counts() == {
        "bash": 1, "edit_file": 1, "write_file": 1,
    }

    report = ToolFilterCommand(tracker=tracker).run()
    assert "Total sends        : 2" in report
    assert "bash x1" in report


def test_command_with_no_records_explains_itself() -> None:
    report = ToolFilterCommand(tracker=ToolFilterTracker()).run()
    assert "--enable tool-filtering" in report
