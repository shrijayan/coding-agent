"""What one enabled optimization changes about how the agent is built.

An optimization can touch the agent in three places, matching the three
kinds of extension points this project's abstractions naturally support:

- wrap_llm_client: wraps the LLMClient (already an interface) to add
  behavior around every model call - caching, model routing, inference
  parameters, cost/observability logging, ...
- history_policy: swaps in a different HistoryPolicy (see
  optimizations/history_policy.py) - conversation summarization, context
  window optimization, ...
- system_prompt_suffix: appends extra instructions to the system prompt
  - prompt optimization, output length/style control, ...
- extra_tools: registers additional Tool(s) the model can call - any
  optimization whose mechanism is "give the model a new capability it can
  invoke on demand" rather than passively changing an existing call, e.g.
  loading reference material only when the model asks for it.

Every field defaults to None ("no change from the base agent") - an
optimization only sets the field(s) relevant to what it actually does.
"""

from collections.abc import Callable
from dataclasses import dataclass

from coding_agent.llm.base import LLMClient
from coding_agent.optimizations.history_policy import HistoryPolicy
from coding_agent.tools.base import Tool


class ConflictingOptimizationsError(RuntimeError):
    """Raised when two enabled optimizations both try to own the same
    single-owner aspect of the agent (only one HistoryPolicy can be
    active at a time - if two enabled optimizations both set one, that's
    a real conflict to resolve deliberately, not silently pick a winner
    for)."""


@dataclass(frozen=True)
class OptimizationBundle:
    """The combined effect of every currently-enabled optimization."""

    history_policy: HistoryPolicy | None = None
    wrap_llm_client: Callable[[LLMClient], LLMClient] | None = None
    system_prompt_suffix: str | None = None
    extra_tools: list[Tool] | None = None

    def merged_with(self, other: "OptimizationBundle") -> "OptimizationBundle":
        """Combine this bundle with another enabled optimization's bundle.

        - wrap_llm_client: both compose (chained, this one's wrapper
          applied around the other's) - e.g. caching AND model routing
          enabled together both take effect.
        - system_prompt_suffix: both concatenate.
        - extra_tools: both concatenate - tools are additive, not a single-
          owner aspect like history_policy, so two optimizations each
          registering a tool is never a conflict (ToolRegistry itself still
          fails fast on an actual duplicate *name*).
        - history_policy: only one policy can decide what history looks
          like - if both set one, that's a conflict, raised loudly.
        """
        if self.history_policy is not None and other.history_policy is not None:
            raise ConflictingOptimizationsError(
                "Two enabled optimizations both try to control conversation "
                "history - only one history policy can be active at a time. "
                "Enable one of them, not both."
            )

        return OptimizationBundle(
            history_policy=self.history_policy or other.history_policy,
            wrap_llm_client=_compose(self.wrap_llm_client, other.wrap_llm_client),
            system_prompt_suffix=_concat(
                self.system_prompt_suffix, other.system_prompt_suffix
            ),
            extra_tools=_concat_tools(self.extra_tools, other.extra_tools),
        )


def _compose(
    outer: Callable[[LLMClient], LLMClient] | None,
    inner: Callable[[LLMClient], LLMClient] | None,
) -> Callable[[LLMClient], LLMClient] | None:
    if outer is None:
        return inner
    if inner is None:
        return outer
    return lambda client: outer(inner(client))


def _concat(first: str | None, second: str | None) -> str | None:
    parts = [part for part in (first, second) if part]
    return "\n\n".join(parts) or None


def _concat_tools(first: list[Tool] | None, second: list[Tool] | None) -> list[Tool] | None:
    if first is None and second is None:
        return None
    return [*(first or []), *(second or [])]
