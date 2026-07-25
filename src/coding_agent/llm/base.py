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


class LLMError(RuntimeError):
    """Raised when the model can't be reached or refuses a request.

    Covers things outside our control: a wrong/expired API key, no
    network connection, rate limits, or the provider's servers being
    down - as opposed to a bug in our own code. This is a recoverable
    error, the same category as a failed tool call: the CLI catches it,
    shows the user one clean line, and keeps the session running instead
    of crashing. Each LLMClient implementation is responsible for
    translating its provider's own exception types into this one, so
    callers never need to know which provider they're talking to.
    """


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

        Raises LLMError if the model can't be reached or rejects the
        request (bad key, rate limit, network issue, server error, ...).
        """
        raise NotImplementedError
