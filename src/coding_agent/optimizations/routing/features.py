"""Free, local feature extraction for the difficulty router.

This is the "pre-generation" half of the survey's difficulty-aware
routing: cheap signals computed from the request text alone, with no
model call and no network.

The signals come in two deliberate flavors, and the split matters:

- **Vocabulary-independent** (word count, long-word density, clause
  complexity, code fences). These generalize to requests using words
  nobody put on a list, which is the common case in real use.
- **Vocabulary-dependent** (the hard/easy keyword lists below). These are
  a precision boost for phrasings we can anticipate.

The first version of this scorer leaned entirely on the keyword lists,
which had a structural bug: a genuinely hard request phrased with
unlisted vocabulary could never score above the routing threshold, so it
always went to the cheap tier no matter how hard it was. The
vocabulary-independent signals exist specifically so difficulty is still
detectable when every keyword misses - see router.py, where they now
carry enough weight to cross the threshold on their own.

Extraction happens at the LLMClient.send() boundary, so the input is a
list of neutral Messages (llm/messages.py), not a single user string.
Mid tool-loop, the most recent message is often a tool result with no
user text; we score the most recent *user-authored* text so every send()
within one user turn scores the same underlying request and routes
consistently.
"""

import re
from dataclasses import dataclass

from coding_agent.llm.messages import Message, TextPart, ToolResultPart

# A word this long or longer is treated as "technical". Design/architecture
# language ("backpressure", "idempotent", "orchestration", "serialization")
# skews long, while everyday instruction language ("add", "fix", "print",
# "file", "name") skews short. This is the main signal that generalizes to
# vocabulary no keyword list anticipated.
LONG_WORD_CHARS = 9

# Words that chain independent requirements together. A request with many
# of these is asking for several things at once, which is hard regardless
# of the subject matter.
CLAUSE_CONNECTORS = frozenset(
    {"and", "also", "plus", "while", "whereas", "but", "then", "besides", "unless"}
)

_SENTENCE_END = re.compile(r"[.!?]+")
_WORD = re.compile(r"[a-z0-9][a-z0-9_\-']*")

# Words that tend to signal a genuinely hard, design-level request.
HARD_KEYWORDS = frozenset(
    {
        "design",
        "architect",
        "architecture",
        "scale",
        "scalable",
        "distributed",
        "concurrency",
        "concurrent",
        "parallel",
        "race",
        "deadlock",
        "thread",
        "async",
        "trade-off",
        "tradeoff",
        "trade-offs",
        "tradeoffs",
        "optimize",
        "optimization",
        "security",
        "secure",
        "multi-tenant",
        "multitenant",
        "redis",
        "kafka",
        "failure-mode",
        "failure",
        "refactor",
        "migrate",
        "migration",
        "throughput",
        "latency",
        "algorithm",
        "complexity",
        "benchmark",
        "consistency",
        "transaction",
        "idempotent",
    }
)

# Words that tend to signal a small, self-contained request.
EASY_KEYWORDS = frozenset(
    {
        "reverse",
        "reverses",
        "print",
        "hello",
        "rename",
        "typo",
        "format",
        "capitalize",
        "uppercase",
        "lowercase",
        "simple",
        "comment",
        "greet",
        "increment",
        "concatenate",
        "palindrome",
    }
)


@dataclass(frozen=True)
class Features:
    """The cheap, local signals the router scores a request on."""

    word_count: int
    char_count: int
    code_fence_count: int
    hard_keyword_hits: int
    easy_keyword_hits: int
    long_word_ratio: float
    """Fraction of words at least LONG_WORD_CHARS long - a proxy for
    technical density that needs no keyword list, so it still fires on
    vocabulary the lists never anticipated."""
    clause_count: int
    """Sentences plus clause connectors: how many separate things this
    request is chaining together."""
    has_tool_results: bool
    """True when this send() is mid tool-loop (the latest message carries
    tool results). Recorded for observability; the router scores the
    original user text so routing stays consistent across a turn."""


def extract_features(messages: list[Message]) -> Features:
    """Compute difficulty features for the current outgoing request."""
    text = _latest_user_text(messages)
    lowered = text.lower()
    words = _WORD.findall(lowered)

    return Features(
        word_count=len(words),
        char_count=len(text),
        code_fence_count=lowered.count("```"),
        hard_keyword_hits=_count_keyword_hits(words, HARD_KEYWORDS),
        easy_keyword_hits=_count_keyword_hits(words, EASY_KEYWORDS),
        long_word_ratio=_long_word_ratio(words),
        clause_count=_clause_count(lowered, words),
        has_tool_results=_has_tool_results(messages),
    )


def _long_word_ratio(words: list[str]) -> float:
    if not words:
        return 0.0
    long_words = sum(1 for word in words if len(word) >= LONG_WORD_CHARS)
    return long_words / len(words)


def _clause_count(lowered: str, words: list[str]) -> int:
    """How many distinct requirements this request chains together.

    Counted as sentences plus clause connectors. A one-line request scores
    1; a multi-sentence request that also says "and ... as well as ..."
    scores several - independent of what the request is actually about.
    """
    sentences = len([part for part in _SENTENCE_END.split(lowered) if part.strip()])
    connectors = sum(1 for word in words if word in CLAUSE_CONNECTORS)
    return max(sentences, 1) + connectors


def _latest_user_text(messages: list[Message]) -> str:
    """The most recent user-authored text, skipping tool-result-only turns."""
    for message in reversed(messages):
        if message.role != "user":
            continue
        text = " ".join(
            part.text for part in message.parts if isinstance(part, TextPart)
        ).strip()
        if text:
            return text
    return ""


def _count_keyword_hits(words: list[str], keywords: frozenset[str]) -> int:
    """Count how many distinct keyword terms appear (each term at most once,
    so repeating one word doesn't inflate the signal)."""
    return len(set(words) & keywords)


def _has_tool_results(messages: list[Message]) -> bool:
    if not messages:
        return False
    last = messages[-1]
    return any(isinstance(part, ToolResultPart) for part in last.parts)
