"""Tracks the running message history for one conversation.

Messages are stored in the exact shape the Anthropic Messages API expects,
because that's what gets replayed back to it on every single turn - the
model has no memory of its own, so we resend the whole history each time.
"""

from dataclasses import dataclass, field
from typing import Any

from coding_agent.tools.base import ToolResult


@dataclass
class Conversation:
    """The list of messages exchanged with the model so far."""

    messages: list[dict[str, Any]] = field(default_factory=list)

    def add_user_text(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def add_assistant_response(self, raw_content: list[dict[str, Any]]) -> None:
        self.messages.append({"role": "assistant", "content": raw_content})

    def add_tool_results(self, results: list[tuple[str, ToolResult]]) -> None:
        """Record the outcome of every tool call from the last assistant turn.

        results: (tool_use_id, ToolResult) pairs, matching the tool_use
        blocks the model just sent, in the same order.
        """
        content = [
            {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": result.output,
                "is_error": result.is_error,
            }
            for tool_use_id, result in results
        ]
        self.messages.append({"role": "user", "content": content})
