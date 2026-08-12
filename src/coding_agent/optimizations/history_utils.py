"""Shared helpers for HistoryPolicy implementations that cut the message
history at some point (conversation summarization, context-window pruning).

A cut point can never fall between a tool_use message and its matching
tool_result message - if it did, whichever side lost its half would
reference a tool call that doesn't exist from that side's perspective, and
the provider's API rejects that outright. This was originally written for
ConversationSummaryPolicy; ContextPruningPolicy needs the exact same
invariant, so it lives here instead of being duplicated.
"""

from coding_agent.llm.messages import Message, Part, ToolUsePart


def safe_keep_from(messages: list[Message], desired_keep_from: int) -> int:
    """Nudge the cut point earlier if needed so it never separates a
    tool_use message from its matching tool_result message."""
    keep_from = desired_keep_from
    while keep_from > 0 and _ends_with_unresolved_tool_use(messages[:keep_from]):
        keep_from -= 1
    return keep_from


def _ends_with_unresolved_tool_use(messages: list[Message]) -> bool:
    if not messages:
        return False
    last = messages[-1]
    return last.role == "assistant" and any(_is_tool_use(part) for part in last.parts)


def _is_tool_use(part: Part) -> bool:
    return isinstance(part, ToolUsePart)
