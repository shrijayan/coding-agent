"""Conversation summarization: the reference optimization implementation.

Once the last send's real input-token count (from the provider's own
response) passes a threshold, the oldest messages get compacted into one
short, model-generated summary, and only the most recent few messages
are still sent verbatim. This is the first real entry in
AVAILABLE_OPTIMIZATIONS - see AGENTS.md's "How to add a new
optimization" for the general pattern this follows.

The trigger is token-based, not message-count-based, on purpose: cost is
driven by how big the send is, and a "yes" message and a 900-line file
dump are both "one message" but 5 and 20,000 tokens. Firing on the
provider-reported input_tokens of the previous call means the decision
is made on real numbers, never an estimate.

Three things worth understanding before copying this pattern:

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

2. The summary itself must stay short. Output tokens are billed at
   several times the rate of input tokens on most models, and every
   future send re-carries the summary - so a summary that reads like a
   detailed transcript gets *regenerated and rebilled* that many times
   over, which can cost more than the raw messages it replaced.
   The win only shows up when the summary is a short list of hard facts,
   not prose: see `_SUMMARY_SYSTEM_PROMPT`.

3. A cut point can never fall between a tool_use message and its
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
    "Compress the conversation so far into the shortest possible record, not "
    "a transcript. Output a terse bulleted list, a handful of bullets at "
    "most - never prose, never restate reasoning or dialogue. Keep only hard "
    "facts the agent needs to act correctly later: the user's goal, in one "
    "bullet; the *exact* file paths created/read/edited and *exact* commands "
    "run, each as its own short bullet naming it plainly (never 'created "
    "some files' - name them); and, only if something is still unresolved, "
    "one bullet for that. Every word here gets resent and rebilled on every "
    "future turn, so omit anything that doesn't change what the agent does "
    "next - no narration, no explanations, no restating what a file's "
    "contents are once its path has been named."
)

_SUMMARY_NOTE_PREFIX = (
    "[This is an automatically generated summary of earlier conversation "
    "history, not something the user said.]\n"
)


class InvalidSummaryConfigError(RuntimeError):
    """Raised when the summarization thresholds don't make sense together."""


@dataclass(frozen=True)
class ConversationSummaryEvent:
    """One summarization that actually fired: what was folded and what the
    summarize call cost (real provider-reported tokens)."""

    folded_messages: int
    summary: str
    input_tokens: int
    output_tokens: int


@dataclass
class ConversationSummaryTracker:
    """Accumulates summarize events across a session so the notebook and a
    future /summary command can show what actually happened - same shape as
    ContextWindowTracker / ToolFilterTracker."""

    events: list[ConversationSummaryEvent] = field(default_factory=list)

    def record_summarize(
        self,
        folded_messages: int,
        summary: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        self.events.append(
            ConversationSummaryEvent(
                folded_messages=folded_messages,
                summary=summary,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        )

    @property
    def total_summarizes(self) -> int:
        return len(self.events)

    @property
    def last_summary(self) -> ConversationSummaryEvent | None:
        return self.events[-1] if self.events else None


@dataclass
class ConversationSummaryPolicy(HistoryPolicy):
    """Compacts old messages into a running summary once sends get big.

    token_threshold: summarize once the previous send's real input-token
    count (from the provider's response, via UsageTracker.last) exceeds
    this many tokens. Purely token-based - message count plays no part.
    keep_recent_messages: this many of the most recent messages are
    always sent verbatim, never folded into the summary.
    tracker: records every summarize event (folded count, summary text,
    real token usage) so the notebook / a command can show what happened.
    """

    token_threshold: int
    keep_recent_messages: int
    tracker: ConversationSummaryTracker = field(default_factory=ConversationSummaryTracker)
    _summary: str | None = field(default=None, init=False)
    _summarized_through: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.token_threshold <= 0:
            raise InvalidSummaryConfigError(
                f"token_threshold must be positive, got: {self.token_threshold}"
            )
        if self.keep_recent_messages < 1:
            raise InvalidSummaryConfigError(
                f"keep_recent_messages must be at least 1, got: {self.keep_recent_messages}"
            )

    def prepare(self, messages: list[Message], context: HistoryContext) -> list[Message]:
        if len(messages) <= self.keep_recent_messages:
            # Nothing would be left outside the verbatim window. Guarding
            # here matters with the token trigger: one huge turn (e.g. a
            # big tool result) can cross the token threshold before the
            # conversation is long enough to fold safely.
            return messages
        last = context.usage_tracker.last
        if last is None or last.input_tokens <= self.token_threshold:
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
        self.tracker.record_summarize(
            folded_messages=len(messages_to_send),
            summary=response.text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        return response.text


_last_tracker: ConversationSummaryTracker | None = None


def get_tracker() -> ConversationSummaryTracker:
    """Return the tracker from the most recent build() (creating one if the
    optimization hasn't been built yet, so callers never get None)."""
    global _last_tracker
    if _last_tracker is None:
        _last_tracker = ConversationSummaryTracker()
    return _last_tracker


def build() -> OptimizationBundle:
    global _last_tracker
    config = Config.from_env()
    tracker = ConversationSummaryTracker()
    _last_tracker = tracker
    policy = ConversationSummaryPolicy(
        token_threshold=config.summary_token_threshold,
        keep_recent_messages=config.summary_keep_recent_messages,
        tracker=tracker,
    )
    return OptimizationBundle(history_policy=policy)
