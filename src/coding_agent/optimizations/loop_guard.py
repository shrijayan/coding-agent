"""Agent loop prevention: the code-side backstop for a stuck agent.

`system_prompt.py` already tells the model, in plain English, "do not repeat
the exact same call expecting a different result" - that's today's
*prompt-side* loop prevention, and it works most of the time. This
optimization is what happens when it doesn't: a wrap_llm_client decorator
that watches for the model repeating an identical *failing* tool call and
intervenes before the cost keeps climbing with zero progress.

Two thresholds, escalating:
  - nudge_after: once the same (tool name, input) has failed this many times
    in a row, inject one corrective note into the outgoing messages before
    the next real model call - a cheap nudge, still a real call.
  - halt_after: once it's failed this many times in a row, skip calling the
    model entirely and return a clean "loop detected, stopping" answer -
    the catastrophe cap. No API call happens, so the recorded usage is a
    true zero, not an estimate.

Detection only fires on repeated *failures* (ToolResultPart.is_error=True).
Repeating a successful call (e.g. re-reading the same file twice) is never
flagged - that's legitimate behavior, not a stuck agent.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from coding_agent.config import Config
from coding_agent.llm.base import LLMClient, LLMResponse
from coding_agent.llm.messages import Message, TextPart, ToolResultPart, ToolUsePart
from coding_agent.metrics.usage import Usage
from coding_agent.optimizations.bundle import OptimizationBundle

_NUDGE_TEXT = (
    "[loop-guard] You've called the same tool with the same input and gotten "
    "the same error more than once in a row. Stop repeating it - read the "
    "error carefully and try a fundamentally different approach, or explain "
    "the blocker to the user instead of retrying again."
)

_HALT_TEXT = (
    "Stopping: the same tool call failed with the same error too many times "
    "in a row (loop-guard tripped before spending more on repeats that "
    "weren't making progress). Here's what was stuck: {name}({input}) -> "
    "{error}"
)

Action = Literal["sent", "nudged", "halted"]


class InvalidLoopGuardConfigError(RuntimeError):
    """Raised when the nudge/halt thresholds don't make sense together."""


@dataclass(frozen=True)
class LoopGuardRecord:
    """What happened on one send() through the loop guard."""

    repeat_count: int
    action: Action


@dataclass
class LoopGuardTracker:
    """Accumulates loop-guard records across a session, read by /loopguard."""

    records: list[LoopGuardRecord] = field(default_factory=list)

    def record(self, repeat_count: int, action: Action) -> None:
        self.records.append(LoopGuardRecord(repeat_count=repeat_count, action=action))

    @property
    def total_sends(self) -> int:
        return len(self.records)

    @property
    def total_nudges(self) -> int:
        return sum(1 for r in self.records if r.action == "nudged")

    @property
    def total_halts(self) -> int:
        return sum(1 for r in self.records if r.action == "halted")

    @property
    def current_streak(self) -> int:
        return self.records[-1].repeat_count if self.records else 0


