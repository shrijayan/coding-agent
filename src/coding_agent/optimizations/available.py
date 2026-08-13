"""The single registration point for every optimization the base agent
knows how to enable via --enable NAME.

Both the interactive CLI (cli.py) and the benchmark runner
(benchmark/report.py) resolve --enable names against this same dict, so
neither entry point can ever see a different set of optimizations than
the other. Adding a new optimization means: build it in
optimizations/your_optimization.py, then add one line here - see
AGENTS.md's "How to add a new optimization".
"""

from collections.abc import Callable

from coding_agent.optimizations import (
    cache_friendly,
    context_window,
    conversation_summary,
    hybrid_routing,
    loop_guard,
    observability,
    observability_otel,
)
from coding_agent.optimizations.bundle import OptimizationBundle

AVAILABLE_OPTIMIZATIONS: dict[str, Callable[[], OptimizationBundle]] = {
    "conversation-summary": conversation_summary.build,
    "hybrid-routing": hybrid_routing.build,
    "cache-friendly-prompts": cache_friendly.build,
    "loop-guard": loop_guard.build,
    "context-window": context_window.build,
    "observability": observability.build,
    "observability-otel": observability_otel.build,
}
