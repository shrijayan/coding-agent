"""The difficulty scorer: features -> a 0.0-1.0 difficulty score.

This is the heuristic the workshop reads aloud, so it is deliberately one
short, named-constant-driven function - no magic numbers scattered
around, no hidden state. It implements the "pre-generation router" half
of the hybrid design: decide EASY vs HARD *before* spending a single
token, using only the free local features from features.py.

The score is a clamped weighted sum of five signals. The weights are set
so that the three **vocabulary-independent** signals (length, technical
density, clause complexity) can cross a typical threshold *on their own*:

    LENGTH + TECHNICAL_DENSITY + CLAUSE_COMPLEXITY = 0.30 + 0.25 + 0.15
                                                   = 0.70 achievable
                                                     with zero keyword hits

That property is the whole point, and it is asserted in the test suite.
The first version of this scorer weighted keywords so heavily that a
request using unlisted vocabulary could reach at most 0.50 - below the
default 0.55 threshold - meaning a genuinely hard request phrased in
words nobody anticipated would *always* be sent to the cheap tier. The
keyword lists are now a precision boost on top of signals that work
without them, not the load-bearing element.

`predict()` is the explicit upgrade hook the survey calls out: once
routing logs have real (features -> did-it-escalate) data, a trained
scikit-learn classifier or bandit can drop in behind this exact
signature with zero changes to the wrapper that calls it.
"""

from coding_agent.optimizations.routing.features import Features

# How the signals combine. Each is the maximum contribution that signal can
# add (+) or subtract (-) from the score before the final clamp.
#
# The first three are vocabulary-independent and sum to 0.70, comfortably
# above any sane threshold - so difficulty stays detectable when every
# keyword misses. The keyword weights only sharpen an already-working
# decision.
LENGTH_WEIGHT = 0.30
TECHNICAL_DENSITY_WEIGHT = 0.25
CLAUSE_COMPLEXITY_WEIGHT = 0.15
HARD_KEYWORD_WEIGHT = 0.30
CODE_FENCE_WEIGHT = 0.15
EASY_KEYWORD_WEIGHT = 0.30

# The point at which each raw count is considered "maxed out" - counts at
# or above these saturate that signal's contribution to its full weight,
# so one extra keyword past the cap doesn't keep inflating the score.
LONG_REQUEST_WORDS = 60
HARD_KEYWORD_SATURATION = 3
EASY_KEYWORD_SATURATION = 2
CODE_FENCE_SATURATION = 3  # 3 backtick markers == roughly one fenced block pair + one
# A quarter of the words being long/technical is already a very dense
# request - past that, extra density says nothing new.
TECHNICAL_DENSITY_SATURATION = 0.25
# Roughly six chained clauses is a thoroughly multi-part request.
CLAUSE_SATURATION = 6


def score_difficulty(features: Features) -> float:
    """Return a difficulty score in [0.0, 1.0] for the given features.

    0.0 == unmistakably easy, 1.0 == unmistakably hard. The caller
    compares this to a tier's difficulty ceiling to pick where to start.
    """
    # Vocabulary-independent signals: these work on any request, including
    # ones using words no keyword list has ever seen.
    length_signal = _saturate(features.word_count, LONG_REQUEST_WORDS)
    density_signal = _saturate(features.long_word_ratio, TECHNICAL_DENSITY_SATURATION)
    clause_signal = _saturate(features.clause_count, CLAUSE_SATURATION)

    # Vocabulary-dependent signals: a precision boost, not the foundation.
    hard_signal = _saturate(features.hard_keyword_hits, HARD_KEYWORD_SATURATION)
    easy_signal = _saturate(features.easy_keyword_hits, EASY_KEYWORD_SATURATION)
    fence_signal = _saturate(features.code_fence_count, CODE_FENCE_SATURATION)

    score = (
        LENGTH_WEIGHT * length_signal
        + TECHNICAL_DENSITY_WEIGHT * density_signal
        + CLAUSE_COMPLEXITY_WEIGHT * clause_signal
        + HARD_KEYWORD_WEIGHT * hard_signal
        + CODE_FENCE_WEIGHT * fence_signal
        - EASY_KEYWORD_WEIGHT * easy_signal
    )
    return _clamp01(score)


def predict(features: Features) -> float:
    """Upgrade hook: same signature a trained classifier will implement.

    Today it just delegates to the readable heuristic. Once routing logs
    have labelled data, swap the body for a loaded scikit-learn model's
    probability output - nothing that calls this needs to change.
    """
    return score_difficulty(features)


def _saturate(count: float, cap: float) -> float:
    """Map a raw count/ratio onto [0.0, 1.0], flattening out at `cap`."""
    if cap <= 0:
        return 0.0
    return min(count / cap, 1.0)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
