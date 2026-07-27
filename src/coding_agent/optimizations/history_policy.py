"""Controls what conversation history actually gets sent to the model.

Sending the full, unmodified history (DefaultHistoryPolicy) is today's
behavior - and it's just one HistoryPolicy implementation. Any
optimization that changes what context the model sees (conversation
summarization, context window optimization, ...) is a different
HistoryPolicy, swapped in via --enable, with zero change to AgentLoop.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from coding_agent.llm.base import LLMClient
from coding_agent.llm.messages import Message
from coding_agent.metrics.usage import UsageTracker


@dataclass(frozen=True)
class HistoryContext:
    """Everything a HistoryPolicy might need beyond the message list itself.

    A policy that only trims/reorders messages needs nothing here.
    A policy that needs to *call the model itself* (e.g. to generate a
    summary) needs llm_client - reusing AgentLoop's own client rather
    than constructing a second one, so it automatically respects
    whatever provider/wrapping (e.g. a caching decorator from another
    enabled optimization) is already configured. Any such call must be
    recorded via usage_tracker - it's a real API call and must show up
    in /usage and the benchmark report, not be hidden overhead.
    """

    llm_client: LLMClient
    usage_tracker: UsageTracker


class HistoryPolicy(ABC):
    """Decides what subset/transformation of history to send the model."""

    @abstractmethod
    def prepare(self, messages: list[Message], context: HistoryContext) -> list[Message]:
        """Return the messages to actually send for this call.

        Called right before every LLMClient.send(), given the full
        conversation so far (AgentLoop/Conversation still keep the
        complete, untouched history regardless of what this returns -
        only what gets sent to the model is affected, so nothing about
        past turns is ever lost from the record).
        """


class DefaultHistoryPolicy(HistoryPolicy):
    """Sends the full conversation history, unchanged - today's behavior."""

    def prepare(self, messages: list[Message], context: HistoryContext) -> list[Message]:
        return messages
