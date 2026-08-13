"""Prompt compression: rewrite long instructions into shorter equivalents.

One of the five prompt-optimization techniques (alongside context pruning,
conversation summarization, tool filtering, and deduplication). The system
prompt and every tool description are resent on every single call - so a
tighter wording of the same instructions is a pure win that compounds with
volume and costs nothing at runtime.

The compression here is deliberately *hand-written and deterministic*, not
an LLM rewriting text on the fly: SYSTEM_PROMPT_COMPACT (system_prompt.py)
and the compact tool descriptions below were tightened by a human once,
reviewed to mean the same thing, and swapped in verbatim at the send
boundary. A runtime "compressor" model would cost tokens to save tokens
and could silently change meaning - this can't.

Two composition details that make this safe to stack:
  - The wrapper replaces only the exact SYSTEM_PROMPT substring inside the
    outgoing system string. Anything appended after it (e.g. the skills
    menu that --enable context-window adds via system_prompt_suffix)
    passes through untouched.
  - Tool descriptions are swapped by name; a tool with no compact variant
    (e.g. an extra tool from another optimization) keeps its original
    description. Schemas and names are never touched - only the prose.

Measured honestly: the tracker records the deterministic character counts
before/after each swap; the actual token effect shows up in /usage's real
input tokens, never estimated here.
"""

from dataclasses import dataclass, field
from typing import Any

from coding_agent.llm.base import LLMClient, LLMResponse
from coding_agent.llm.messages import Message
from coding_agent.optimizations.bundle import OptimizationBundle
from coding_agent.system_prompt import SYSTEM_PROMPT, SYSTEM_PROMPT_COMPACT

# Hand-tightened equivalents of the base tools' descriptions (tools/*.py),
# keyed by tool name - same meaning, fewer words. A name missing here means
# "leave that tool's description alone".
COMPACT_TOOL_DESCRIPTIONS: dict[str, str] = {
    "read_file": (
        "Read a text file's full contents. Do this before editing a file."
    ),
    "write_file": (
        "Create or fully overwrite a file with the given content. For "
        "partial changes use edit_file."
    ),
    "edit_file": (
        "Replace one exact, unique snippet in a file with new text. "
        "old_text must match the current content exactly - read the file "
        "first."
    ),
    "bash": (
        "Run a shell command; returns combined stdout/stderr. For tests, "
        "searches, installs, etc."
    ),
    "list_files": (
        "Recursively list files and directories under a path. Use to "
        "explore before reading."
    ),
}


@dataclass(frozen=True)
class CompressionRecord:
    """The deterministic size effect of one send()'s compression."""

    system_chars_before: int
    system_chars_after: int
    tool_chars_before: int
    tool_chars_after: int

    @property
    def chars_saved(self) -> int:
        return (self.system_chars_before - self.system_chars_after) + (
            self.tool_chars_before - self.tool_chars_after
        )


@dataclass
class CompressionTracker:
    """Accumulates compression records across a session, read by /compression."""

    records: list[CompressionRecord] = field(default_factory=list)

    def record(self, record: CompressionRecord) -> None:
        self.records.append(record)

    @property
    def total_sends(self) -> int:
        return len(self.records)

    @property
    def total_chars_saved(self) -> int:
        return sum(record.chars_saved for record in self.records)


class PromptCompressionLLMClient(LLMClient):
    """Swaps the verbose system prompt and tool descriptions for their
    hand-tightened equivalents on every send(), then delegates. Implements
    LLMClient so AgentLoop can't tell it apart from a plain client."""

    def __init__(
        self,
        *,
        inner: LLMClient,
        tracker: CompressionTracker,
        compact_system_prompt: str = SYSTEM_PROMPT_COMPACT,
        compact_tool_descriptions: dict[str, str] | None = None,
    ) -> None:
        self._inner = inner
        self._tracker = tracker
        self._compact_system = compact_system_prompt
        self._compact_descriptions = (
            compact_tool_descriptions
            if compact_tool_descriptions is not None
            else COMPACT_TOOL_DESCRIPTIONS
        )

    def send(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        # Substring replace, not wholesale: preserves any suffix another
        # optimization appended after the base prompt (e.g. a skills menu).
        compressed_system = system.replace(SYSTEM_PROMPT, self._compact_system)

        tool_chars_before = sum(len(t.get("description", "")) for t in tools)
        compressed_tools = [self._compress_tool(tool) for tool in tools]
        tool_chars_after = sum(
            len(t.get("description", "")) for t in compressed_tools
        )

        self._tracker.record(
            CompressionRecord(
                system_chars_before=len(system),
                system_chars_after=len(compressed_system),
                tool_chars_before=tool_chars_before,
                tool_chars_after=tool_chars_after,
            )
        )
        return self._inner.send(
            system=compressed_system, messages=messages, tools=compressed_tools
        )

    def _compress_tool(self, tool: dict[str, Any]) -> dict[str, Any]:
        compact = self._compact_descriptions.get(tool.get("name", ""))
        if compact is None:
            return tool
        return {**tool, "description": compact}


_last_tracker: CompressionTracker | None = None


def get_tracker() -> CompressionTracker:
    """Return the tracker from the most recent build() (creating one if the
    optimization hasn't been built yet, so callers never get None)."""
    global _last_tracker
    if _last_tracker is None:
        _last_tracker = CompressionTracker()
    return _last_tracker


def build() -> OptimizationBundle:
    global _last_tracker
    tracker = CompressionTracker()
    _last_tracker = tracker

    def wrap(inner: LLMClient) -> LLMClient:
        return PromptCompressionLLMClient(inner=inner, tracker=tracker)

    return OptimizationBundle(wrap_llm_client=wrap)
