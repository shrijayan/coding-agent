"""The post-generation quality gate: a deterministic check on cheap output.

This is the "cascade" half of the hybrid design. After a tier answers, we
run cheap, deterministic checks on its output and only escalate to the
next tier up if a check fails - so we pay for the expensive model only
when the cheaper one demonstrably got it wrong, not on every request.

Why this half matters more than it looks: the pre-generation router is a
*prior*, and a cheap one - it will sometimes send a genuinely hard
request to a weak tier. The gate is the safety net that catches those
misroutes after the fact. Every check added here widens the set of
pre-router mistakes the system can recover from.

Adapting the survey's generic gate to THIS agent: a tier's LLMResponse
here is usually tool calls plus prose, not a standalone Python file, so
"run ruff/pytest on the output" doesn't apply at the send() boundary -
those only make sense on files already written to disk later in the tool
loop, and are left as an optional, off-by-default extension.

The checks below are all deterministic, run in microseconds, and need no
model call. Each is a concrete "this tier got it wrong" signal:

  ast_valid=false        a ```python block doesn't parse
  unterminated_code_fence output was cut off mid-code-block
  empty_response          no text, no code, no tool calls
  refusal                 the model declined or professed ignorance
  placeholder_code        stub/TODO code instead of a real implementation
  missing_tool_arguments  a tool call omitted a required parameter

Every check is deliberately conservative: a false FAIL costs a real
escalation to a paid model, so these fire only on unambiguous evidence.
"""

import ast
import re
from dataclasses import dataclass, field
from typing import Any

from coding_agent.llm.base import LLMResponse

# Matches a fenced code block tagged as python (```python ... ``` or
# ```py ... ```), capturing the code inside. re.DOTALL so it spans lines.
_PYTHON_BLOCK = re.compile(r"```(?:python|py)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)

# Phrases that mean the model declined or didn't know. Small models fall
# back to these instead of attempting the task - a clear escalation signal.
# Kept narrow: "I can't" inside a longer correct answer is rare, whereas
# these lead-ins are what an actual refusal looks like.
_REFUSAL_PATTERNS = (
    r"\bi (?:can(?:'|no)?t|cannot|am unable to|'m unable to) (?:help|assist|do|complete|provide)",
    r"\bi (?:don'?t|do not) (?:know|have enough)",
    r"\bi'?m (?:not sure|unsure) (?:how|what|whether)",
    r"\bas an ai\b",
    r"\bunable to (?:determine|answer|help)",
)
_REFUSAL = re.compile("|".join(_REFUSAL_PATTERNS), re.IGNORECASE)

# Markers of stub code handed back instead of a real implementation.
_PLACEHOLDER = re.compile(
    r"#\s*(?:TODO|FIXME)\b|YOUR CODE HERE|implement (?:this|me)\b|rest of (?:the )?(?:code|implementation)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GateResult:
    """The outcome of the quality gate for one tier's response."""

    passed: bool
    ast_valid: bool
    failed_checks: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Compact reason string for the terminal status line."""
        if self.passed:
            return "quality gate PASS"
        return "quality gate FAIL (" + ", ".join(self.failed_checks) + ")"


def check(
    response: LLMResponse, tools: list[dict[str, Any]] | None = None
) -> GateResult:
    """Run the deterministic gate on one tier's response.

    `tools` is the tool list that was sent with the request. When given,
    the gate can verify the model's tool calls actually satisfy each
    tool's declared required parameters - a malformed tool call would
    otherwise fail later, deeper in the loop, after we'd already accepted
    the answer.
    """
    text = response.text
    code_blocks = _extract_python_blocks(text)

    failed_checks: list[str] = []
    ast_valid = True

    for block in code_blocks:
        if not _parses(block):
            ast_valid = False
            failed_checks.append("ast_valid=false")
            break

    if _has_unterminated_fence(text):
        failed_checks.append("unterminated_code_fence")

    if not text.strip() and not code_blocks and not response.tool_calls:
        failed_checks.append("empty_response")

    # A refusal only counts when the model didn't also do the work: if it
    # produced code or called a tool, hedging prose is harmless.
    if not code_blocks and not response.tool_calls and _REFUSAL.search(text):
        failed_checks.append("refusal")

    if any(_PLACEHOLDER.search(block) for block in code_blocks):
        failed_checks.append("placeholder_code")

    missing = _missing_tool_arguments(response, tools or [])
    if missing:
        failed_checks.append(f"missing_tool_arguments={missing}")

    return GateResult(
        passed=not failed_checks, ast_valid=ast_valid, failed_checks=failed_checks
    )


def _extract_python_blocks(text: str) -> list[str]:
    return [match.group(1) for match in _PYTHON_BLOCK.finditer(text)]


def _parses(code: str) -> bool:
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def _has_unterminated_fence(text: str) -> bool:
    """An odd number of ``` markers means a code block was never closed -
    reliable evidence the response was truncated mid-generation."""
    return text.count("```") % 2 == 1


def _missing_tool_arguments(
    response: LLMResponse, tools: list[dict[str, Any]]
) -> str | None:
    """Name the first required tool parameter a tool call left out.

    Returns "tool_name.param" for the first violation, or None if every
    tool call supplies everything its schema marks required.
    """
    schemas = {tool["name"]: tool.get("input_schema", {}) for tool in tools}
    for call in response.tool_calls:
        schema = schemas.get(call.name)
        if schema is None:
            continue  # Unknown tool - the registry surfaces that, not the gate.
        for required in schema.get("required", []):
            if required not in (call.input or {}):
                return f"{call.name}.{required}"
    return None
