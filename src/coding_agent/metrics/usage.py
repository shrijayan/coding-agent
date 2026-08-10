"""Tracks token usage across a session.

This is the foundation every optimization gets measured against: before
you can claim "this optimization saved 40% tokens," you need something
that's actually counting tokens in the first place.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Usage:
    """Token counts for one model call, or an accumulated total of many."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


@dataclass
class UsageTracker:
    """Accumulates usage and call counts across an entire session.

    One instance is created per agent session and injected into
    AgentLoop (constructor injection, same as every other dependency in
    this project) so both the loop and the /usage command can share the
    same running totals.
    """

    total: Usage = field(default_factory=Usage)
    user_messages: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    by_model: dict[str, Usage] = field(default_factory=dict)
    """Token usage per model that actually served calls - with routing
    enabled a session can span several models with different prices, so
    a single merged total can't be priced correctly on its own. Keyed by
    LLMResponse.model (a models.yaml catalog key); "" if a client didn't say."""
    calls_by_model: dict[str, int] = field(default_factory=dict)

    def record_user_message(self) -> None:
        self.user_messages += 1

    def record_llm_call(self, usage: Usage, model: str) -> None:
        self.llm_calls += 1
        self.total = self.total + usage
        self.by_model[model] = self.by_model.get(model, Usage()) + usage
        self.calls_by_model[model] = self.calls_by_model.get(model, 0) + 1

    def record_tool_call(self) -> None:
        self.tool_calls += 1
