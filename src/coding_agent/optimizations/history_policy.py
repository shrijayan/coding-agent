"""Controls what conversation history actually gets sent to the model.

Sending the full, unmodified history (DefaultHistoryPolicy) is today's
behavior - and it's just one HistoryPolicy implementation. Any
optimization that changes what context the model sees (conversation
summarization, context window optimization, ...) is a different
HistoryPolicy, swapped in via --enable, with zero change to AgentLoop.
"""

from abc import ABC, abstractmethod

from coding_agent.llm.messages import Message


class HistoryPolicy(ABC):
    """Decides what subset/transformation of history to send the model."""

    @abstractmethod
    def prepare(self, messages: list[Message]) -> list[Message]:
        """Return the messages to actually send for this call.

        Called right before every LLMClient.send(), given the full
        conversation so far (AgentLoop/Conversation still keep the
        complete, untouched history regardless of what this returns -
        only what gets sent to the model is affected, so nothing about
        past turns is ever lost from the record).
        """


class DefaultHistoryPolicy(HistoryPolicy):
    """Sends the full conversation history, unchanged - today's behavior."""

    def prepare(self, messages: list[Message]) -> list[Message]:
        return messages
