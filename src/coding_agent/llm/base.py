"""The contract for talking to a large language model.

The agent loop depends on this abstract interface, not on Anthropic
directly (dependency inversion). Today there's one implementation,
AnthropicClient, but the loop has no idea that's the case - it just
calls .send(). That's what would let us add a second provider later,
or substitute a fake client in a test, without touching the loop.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    """One tool invocation the model is requesting."""

    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class LLMResponse:
    """The model's next move, normalized away from any provider's SDK types."""

    text: str
    tool_calls: list[ToolCall]
    raw_content: list[dict[str, Any]]
    stop_reason: str

    @property
    def wants_tool_use(self) -> bool:
        """True when the model is asking us to run tools before it continues."""
        return self.stop_reason == "tool_use"


class LLMClient(ABC):
    """Turns a conversation-so-far into the model's next response."""

    @abstractmethod
    def send(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Send the full conversation and tool list, get the next response.

        messages/raw_content use the wire format of the underlying provider
        (here, Anthropic's Messages API) since that's what needs to be
        replayed back on every turn - we don't invent our own format only
        to translate it back and forth for no benefit.
        """
        raise NotImplementedError
