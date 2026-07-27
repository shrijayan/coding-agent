"""Tracks the running message history for one conversation.

Messages are stored in our own provider-agnostic format (see
llm/messages.py) because the model has no memory of its own - we resend
the whole history on every single turn, to whichever provider is
currently configured, and that provider's LLMClient translates this
neutral format into its own wire format right before sending it.
"""

from dataclasses import dataclass, field

from coding_agent.llm.messages import Message, Part, TextPart, ToolResultPart, ToolUsePart
from coding_agent.tools.base import ToolResult


@dataclass
class Conversation:
    """The list of messages exchanged with the model so far."""

    messages: list[Message] = field(default_factory=list)

    def add_user_text(self, text: str) -> None:
        self.messages.append(Message(role="user", parts=[TextPart(text)]))

    def add_assistant_turn(self, text: str, tool_calls: list[ToolUsePart]) -> None:
        """Record what the model just said and/or asked to run."""
        parts: list[Part] = []
        if text:
            parts.append(TextPart(text))
        parts.extend(tool_calls)
        self.messages.append(Message(role="assistant", parts=parts))

    def add_tool_results(self, results: list[tuple[str, ToolResult]]) -> None:
        """Record the outcome of every tool call from the last assistant turn.

        results: (tool_use_id, ToolResult) pairs, matching the tool calls
        the model just made, in the same order.
        """
        parts: list[Part] = [
            ToolResultPart(
                tool_use_id=tool_use_id,
                output=result.output,
                is_error=result.is_error,
            )
            for tool_use_id, result in results
        ]
        self.messages.append(Message(role="user", parts=parts))
