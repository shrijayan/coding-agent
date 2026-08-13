"""Deduplication: never resend identical content the model has already seen.

One of the five prompt-optimization techniques (alongside context pruning,
conversation summarization, tool filtering, and prompt compression). An
agent conversation naturally accumulates exact duplicates: the model
re-reads the same file across turns, re-runs the same command, or the user
pastes the same instructions twice. Every duplicate is billed again as
input tokens on every subsequent call - for bytes the model has already
seen verbatim.

This wrapper scans the outgoing messages on each send(), keeps the FIRST
occurrence of any sufficiently large text block intact, and replaces later
exact duplicates with a short, specific marker that points back to the
original: "[duplicate removed: identical to the earlier read_file result
above, 812 chars]". The model keeps one full copy in context; the marker
tells it exactly where.

Safety properties:
  - Only *exact* matches count (a plain string comparison, not similarity)
    - near-duplicates never qualify, so meaning is never changed.
  - Only blocks >= min_chars are considered; a short "ok" repeating is
    normal conversation, not waste worth a marker.
  - No message is ever removed and tool_use/tool_result pairing is never
    touched - only the *text inside* a duplicated part is replaced.
  - The latest message is never deduplicated against itself; the first
    occurrence always survives, wherever it is.

The conversation AgentLoop keeps is untouched - like every wrap_llm_client
optimization, only what gets sent per call changes. Savings are recorded
as deterministic character counts; the real token effect shows up in
/usage's provider-reported input tokens, never estimated here.
"""

from dataclasses import dataclass, field
from typing import Any

from coding_agent.config import Config
from coding_agent.llm.base import LLMClient, LLMResponse
from coding_agent.llm.messages import Message, TextPart, ToolResultPart
from coding_agent.optimizations.bundle import OptimizationBundle


@dataclass(frozen=True)
class DedupRecord:
    """One duplicate block replaced on one send()."""

    kind: str  # "tool_result" or "text"
    chars_removed: int


@dataclass
class DedupTracker:
    """Accumulates dedup records across a session, read by /dedup."""

    records: list[DedupRecord] = field(default_factory=list)
    total_sends: int = 0

    def record_send(self) -> None:
        self.total_sends += 1

    def record_duplicate(self, *, kind: str, chars_removed: int) -> None:
        self.records.append(DedupRecord(kind=kind, chars_removed=chars_removed))

    @property
    def total_duplicates(self) -> int:
        return len(self.records)

    @property
    def total_chars_removed(self) -> int:
        return sum(record.chars_removed for record in self.records)


class DeduplicationLLMClient(LLMClient):
    """Replaces later exact duplicates of large text blocks with a marker
    pointing at the surviving first occurrence, then delegates. Implements
    LLMClient so AgentLoop can't tell it apart from a plain client."""

    def __init__(
        self,
        *,
        inner: LLMClient,
        tracker: DedupTracker,
        min_chars: int,
    ) -> None:
        self._inner = inner
        self._tracker = tracker
        self._min_chars = min_chars

    def send(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        self._tracker.record_send()
        deduped = self._dedupe(messages)
        return self._inner.send(system=system, messages=deduped, tools=tools)

    def _dedupe(self, messages: list[Message]) -> list[Message]:
        seen: set[str] = set()
        result: list[Message] = []
        for message in messages:
            new_parts = []
            changed = False
            for part in message.parts:
                replaced = self._dedupe_part(part, seen)
                if replaced is not part:
                    changed = True
                new_parts.append(replaced)
            result.append(
                Message(role=message.role, parts=new_parts) if changed else message
            )
        return result

    def _dedupe_part(self, part: Any, seen: set[str]) -> Any:
        if isinstance(part, ToolResultPart):
            text, kind = part.output, "tool_result"
        elif isinstance(part, TextPart):
            text, kind = part.text, "text"
        else:
            return part

        if len(text) < self._min_chars:
            return part
        if text not in seen:
            seen.add(text)
            return part

        marker = (
            f"[duplicate removed: identical to an earlier {kind} above, "
            f"{len(text)} chars - the first copy is still in context]"
        )
        self._tracker.record_duplicate(
            kind=kind, chars_removed=len(text) - len(marker)
        )
        if isinstance(part, ToolResultPart):
            return ToolResultPart(
                tool_use_id=part.tool_use_id, output=marker, is_error=part.is_error
            )
        return TextPart(marker)


_last_tracker: DedupTracker | None = None


def get_tracker() -> DedupTracker:
    """Return the tracker from the most recent build() (creating one if the
    optimization hasn't been built yet, so callers never get None)."""
    global _last_tracker
    if _last_tracker is None:
        _last_tracker = DedupTracker()
    return _last_tracker


def build() -> OptimizationBundle:
    global _last_tracker
    config = Config.from_env()
    tracker = DedupTracker()
    _last_tracker = tracker

    def wrap(inner: LLMClient) -> LLMClient:
        return DeduplicationLLMClient(
            inner=inner, tracker=tracker, min_chars=config.dedup_min_chars
        )

    return OptimizationBundle(wrap_llm_client=wrap)
