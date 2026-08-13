"""Tool filtering: expose only the tools relevant to the current request.

One of the five prompt-optimization techniques (alongside context pruning,
conversation summarization, prompt compression, and deduplication): every
tool definition sent to the model is prompt text the provider bills as
input tokens, on every single send. A request like "list the files you
created" doesn't need write_file/edit_file/bash riding along - so this
optimization filters the tool list per send, using free, local keyword
heuristics on the latest user message (the same "score locally, never
spend a model call deciding" stance as routing's difficulty scorer).

Safety rules, in priority order - filtering must never break the agent:
  1. Only the action tools (write_file, edit_file, bash) are ever
     candidates. read_file and list_files are always kept - the system
     prompt tells the model to explore before acting, so hiding them
     would fight the agent's own instructions. Unknown/extra tools (e.g.
     load_skill from --enable context-window) are always kept too - we
     can't reason about a tool we don't know.
  2. Any tool already used in the current turn's tool loop stays exposed -
     mid-loop, the model may legitimately call it again.
  3. If the latest message matches no keyword confidently, ALL tools are
     kept. When uncertain, spend the tokens rather than risk correctness.

Composition note: tool definitions live in the STABLE layer of
cache-friendly-prompts' construction - a filtered set that changes between
sends moves that stable-prefix hash. That's a real trade (fewer input
tokens now vs a byte-stable prefix for a cache); enabling both is allowed,
just measured honestly by /cache showing more than one distinct prefix.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from coding_agent.llm.base import LLMClient, LLMResponse
from coding_agent.llm.messages import Message, TextPart, ToolUsePart
from coding_agent.optimizations.bundle import OptimizationBundle

# The only tools this module will ever consider dropping, and the keyword
# evidence that marks each one relevant to a request. Matching is on word
# boundaries (so "prune" never matches "run"), and keywords err on the
# side of matching too often (keeping a tool) rather than too rarely.
_FILTERABLE_TOOL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "write_file": (
        "write", "create", "new file", "generate", "scaffold", "save",
        "make",
    ),
    "edit_file": (
        "edit", "change", "modify", "update", "fix", "rename", "refactor",
        "add", "remove", "replace", "delete", "insert", "append",
    ),
    "bash": (
        "run", "test", "tests", "pytest", "execute", "install", "command",
        "shell", "script", "verify", "git", "build",
    ),
}

# Evidence that a request is read/explore-only. These never mark a
# filterable tool relevant - they exist so a pure "show me X" request
# counts as understood (and can confidently withhold the action tools)
# instead of falling into the keep-everything fallback.
_READ_INTENT_KEYWORDS: tuple[str, ...] = (
    "read", "show", "list", "contents", "look", "open", "view", "inspect",
    "explain", "summarize", "summary", "describe", "files", "structure",
    "tree", "which", "where",
)


@dataclass(frozen=True)
class ToolFilterRecord:
    """What one send() exposed vs filtered."""

    tools_offered: int
    tools_exposed: int
    filtered_names: tuple[str, ...]


@dataclass
class ToolFilterTracker:
    """Accumulates tool-filter records across a session, read by /toolfilter."""

    records: list[ToolFilterRecord] = field(default_factory=list)

    def record(
        self, *, offered: int, exposed: int, filtered_names: tuple[str, ...]
    ) -> None:
        self.records.append(
            ToolFilterRecord(
                tools_offered=offered,
                tools_exposed=exposed,
                filtered_names=filtered_names,
            )
        )

    @property
    def total_sends(self) -> int:
        return len(self.records)

    @property
    def total_filtered(self) -> int:
        return sum(len(r.filtered_names) for r in self.records)

    def filtered_name_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.records:
            for name in record.filtered_names:
                counts[name] = counts.get(name, 0) + 1
        return counts


class ToolFilteringLLMClient(LLMClient):
    """Narrows the tool list per send() to what the request plausibly needs,
    then delegates. Implements LLMClient so AgentLoop can't tell it apart
    from a plain client - the same decorator shape as every other
    wrap_llm_client optimization."""

    def __init__(self, *, inner: LLMClient, tracker: ToolFilterTracker) -> None:
        self._inner = inner
        self._tracker = tracker

    def send(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        exposed = _relevant_tools(messages, tools)
        filtered = tuple(
            sorted({t["name"] for t in tools} - {t["name"] for t in exposed})
        )
        self._tracker.record(
            offered=len(tools), exposed=len(exposed), filtered_names=filtered
        )
        return self._inner.send(system=system, messages=messages, tools=exposed)


def _relevant_tools(
    messages: list[Message], tools: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The subset of tools worth sending for this request (original order
    preserved). Falls back to all tools whenever confidence is low."""
    request_text = _latest_user_text(messages)
    if not request_text:
        return tools

    matched = {
        name
        for name, keywords in _FILTERABLE_TOOL_KEYWORDS.items()
        if any(_word_match(keyword, request_text) for keyword in keywords)
    }
    read_intent = any(
        _word_match(keyword, request_text) for keyword in _READ_INTENT_KEYWORDS
    )
    if not matched and not read_intent:
        # No keyword evidence at all - keep everything rather than guess.
        return tools

    used_this_turn = _tools_used_since_latest_user_text(messages)
    return [
        tool
        for tool in tools
        if tool["name"] not in _FILTERABLE_TOOL_KEYWORDS  # not a candidate: keep
        or tool["name"] in matched
        or tool["name"] in used_this_turn
    ]


def _word_match(keyword: str, text: str) -> bool:
    return re.search(rf"\b{re.escape(keyword)}\b", text) is not None


def _latest_user_text_index(messages: list[Message]) -> int:
    """Index of the most recent user message that carries actual text.
    Tool-result turns also have role='user' but say nothing worth scoring,
    so we walk back to the last one that does. -1 if there is none."""
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.role == "user" and any(
            isinstance(part, TextPart) for part in message.parts
        ):
            return index
    return -1


def _latest_user_text(messages: list[Message]) -> str:
    index = _latest_user_text_index(messages)
    if index < 0:
        return ""
    return " ".join(
        part.text for part in messages[index].parts if isinstance(part, TextPart)
    ).lower()


def _tools_used_since_latest_user_text(messages: list[Message]) -> set[str]:
    """Tools the model called during the current turn's tool loop. Kept
    exposed no matter what the keywords say - hiding a tool mid-use is how
    filtering would break an in-flight plan."""
    start = _latest_user_text_index(messages) + 1
    return {
        part.name
        for message in messages[start:]
        for part in message.parts
        if isinstance(part, ToolUsePart)
    }


_last_tracker: ToolFilterTracker | None = None


def get_tracker() -> ToolFilterTracker:
    """Return the tracker from the most recent build() (creating one if the
    optimization hasn't been built yet, so callers never get None)."""
    global _last_tracker
    if _last_tracker is None:
        _last_tracker = ToolFilterTracker()
    return _last_tracker


def build() -> OptimizationBundle:
    global _last_tracker
    tracker = ToolFilterTracker()
    _last_tracker = tracker

    def wrap(inner: LLMClient) -> LLMClient:
        return ToolFilteringLLMClient(inner=inner, tracker=tracker)

    return OptimizationBundle(wrap_llm_client=wrap)
