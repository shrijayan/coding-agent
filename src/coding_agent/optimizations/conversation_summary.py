"""Conversation summarization: the reference optimization implementation.

Once conversation history grows past a threshold, the oldest messages
get compacted into one short, model-generated summary, and only the
most recent few messages are still sent verbatim. This is the first
real entry in AVAILABLE_OPTIMIZATIONS - see AGENTS.md's "How to add a
new optimization" for the general pattern this follows.

Two things worth understanding before copying this pattern:

1. Summarizing is itself a real model call, so it costs real tokens.
   To keep that cost bounded as a conversation gets very long, this
   keeps a running cached summary and only folds in messages that
   arrived *since* the last summarization, rather than re-summarizing
   the entire history from scratch every time (which would make the
   summarization step itself grow without bound - defeating the point).
   That means this policy is stateful and must NOT be reused across
   otherwise-independent conversations (see the benchmark runner, which
   already resolves a fresh OptimizationBundle per task for exactly
   this reason).

2. A cut point can never fall between a tool_use message and its
   matching tool_result message - if it did, whichever side lost its
   half would reference a tool call that doesn't exist from that side's
   perspective, and the provider's API rejects that outright. See
   `optimizations/history_utils.py`'s `safe_keep_from`, shared with
   ContextPruningPolicy (optimizations/context_window.py) for the same reason.
"""

from dataclasses import dataclass, field

from coding_agent.config import Config
from coding_agent.llm.messages import Message, TextPart
from coding_agent.optimizations.bundle import OptimizationBundle
from coding_agent.optimizations.history_policy import HistoryContext, HistoryPolicy
from coding_agent.optimizations.history_utils import safe_keep_from

_SUMMARY_SYSTEM_PROMPT = (
    "Summarize the conversation so far, concisely but precisely: what the "
    "user is trying to accomplish, and everything already done - list the "
    "*exact* file paths created/read/edited and the *exact* commands run, "
    "with their outcomes. Do not generalize or omit specific names (e.g. "
    "say 'created one.txt, two.txt, and three.txt', never just 'created "
    "some files') - whichever specifics you drop here are permanently "
    "gone from the conversation. Also note anything still unresolved."
)

_SUMMARY_NOTE_PREFIX = (
    "[This is an automatically generated summary of earlier conversation "
    "history, not something the user said.]\n"
)


class InvalidSummaryConfigError(RuntimeError):
    """Raised when the summarization thresholds don't make sense together."""


@dataclass
class ConversationSummaryPolicy(HistoryPolicy):
    """Compacts old messages into a running summary once history grows.

    threshold_messages: only start summarizing once history exceeds this
    many messages.
    keep_recent_messages: this many of the most recent messages are
    always sent verbatim, never folded into the summary.
    """

    threshold_messages: int
    keep_recent_messages: int
    _summary: str | None = field(default=None, init=False)
    _summarized_through: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.keep_recent_messages >= self.threshold_messages:
            raise InvalidSummaryConfigError(
                "AGENT_SUMMARY_KEEP_RECENT_MESSAGES "
                f"({self.keep_recent_messages}) must be smaller than "
                f"AGENT_SUMMARY_THRESHOLD_MESSAGES ({self.threshold_messages}), "
                "otherwise there would be nothing left to summarize."
            )

    def prepare(self, messages: list[Message], context: HistoryContext) -> list[Message]:
        if len(messages) <= self.threshold_messages:
            return messages

        keep_from = safe_keep_from(messages, len(messages) - self.keep_recent_messages)
        new_messages = messages[self._summarized_through : keep_from]

        if new_messages:
            self._summary = self._summarize(new_messages, context)
            self._summarized_through = keep_from

        summary_message = Message(
            role="user",
            parts=[TextPart(f"{_SUMMARY_NOTE_PREFIX}{self._summary}")],
        )
        return [summary_message, *messages[keep_from:]]

    def _summarize(self, new_messages: list[Message], context: HistoryContext) -> str:
        messages_to_send = list(new_messages)
        if self._summary is not None:
            # Fold the previous summary in as leading context, so this
            # call only has to process what's new - see module docstring.
            messages_to_send = [
                Message(role="user", parts=[TextPart(f"Summary so far:\n{self._summary}")]),
                *messages_to_send,
            ]

        response = context.llm_client.send(
            system=_SUMMARY_SYSTEM_PROMPT,
            messages=messages_to_send,
            tools=[],
        )
        # A real API call - must be counted, not hidden overhead that
        # would make this optimization look cheaper than it actually is.
        context.usage_tracker.record_llm_call(response.usage, response.model)
        return response.text


def build() -> OptimizationBundle:
    config = Config.from_env()
    policy = ConversationSummaryPolicy(
        threshold_messages=config.summary_threshold_messages,
        keep_recent_messages=config.summary_keep_recent_messages,
    )
    return OptimizationBundle(history_policy=policy)