class LoopGuardLLMClient(LLMClient):
    """Detects a repeated, failing tool call in the tail of the conversation
    and nudges (still calls the model) or halts (doesn't) before it repeats
    again unchecked."""

    def __init__(
        self,
        *,
        inner: LLMClient,
        tracker: LoopGuardTracker,
        nudge_after: int,
        halt_after: int,
    ) -> None:
        self._inner = inner
        self._tracker = tracker
        self._nudge_after = nudge_after
        self._halt_after = halt_after

    def send(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        streak = _trailing_identical_failed_streak(messages)

        if streak >= self._halt_after:
            self._tracker.record(streak, "halted")
            return _halt_response(messages)

        messages_to_send = messages
        action: Action = "sent"
        if streak >= self._nudge_after:
            messages_to_send = [*messages, Message(role="user", parts=[TextPart(_NUDGE_TEXT)])]
            action = "nudged"

        response = self._inner.send(system=system, messages=messages_to_send, tools=tools)
        self._tracker.record(streak, action)
        return response


def _halt_response(messages: list[Message]) -> LLMResponse:
    name, tool_input, error = _last_failed_call(messages)
    text = _HALT_TEXT.format(name=name, input=tool_input, error=error)
    # No real API call happened, so zero usage is a true fact, not an
    # estimate - and model="" is the existing "no real model answered this"
    # convention (see LLMResponse.model / UsageCommand._by_model), which
    # /usage already folds into the configured model and skips once its
    # token delta is zero, so it neither crashes nor misprices a session.
    return LLMResponse(text=text, tool_calls=[], wants_tool_use=False, usage=Usage(), model="")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _extract_steps(messages: list[Message]) -> list[tuple[tuple[tuple[str, str], ...], bool]]:
    """Pair each assistant tool-use turn with its following tool-result turn.

    Returns one entry per step: a signature (sorted (name, canonical input)
    tuples, so a multi-call turn is order-independent) and whether every
    result in that step was an error.
    """
    steps: list[tuple[tuple[tuple[str, str], ...], bool]] = []
    i = 0
    while i < len(messages) - 1:
        current, following = messages[i], messages[i + 1]
        calls = [part for part in current.parts if isinstance(part, ToolUsePart)]
        if current.role == "assistant" and calls:
            results_by_id = {
                part.tool_use_id: part
                for part in following.parts
                if isinstance(part, ToolResultPart)
            }
            if results_by_id and all(call.id in results_by_id for call in calls):
                signature = tuple(
                    sorted((call.name, _canonical(call.input)) for call in calls)
                )
                all_errors = all(results_by_id[call.id].is_error for call in calls)
                steps.append((signature, all_errors))
                i += 2
                continue
        i += 1
    return steps


def _trailing_identical_failed_streak(messages: list[Message]) -> int:
    """How many consecutive steps, counting back from the end, are the exact
    same failing tool call(s) repeated. 0 if the most recent step succeeded,
    wasn't a tool call, or there's no history yet."""
    steps = _extract_steps(messages)
    streak = 0
    last_signature = None
    for signature, all_errors in reversed(steps):
        if not all_errors:
            break
        if last_signature is None or signature == last_signature:
            streak += 1
            last_signature = signature
        else:
            break
    return streak


def _last_failed_call(messages: list[Message]) -> tuple[str, dict, str]:
    """The most recent failing tool call's (name, input, error text), for the
    halt message. Falls back to placeholders if none is found (shouldn't
    happen when this is only called after a halt-triggering streak)."""
    for message in reversed(messages):
        for part in message.parts:
            if isinstance(part, ToolResultPart) and part.is_error:
                call = _matching_tool_use(messages, part.tool_use_id)
                if call is not None:
                    return call.name, call.input, part.output
    return "(unknown tool)", {}, "(unknown error)"


def _matching_tool_use(messages: list[Message], tool_use_id: str) -> ToolUsePart | None:
    for message in messages:
        for part in message.parts:
            if isinstance(part, ToolUsePart) and part.id == tool_use_id:
                return part
    return None


_last_tracker: LoopGuardTracker | None = None


def get_tracker() -> LoopGuardTracker:
    """Return the tracker from the most recent build() (creating one if the
    optimization hasn't been built yet, so callers never get None)."""
    global _last_tracker
    if _last_tracker is None:
        _last_tracker = LoopGuardTracker()
    return _last_tracker


def build() -> OptimizationBundle:
    global _last_tracker
    config = Config.from_env()
    nudge_after = config.loop_guard_nudge_after
    halt_after = config.loop_guard_halt_after
    if halt_after <= nudge_after:
        raise InvalidLoopGuardConfigError(
            "AGENT_LOOP_GUARD_HALT_AFTER "
            f"({halt_after}) must be greater than AGENT_LOOP_GUARD_NUDGE_AFTER "
            f"({nudge_after}), otherwise the guard would halt before it ever nudges."
        )

    tracker = LoopGuardTracker()
    _last_tracker = tracker

    def wrap(inner: LLMClient) -> LLMClient:
        return LoopGuardLLMClient(
            inner=inner, tracker=tracker, nudge_after=nudge_after, halt_after=halt_after
        )

    return OptimizationBundle(wrap_llm_client=wrap)
