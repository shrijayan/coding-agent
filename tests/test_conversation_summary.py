"""Tests for conversation summarization (conversation_summary.py).

The trigger is purely token-based: it fires when the previous send's
real input-token count (UsageTracker.last) exceeds the threshold.
Message count plays no part in the decision.
"""

from coding_agent.llm.base import LLMClient, LLMResponse
from coding_agent.llm.messages import Message, TextPart, ToolResultPart, ToolUsePart
from coding_agent.metrics.usage import Usage, UsageTracker
from coding_agent.optimizations.conversation_summary import (
    ConversationSummaryPolicy,
    ConversationSummaryTracker,
    InvalidSummaryConfigError,
)
from coding_agent.optimizations.history_policy import HistoryContext


class FakeClient(LLMClient):
    """Returns a canned summary and records what it was asked to send."""

    def __init__(self, summary_text: str = "Goal: write tests. Done: none.") -> None:
        self.summary_text = summary_text
        self.sent_messages: list[Message] = []

    def send(self, *, system: str, messages: list[Message], tools: list[dict]) -> LLMResponse:
        self.sent_messages = messages
        return LLMResponse(
            text=self.summary_text,
            tool_calls=[],
            wants_tool_use=False,
            usage=Usage(input_tokens=10, output_tokens=15),
            model="test-model",
        )


def _user(text: str) -> Message:
    return Message(role="user", parts=[TextPart(text)])


def _call_pair(output: str) -> list[Message]:
    return [
        Message(role="assistant", parts=[ToolUsePart(id="c1", name="bash", input={"cmd": "pytest"})]),
        Message(role="user", parts=[ToolResultPart(tool_use_id="c1", output=output, is_error=False)]),
    ]


def _context(tracker: UsageTracker, client: FakeClient) -> HistoryContext:
    return HistoryContext(llm_client=client, usage_tracker=tracker)


def _tracker_with_last(input_tokens: int) -> UsageTracker:
    tracker = UsageTracker()
    tracker.record_llm_call(Usage(input_tokens=input_tokens, output_tokens=100), "test-model")
    return tracker


# --- trigger -----------------------------------------------------------------


def test_no_previous_call_means_no_summarization() -> None:
    tracker = UsageTracker()  # never recorded a call -> last is None
    policy = ConversationSummaryPolicy(token_threshold=8000, keep_recent_messages=2)
    messages = [_user("hi"), *_call_pair("ok")]

    result = policy.prepare(messages, _context(tracker, FakeClient()))

    assert result == messages


def test_send_below_threshold_is_left_untouched() -> None:
    tracker = _tracker_with_last(input_tokens=5000)  # below 8000
    policy = ConversationSummaryPolicy(token_threshold=8000, keep_recent_messages=2)
    messages = [_user("hi"), *_call_pair("ok")]

    result = policy.prepare(messages, _context(tracker, FakeClient()))

    assert result == messages


def test_send_above_threshold_folds_old_messages_into_summary() -> None:
    tracker = _tracker_with_last(input_tokens=12000)  # above 8000
    client = FakeClient()
    policy = ConversationSummaryPolicy(token_threshold=8000, keep_recent_messages=2)
    messages = [_user("add tests"), *_call_pair("3 passed"), _user("next: the logger")]

    result = policy.prepare(messages, _context(tracker, client))

    summary_text = result[0].parts[0]
    assert isinstance(summary_text, TextPart)
    assert "Goal: write tests" in summary_text.text
    # Cut wanted messages[2:] (keep 2 recent) but that would split the
    # tool pair, so safe_keep_from nudged it to messages[1:].
    assert result[1:] == messages[1:]
    assert len(client.sent_messages) == 1  # only the oldest message got folded


