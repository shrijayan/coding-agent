"""In-memory prompt-cache metrics, mirroring routing/metrics.py's tracker.

The repo already surfaces per-session signals from in-memory trackers (token
usage via /usage, routing decisions via /metrics). This is the same shape for
cache-friendliness, surfaced via /cache. One PromptCacheRecord is appended per
LLMClient.send() (NOT per user turn - a turn spans many sends across the tool
loop), capturing how cacheable that request's prompt was.

What is and isn't estimated here matters, per the project's hard rule:
  - `input_tokens` is the provider's REAL token count for the call, taken
    straight off the usage response - never guessed.
  - every structural figure (stable-prefix bytes, reuse %, cache-friendly ratio)
    is measured in canonical bytes. Those are deterministic facts about the
    prompt we built, not a tokenizer's approximation, so they never masquerade
    as token counts.
"""

from dataclasses import dataclass, field

from coding_agent.optimizations.prompt_cache.builder import BuiltPrompt


@dataclass(frozen=True)
class PromptCacheRecord:
    """Everything worth knowing about one send()'s prompt cache-friendliness."""

    stable_hash: str
    stable_bytes: int
    semi_stable_bytes: int
    dynamic_bytes: int
    total_bytes: int
    reuse_pct: float
    """Fraction of THIS request's canonical bytes that were already present, as
    a leading prefix, in the previous request - i.e. how much a prefix cache
    could reuse. 0.0 on the first send of a session (nothing to reuse yet)."""
    cache_friendly_ratio: float
    """Stable bytes / total bytes: the structurally cacheable share."""
    input_tokens: int
    """Real prompt tokens from the provider's usage response, never estimated."""
    model: str = ""


@dataclass
class PromptCacheTracker:
    """Accumulates prompt-cache records across a session.

    One instance is shared (constructor injection) between the wrapper that
    records into it and the /cache command that reads it - exactly how
    UsageTracker is shared with /usage and RoutingTracker with /metrics. It also
    holds the previous send's canonical stream, since prefix reuse is inherently
    a cross-send measurement.
    """

    records: list[PromptCacheRecord] = field(default_factory=list)
    _previous_canonical: str | None = field(default=None, repr=False)

    def record(
        self, *, built: BuiltPrompt, input_tokens: int, model: str
    ) -> PromptCacheRecord:
        """Compute reuse vs the previous send, store a record, return it."""
        reuse = _prefix_reuse_ratio(self._previous_canonical, built.canonical)
        record = PromptCacheRecord(
            stable_hash=built.stable_hash,
            stable_bytes=built.stable_bytes,
            semi_stable_bytes=built.semi_stable_bytes,
            dynamic_bytes=built.dynamic_bytes,
            total_bytes=built.total_bytes,
            reuse_pct=reuse,
            cache_friendly_ratio=built.cache_friendly_ratio,
            input_tokens=input_tokens,
            model=model,
        )
        self.records.append(record)
        self._previous_canonical = built.canonical
        return record

    @property
    def total_sends(self) -> int:
        return len(self.records)

    def distinct_stable_hashes(self) -> int:
        """How many different stable prefixes were seen. 1 means it never moved."""
        return len({record.stable_hash for record in self.records})

    def avg_reuse_pct(self) -> float | None:
        """Mean prefix reuse across sends that had a previous request to reuse.

        The first send is excluded (its reuse is 0 only because there was nothing
        before it, not because the prompt was un-cacheable). None when there has
        not yet been a second send to compare against.
        """
        comparable = self.records[1:]
        if not comparable:
            return None
        return sum(record.reuse_pct for record in comparable) / len(comparable)

    def avg_cache_friendly_ratio(self) -> float | None:
        if not self.records:
            return None
        return sum(r.cache_friendly_ratio for r in self.records) / len(self.records)

    def total_input_tokens(self) -> int:
        return sum(record.input_tokens for record in self.records)


def _prefix_reuse_ratio(previous: str | None, current: str) -> float:
    """Longest common leading byte run of two canonical streams / current size.

    Bytes (not characters) because that is the unit a provider cache matches on.
    Returns 0.0 when there is no previous request or the current one is empty.
    """
    if previous is None or not current:
        return 0.0
    prev_bytes = previous.encode("utf-8")
    curr_bytes = current.encode("utf-8")
    limit = min(len(prev_bytes), len(curr_bytes))
    shared = 0
    while shared < limit and prev_bytes[shared] == curr_bytes[shared]:
        shared += 1
    return shared / len(curr_bytes)
