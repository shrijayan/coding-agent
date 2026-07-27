"""The contract for talking to a large language model.

The agent loop depends on this abstract interface, not on any specific
provider (dependency inversion). There are two implementations today,
AnthropicClient and OpenRouterClient, but the loop has no idea that's
the case - it just calls .send(). That's what lets us add a third
provider later, or substitute a fake client in a test, without
touching the loop.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from coding_agent.llm.messages import Message, ToolUsePart


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
class LLMResponse:
    """The model's next move, normalized away from any provider's SDK types."""

    text: str
    tool_calls: list[ToolUsePart]
    wants_tool_use: bool
    """True when the model is asking us to run tools before it continues.

    Each provider signals this differently (Anthropic sets
    stop_reason="tool_use"; OpenAI-style APIs just include a non-empty
    tool_calls list) - that difference is resolved by the client, so
    everything downstream only ever sees this one plain boolean.
    """


class LLMClient(ABC):
    """Turns a conversation-so-far into the model's next response."""

    @abstractmethod
    def send(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Send the full conversation and tool list, get the next response.

        messages is our own provider-agnostic format (see llm/messages.py);
        translating it into the wire format a specific provider expects is
        this method's job. tools is a list of {name, description,
        input_schema} dicts - the same neutral shape ToolRegistry already
        produces, since that's already just plain JSON-schema.

        Raises LLMError if the model can't be reached or rejects the
        request (bad key, rate limit, network issue, server error, ...).
        """
        raise NotImplementedError