def test_summarize_call_is_recorded_in_tracker() -> None:
    tracker = _tracker_with_last(input_tokens=12000)
    policy = ConversationSummaryPolicy(token_threshold=8000, keep_recent_messages=2)
    messages = [_user("add tests"), *_call_pair("3 passed"), _user("next")]

    calls_before = tracker.llm_calls
    policy.prepare(messages, _context(tracker, FakeClient()))

    assert tracker.llm_calls == calls_before + 1
    assert tracker.last is not None and tracker.last.input_tokens == 10


def test_running_summary_only_folds_new_messages() -> None:
    tracker = _tracker_with_last(input_tokens=12000)
    client = FakeClient()
    policy = ConversationSummaryPolicy(token_threshold=8000, keep_recent_messages=1)

    first = [_user("task one"), *_call_pair("1 passed"), _user("task two")]
    policy.prepare(first, _context(tracker, client))
    # Cut at messages[3:]: the tool pair sits fully before it, so it stays whole.
    assert len(client.sent_messages) == 3  # first summarize folded task one + pair
    assert policy._summarized_through == 3

    # The loop records the main send's usage after each turn - and that main
    # send is what the trigger looks at, not the summarize call itself.
    tracker.record_llm_call(Usage(input_tokens=12000, output_tokens=50), "test-model")

    # Next turn: new content arrived since the last fold; the summarize call
    # must NOT re-send what was already folded.
    second = [_user("task one"), *_call_pair("1 passed"), _user("task two"), *_call_pair("2 passed")]
    policy.prepare(second, _context(tracker, client))

    # Cut at messages[4:]: messages[3] (the second user turn) is what's new.
    # The summarize call gets the running summary as leading context + that
    # one new message - never the already-folded pair again.
    assert len(client.sent_messages) == 2
    assert policy._summarized_through == 4


def test_huge_first_turn_cannot_split_a_tool_pair() -> None:
    # A big tool result can cross the token threshold while the conversation
    # is still shorter than the verbatim window - folding then would split
    # the tool pair. The policy must decline until history is long enough.
    tracker = _tracker_with_last(input_tokens=20000)  # way above 8000
    policy = ConversationSummaryPolicy(token_threshold=8000, keep_recent_messages=4)
    messages = [_user("read the big file"), *_call_pair("x" * 5000)]

    result = policy.prepare(messages, _context(tracker, FakeClient()))

    assert result == messages


def test_summarize_event_is_recorded_with_real_usage() -> None:
    tracker = _tracker_with_last(input_tokens=12000)
    client = FakeClient()
    summary_tracker = ConversationSummaryTracker()
    policy = ConversationSummaryPolicy(
        token_threshold=8000, keep_recent_messages=2, tracker=summary_tracker
    )
    messages = [_user("add tests"), *_call_pair("3 passed"), _user("next")]

    policy.prepare(messages, _context(tracker, client))

    assert summary_tracker.total_summarizes == 1
    event = summary_tracker.last_summary
    assert event is not None
    assert event.folded_messages == 1
    assert event.summary == client.summary_text
    assert (event.input_tokens, event.output_tokens) == (10, 15)  # fake usage


def test_no_summarize_means_no_events() -> None:
    tracker = _tracker_with_last(input_tokens=5000)  # below threshold
    summary_tracker = ConversationSummaryTracker()
    policy = ConversationSummaryPolicy(
        token_threshold=8000, keep_recent_messages=2, tracker=summary_tracker
    )

    policy.prepare([_user("hi")], _context(tracker, FakeClient()))

    assert summary_tracker.total_summarizes == 0


# --- config validation -------------------------------------------------------


def test_token_threshold_must_be_positive() -> None:
    try:
        ConversationSummaryPolicy(token_threshold=0, keep_recent_messages=2)
    except InvalidSummaryConfigError:
        pass
    else:
        raise AssertionError("expected InvalidSummaryConfigError")


def test_keep_recent_must_be_at_least_one() -> None:
    try:
        ConversationSummaryPolicy(token_threshold=8000, keep_recent_messages=0)
    except InvalidSummaryConfigError:
        pass
    else:
        raise AssertionError("expected InvalidSummaryConfigError")
