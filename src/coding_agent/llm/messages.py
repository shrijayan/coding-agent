"""Provider-agnostic representation of a conversation.

Every LLM provider has its own wire format for a back-and-forth
conversation. For example: Anthropic nests a tool call inside the
assistant message's content blocks and tool results inside a user
message's content blocks; OpenAI-style APIs (which OpenRouter uses) put
tool calls in their own field and give each tool result its own
message with role="tool". Neither of those provider shapes belongs in
the rest of the app.

So conversation history is stored here, in one neutral shape, and each
LLMClient implementation (AnthropicClient, OpenRouterClient, ...) is
responsible for translating to/from its own provider's format right
before/after the API call. That translation logic belongs next to the
provider it's for - it's exactly what would need to change if a new
provider were added, and nowhere else should.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TextPart:
    """A plain text chunk of a message."""

    text: str


@dataclass(frozen=True)
class ToolUsePart:
    """A tool invocation: the model asking to run one tool with some input.

    Used both for a live request (LLMResponse.tool_calls, about to be
    run) and for a historical record of one already run, stored back
    into the conversation - it's the same fact either way.
    """

    id: str
    name: str
    input: dict


@dataclass(frozen=True)
class ToolResultPart:
    """The outcome of one tool call, to be sent back to the model."""

    tool_use_id: str
    output: str
    is_error: bool


Part = TextPart | ToolUsePart | ToolResultPart
Role = Literal["user", "assistant"]


@dataclass(frozen=True)
class Message:
    """One turn in the conversation: who said it, and what it contains."""

    role: Role
    parts: list[Part]
