"""Context window optimization: keep only what the current step actually
needs in context, instead of resending everything forever.

Two distinct mechanisms, both about relevance over compression - contrast
with conversation-summary, which compresses old turns into prose:

1. Pruning (ContextPruningPolicy, a HistoryPolicy): once a tool result
   falls outside the most recent `keep_recent_messages` window, and its
   output is bulky (over `min_chars_to_prune`), replace it with a short,
   specific placeholder - "[pruned: read_file output for 'x.py', 812
   chars]" - instead of resending it on every subsequent call. The tool
   call and its place in the conversation stay; only the (often large,
   often stale) output does not. Nothing here estimates tokens - the
   chars-removed figure is a deterministic fact about the text that was
   dropped, same rule cache-friendly's byte figures follow.

2. Skills, loaded on demand (extra_tools + system_prompt_suffix): see
   skills_library.py and tools/load_skill.py. The system prompt carries
   only a short menu (names + one-line descriptions); a skill's full
   guidance only enters context via a real load_skill() call.

Both mechanisms report into one shared ContextWindowTracker, read by
/context - one command for "what got left out and what got pulled in."
"""

from dataclasses import dataclass, field
from typing import Literal

from coding_agent.config import Config
from coding_agent.llm.messages import Message, Part, ToolResultPart, ToolUsePart
from coding_agent.optimizations.bundle import OptimizationBundle
from coding_agent.optimizations.history_policy import HistoryContext, HistoryPolicy
from coding_agent.optimizations.history_utils import safe_keep_from
from coding_agent.optimizations.skills_library import SkillsLibrary, load_skills_dir
from coding_agent.tools.load_skill import LoadSkillTool

_SKILLS_SUFFIX_TEMPLATE = """\
Skills menu (reference material you can load on demand - loading one you \
won't use just spends tokens for nothing, so only load a skill whose \
description actually matches what you're about to do):
{menu}
Call load_skill(name) with the exact name above to load a skill's full \
guidance before starting related work.\
"""

EventKind = Literal["prune", "skill_load"]


@dataclass(frozen=True)
class ContextWindowEvent:
    """One thing the context-window optimization did: pruned a stale tool
    output, or loaded a skill on demand."""

    kind: EventKind
    chars_removed: int = 0
    skill_name: str = ""


@dataclass
class ContextWindowTracker:
    """Accumulates context-window events across a session, read by /context."""

    events: list[ContextWindowEvent] = field(default_factory=list)

    def record_prune(self, chars_removed: int) -> None:
        self.events.append(ContextWindowEvent(kind="prune", chars_removed=chars_removed))

    def record_skill_load(self, skill_name: str) -> None:
        self.events.append(ContextWindowEvent(kind="skill_load", skill_name=skill_name))

    @property
    def total_prunes(self) -> int:
        return sum(1 for event in self.events if event.kind == "prune")

    @property
    def total_chars_pruned(self) -> int:
        return sum(event.chars_removed for event in self.events if event.kind == "prune")

    @property
    def skills_loaded(self) -> list[str]:
        return [event.skill_name for event in self.events if event.kind == "skill_load"]


@dataclass
class ContextPruningPolicy(HistoryPolicy):
    """Drops (doesn't compress) stale, bulky tool output from older history.

    keep_recent_messages: this many of the most recent messages are always
    sent verbatim - pruning only ever considers messages outside this window.
    min_chars_to_prune: a tool result's output shorter than this is left
    alone even outside the window (not worth replacing with a placeholder).
    """

    keep_recent_messages: int
    min_chars_to_prune: int
    tracker: ContextWindowTracker
    _recorded_prune_ids: set[str] = field(default_factory=set, init=False)
    """Every prepare() call re-derives pruning from AgentLoop's untouched,
    ever-growing conversation (the invariant every HistoryPolicy upholds -
    see history_policy.py), so the exact same old bulky output would
    otherwise get "pruned" and recorded again on every subsequent send()
    within the same session. Tracked here by tool_use_id so /context reports
    each real prune exactly once, the same way ConversationSummaryPolicy
    tracks `_summarized_through` to avoid reprocessing."""

    def prepare(self, messages: list[Message], context: HistoryContext) -> list[Message]:
        if len(messages) <= self.keep_recent_messages:
            return messages

        keep_from = safe_keep_from(messages, len(messages) - self.keep_recent_messages)
        tool_calls_by_id = _tool_calls_by_id(messages[:keep_from])

        pruned_prefix = [
            self._prune_message(message, tool_calls_by_id) for message in messages[:keep_from]
        ]
        return [*pruned_prefix, *messages[keep_from:]]

    def _prune_message(
        self, message: Message, tool_calls_by_id: dict[str, ToolUsePart]
    ) -> Message:
        new_parts: list[Part] = []
        changed = False
        for part in message.parts:
            if isinstance(part, ToolResultPart) and len(part.output) > self.min_chars_to_prune:
                new_parts.append(self._placeholder(part, tool_calls_by_id))
                changed = True
            else:
                new_parts.append(part)
        return Message(role=message.role, parts=new_parts) if changed else message

    def _placeholder(
        self, part: ToolResultPart, tool_calls_by_id: dict[str, ToolUsePart]
    ) -> ToolResultPart:
        call = tool_calls_by_id.get(part.tool_use_id)
        call_desc = f"{call.name} output" if call else "output"
        if call is not None and "path" in call.input:
            call_desc = f"{call.name} output for '{call.input['path']}'"
        chars_removed = len(part.output)
        if part.tool_use_id not in self._recorded_prune_ids:
            self._recorded_prune_ids.add(part.tool_use_id)
            self.tracker.record_prune(chars_removed)
        placeholder = (
            f"[pruned: {call_desc}, {chars_removed} chars - "
            f"call {call.name if call else 'the tool'} again if you need it]"
        )
        return ToolResultPart(
            tool_use_id=part.tool_use_id, output=placeholder, is_error=part.is_error
        )


def _tool_calls_by_id(messages: list[Message]) -> dict[str, ToolUsePart]:
    return {
        part.id: part
        for message in messages
        for part in message.parts
        if isinstance(part, ToolUsePart)
    }


_last_tracker: ContextWindowTracker | None = None


def get_tracker() -> ContextWindowTracker:
    """Return the tracker from the most recent build() (creating one if the
    optimization hasn't been built yet, so callers never get None)."""
    global _last_tracker
    if _last_tracker is None:
        _last_tracker = ContextWindowTracker()
    return _last_tracker


def _skills_menu_suffix(library: SkillsLibrary) -> str | None:
    if not library.skills:
        return None
    return _SKILLS_SUFFIX_TEMPLATE.format(menu=library.menu())


def build() -> OptimizationBundle:
    global _last_tracker
    config = Config.from_env()
    tracker = ContextWindowTracker()
    _last_tracker = tracker

    policy = ContextPruningPolicy(
        keep_recent_messages=config.context_prune_keep_recent_messages,
        min_chars_to_prune=config.context_prune_min_chars_to_prune,
        tracker=tracker,
    )

    if not config.context_window_skills_enabled:
        return OptimizationBundle(history_policy=policy)

    library = load_skills_dir()
    skill_tool = LoadSkillTool(library=library, on_load=tracker.record_skill_load)

    return OptimizationBundle(
        history_policy=policy,
        extra_tools=[skill_tool],
        system_prompt_suffix=_skills_menu_suffix(library),
    )
