"""The REPL: reads user input, runs one agent turn, prints the answer.

This file's only job is wiring things together and talking to the
terminal. All the actual logic lives in config/, llm/, tools/, agent/,
metrics/, commands/, and optimizations/ - this stays thin on purpose so
it's obvious where to look for behavior versus where to look for I/O.
"""

import sys
import time
from typing import Any

from coding_agent.agent.factory import build_agent
from coding_agent.cli_args import parse_args
from coding_agent.commands.cache_command import PromptCacheCommand
from coding_agent.commands.compression_command import CompressionCommand
from coding_agent.commands.context_command import ContextWindowCommand
from coding_agent.commands.dedup_command import DedupCommand
from coding_agent.commands.loop_guard_command import LoopGuardCommand
from coding_agent.commands.metrics_command import RoutingMetricsCommand
from coding_agent.commands.observability_command import ObservabilityCommand
from coding_agent.commands.observability_otel_command import ObservabilityOtelCommand
from coding_agent.commands.registry import SlashCommandRegistry
from coding_agent.commands.tool_filter_command import ToolFilterCommand
from coding_agent.commands.usage_command import UsageCommand
from coding_agent.config import Config, MissingConfigError
from coding_agent.llm.base import LLMError
from coding_agent.metrics.pricing import MissingPricingError, PricingTable
from coding_agent.metrics.usage import Usage, UsageTracker
from coding_agent.models_config import (
    ModelsConfigError,
    load_catalog_metadata,
    read_models_yaml,
)
from coding_agent.optimizations import (
    cache_friendly,
    context_window,
    deduplication,
    hybrid_routing,
    loop_guard,
    observability,
    observability_otel,
    prompt_compression,
    tool_filtering,
)
from coding_agent.optimizations.available import AVAILABLE_OPTIMIZATIONS
from coding_agent.optimizations.bundle import ConflictingOptimizationsError
from coding_agent.optimizations.context_window import (
    ContextWindowEvent,
    ContextWindowTracker,
)
from coding_agent.optimizations.deduplication import DedupRecord, DedupTracker
from coding_agent.optimizations.loop_guard import LoopGuardRecord, LoopGuardTracker
from coding_agent.optimizations.observability import CallRecord, ObservabilityTracker
from coding_agent.optimizations.prompt_cache.metrics import (
    PromptCacheRecord,
    PromptCacheTracker,
)
from coding_agent.optimizations.prompt_compression import (
    CompressionRecord,
    CompressionTracker,
)
from coding_agent.optimizations.registry import (
    OptimizationRegistry,
    UnknownOptimizationError,
)
from coding_agent.optimizations.routing.metrics import RoutingRecord, RoutingTracker
from coding_agent.optimizations.routing.tiers import InvalidTierConfigError, load_tiers
from coding_agent.optimizations.tool_filtering import (
    ToolFilterRecord,
    ToolFilterTracker,
)

_EXIT_COMMANDS = {"exit", "quit"}
_HYBRID_ROUTING = "hybrid-routing"
_CACHE_FRIENDLY = "cache-friendly-prompts"
_LOOP_GUARD = "loop-guard"
_CONTEXT_WINDOW = "context-window"
_TOOL_FILTERING = "tool-filtering"
_PROMPT_COMPRESSION = "prompt-compression"
_DEDUPLICATION = "deduplication"
_OBSERVABILITY = "observability"
_OBSERVABILITY_OTEL = "observability-otel"

# Terminal colors: the agent's answer is green, the user's prompt/input white,
# and every auxiliary line (turn/routing/cache summaries, tool calls, warnings,
# and slash-command output like /usage and /metrics) yellow; errors are red.
# Disabled automatically when stdout isn't a TTY so piped/redirected output
# stays free of escape codes.
_GREEN = "\033[32m"
_WHITE = "\033[37m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_RESET = "\033[0m"
_USE_COLOR = sys.stdout.isatty()


def _seq(code: str) -> str:
    """The raw ANSI code, or '' when color is disabled (non-TTY)."""
    return code if _USE_COLOR else ""


def _color(text: str, code: str) -> str:
    """Wrap text in an ANSI color (a no-op when color is disabled)."""
    return f"{code}{text}{_RESET}" if _USE_COLOR else text


def run() -> None:
    """Entry point: parse flags, build the agent from config, then loop."""
    args = parse_args()

    try:
        config = Config.from_env()
    except MissingConfigError as error:
        print(f"Configuration error: {error}")
        raise SystemExit(1) from error

    try:
        pricing = PricingTable.load()
        pricing.require(config.model)
    except (MissingPricingError, ModelsConfigError) as error:
        print(f"Configuration error: {error}")
        raise SystemExit(1) from error

    if args.benchmark:
        from coding_agent.benchmark.report import run_benchmark

        run_benchmark(config, pricing, args.enabled_optimizations)
        return

    try:
        optimizations = OptimizationRegistry(AVAILABLE_OPTIMIZATIONS).resolve(
            args.enabled_optimizations
        )
    except (UnknownOptimizationError, ConflictingOptimizationsError) as error:
        print(f"Configuration error: {error}")
        raise SystemExit(1) from error

    usage_tracker = UsageTracker()
    agent = build_agent(config, usage_tracker, optimizations, pricing=pricing)

    # Per-model capability notes for /usage, from the models.yaml catalog.
    model_metadata = load_catalog_metadata(read_models_yaml())

    # With routing enabled, "configured" means the whole ladder, not just
    # AGENT_MODEL - /usage shows it so the header matches what can run.
    configured_models: list[str] | None = None
    routing_tracker: RoutingTracker | None = None
    if _HYBRID_ROUTING in args.enabled_optimizations:
        # Fail fast now (not mid-demo) if any ladder tier has no pricing
        # entry - /metrics derives cost from it, same rule as /usage.
        try:
            tiers = load_tiers(provider=config.provider)
            for tier in tiers:
                pricing.require(tier.model or config.model)
        except (MissingPricingError, InvalidTierConfigError) as error:
            print(f"Configuration error: {error}")
            raise SystemExit(1) from error
        configured_models = [tier.model or config.model for tier in tiers]
        routing_tracker = hybrid_routing.get_tracker()
        for warning in hybrid_routing.get_warnings():
            print(_color(f"warning> {warning}", _YELLOW))

    # /cache only exists when cache-friendly construction is actually enabled -
    # it reports on the same tracker the wrapper (built above via the bundle)
    # records into, one row per send().
    cache_tracker: PromptCacheTracker | None = None
    if _CACHE_FRIENDLY in args.enabled_optimizations:
        cache_tracker = cache_friendly.get_tracker()

    # /loopguard and /context only exist when their optimization is actually
    # enabled - same "own tracker, own command" shape as cache-friendly above.
    loop_guard_tracker: LoopGuardTracker | None = None
    if _LOOP_GUARD in args.enabled_optimizations:
        loop_guard_tracker = loop_guard.get_tracker()

    context_tracker: ContextWindowTracker | None = None
    if _CONTEXT_WINDOW in args.enabled_optimizations:
        context_tracker = context_window.get_tracker()

    tool_filter_tracker: ToolFilterTracker | None = None
    if _TOOL_FILTERING in args.enabled_optimizations:
        tool_filter_tracker = tool_filtering.get_tracker()

    compression_tracker: CompressionTracker | None = None
    if _PROMPT_COMPRESSION in args.enabled_optimizations:
        compression_tracker = prompt_compression.get_tracker()

    dedup_tracker: DedupTracker | None = None
    if _DEDUPLICATION in args.enabled_optimizations:
        dedup_tracker = deduplication.get_tracker()

    observability_tracker: ObservabilityTracker | None = None
    if _OBSERVABILITY in args.enabled_optimizations:
        observability_tracker = observability.get_tracker()

    observability_otel_command: ObservabilityOtelCommand | None = None
    if _OBSERVABILITY_OTEL in args.enabled_optimizations:
        observability_otel_command = ObservabilityOtelCommand(
            status=observability_otel.get_status()
        )

    commands = [
        UsageCommand(
            tracker=usage_tracker,
            pricing=pricing,
            config=config,
            enabled_optimizations=args.enabled_optimizations,
            configured_models=configured_models,
            model_metadata=model_metadata,
            cost_cap_usd=config.session_cost_cap_usd,
        ),
    ]
    # /metrics only exists when the routing layer is actually enabled - it
    # reports on the same tracker the routing wrapper (built above via the
    # optimization bundle) records into.
    if routing_tracker is not None:
        commands.append(RoutingMetricsCommand(tracker=routing_tracker, pricing=pricing))
    if cache_tracker is not None:
        commands.append(PromptCacheCommand(tracker=cache_tracker))
    if loop_guard_tracker is not None:
        commands.append(LoopGuardCommand(tracker=loop_guard_tracker))
    if context_tracker is not None:
        commands.append(ContextWindowCommand(tracker=context_tracker))
    if tool_filter_tracker is not None:
        commands.append(ToolFilterCommand(tracker=tool_filter_tracker))
    if compression_tracker is not None:
        commands.append(CompressionCommand(tracker=compression_tracker))
    if dedup_tracker is not None:
        commands.append(DedupCommand(tracker=dedup_tracker))
    if observability_tracker is not None:
        commands.append(ObservabilityCommand(tracker=observability_tracker))
    if observability_otel_command is not None:
        commands.append(observability_otel_command)

    command_registry = SlashCommandRegistry(commands=commands)

    optimizations_label = ", ".join(args.enabled_optimizations) or "none"
    print(
        f"Coding Agent ready ({config.provider} / {config.model}, "
        f"optimizations: {optimizations_label}). Type 'exit' to quit.\n"
    )
    while True:
        try:
            user_input = input(_seq(_WHITE) + "you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(_seq(_RESET) + "\nBye.")
            return
        # Close the white input color before printing anything else.
        print(_seq(_RESET), end="", flush=True)

        if not user_input:
            continue
        if user_input.lower() in _EXIT_COMMANDS:
            print("Bye.")
            return

        if command_registry.is_command(user_input):
            print(f"\n{_color(command_registry.run(user_input), _YELLOW)}\n")
            continue

        # Snapshot the routing log so we can show just this turn's decisions
        # afterward - a turn can span many internal send()s (the tool loop),
        # so we summarize the records it produced rather than printing from
        # inside the wrapper on every send().
        routing_mark = len(routing_tracker.records) if routing_tracker else 0
        cache_mark = len(cache_tracker.records) if cache_tracker else 0
        loop_guard_mark = len(loop_guard_tracker.records) if loop_guard_tracker else 0
        context_mark = len(context_tracker.events) if context_tracker else 0
        tool_filter_mark = (
            len(tool_filter_tracker.records) if tool_filter_tracker else 0
        )
        compression_mark = (
            len(compression_tracker.records) if compression_tracker else 0
        )
        dedup_mark = len(dedup_tracker.records) if dedup_tracker else 0
        observability_mark = (
            len(observability_tracker.records) if observability_tracker else 0
        )
        # Same snapshot idea for the plain-mode turn summary: diff the
        # usage tracker before/after rather than instrumenting the loop.
        calls_before = usage_tracker.llm_calls
        by_model_before = dict(usage_tracker.by_model)
        turn_start = time.perf_counter()

        try:
            answer = agent.run_turn(user_input, on_tool_call=_print_tool_call)
        except LLMError as error:
            print(f"\n{_color(f'error> {error}', _RED)}\n")
            continue

        turn_ms = (time.perf_counter() - turn_start) * 1000.0
        print(f"\n{_color(f'agent> {answer}', _GREEN)}\n")

        if routing_tracker is not None:
            new_records = routing_tracker.records[routing_mark:]
            summary = _format_routing_summary(new_records, pricing)
        else:
            summary = _format_turn_summary(
                by_model_before, calls_before, usage_tracker, pricing, config, turn_ms
            )
        if summary:
            print(f"{_color(summary, _YELLOW)}\n")

        # Cache-friendly construction is its own mode with its own signals
        # (reuse %, cacheable ratio), so it prints its own line - in addition
        # to whichever summary above, since it can be enabled alongside routing.
        if cache_tracker is not None:
            cache_summary = _format_cache_summary(cache_tracker.records[cache_mark:])
            if cache_summary:
                print(f"{_color(cache_summary, _YELLOW)}\n")

        # loop-guard and context-window are each their own mode with their
        # own signals too - same "print an extra line, don't crowd the
        # generic one" rule as cache-friendly above.
        if loop_guard_tracker is not None:
            loop_guard_summary = _format_loop_guard_summary(
                loop_guard_tracker.records[loop_guard_mark:]
            )
            if loop_guard_summary:
                print(f"{_color(loop_guard_summary, _YELLOW)}\n")

        if context_tracker is not None:
            context_summary = _format_context_summary(context_tracker.events[context_mark:])
            if context_summary:
                print(f"{_color(context_summary, _YELLOW)}\n")

        # The three prompt-optimization modes each print their own line too,
        # silent on a turn where their mechanism didn't actually do anything.
        if tool_filter_tracker is not None:
            tool_filter_summary = _format_tool_filter_summary(
                tool_filter_tracker.records[tool_filter_mark:]
            )
            if tool_filter_summary:
                print(f"{_color(tool_filter_summary, _YELLOW)}\n")

        if compression_tracker is not None:
            compression_summary = _format_compression_summary(
                compression_tracker.records[compression_mark:]
            )
            if compression_summary:
                print(f"{_color(compression_summary, _YELLOW)}\n")

        if dedup_tracker is not None:
            dedup_summary = _format_dedup_summary(
                dedup_tracker.records[dedup_mark:]
            )
            if dedup_summary:
                print(f"{_color(dedup_summary, _YELLOW)}\n")

        if observability_tracker is not None:
            observability_summary = _format_observability_summary(
                observability_tracker.records[observability_mark:]
            )
            if observability_summary:
                print(f"{_color(observability_summary, _YELLOW)}\n")


def _format_cache_summary(records: list[PromptCacheRecord]) -> str:
    """One compact annotation for a turn's cache-friendly prompt construction.

    Shows only what this mode adds - stable-prefix size and fingerprint, average
    prefix reuse vs the previous request, and the structurally cacheable share -
    none of which the plain or routing summaries carry. A turn spans many sends
    (the tool loop), so reuse is averaged across the sends it produced.
    """
    if not records:
        return ""
    latest = records[-1]
    avg_reuse = sum(record.reuse_pct for record in records) / len(records)
    return (
        f"  \u21b3 cache: {len(records)} sends \u00b7 "
        f"stable {latest.stable_bytes:,}B ({latest.stable_hash[:8]}) \u00b7 "
        f"reuse {avg_reuse * 100:.0f}% \u00b7 "
        f"cacheable {latest.cache_friendly_ratio * 100:.0f}%"
    )


def _format_loop_guard_summary(records: list[LoopGuardRecord]) -> str:
    """One compact annotation for a turn's loop-guard activity: how many
    sends it watched, the repeat streak it saw, and any nudges/halts."""
    if not records:
        return ""
    nudged = sum(1 for record in records if record.action == "nudged")
    halted = sum(1 for record in records if record.action == "halted")
    streak = records[-1].repeat_count
    return (
        f"  \u21b3 loop-guard: {len(records)} sends \u00b7 streak {streak} \u00b7 "
        f"{nudged} nudged \u00b7 {halted} halted"
    )


def _format_context_summary(events: list[ContextWindowEvent]) -> str:
    """One compact annotation for a turn's context-window optimization:
    stale tool output pruned (a deterministic char count, not a token
    estimate) and any skills loaded on demand. Silent when neither
    happened this turn - most turns, since both are conditional."""
    prunes = [event for event in events if event.kind == "prune"]
    skills = [event.skill_name for event in events if event.kind == "skill_load"]
    if not prunes and not skills:
        return ""

    parts = []
    if prunes:
        chars = sum(event.chars_removed for event in prunes)
        plural = "s" if len(prunes) != 1 else ""
        parts.append(f"pruned {len(prunes)} output{plural} ({chars:,} chars)")
    if skills:
        parts.append("skills loaded: " + ", ".join(skills))
    return "  \u21b3 context: " + " \u00b7 ".join(parts)


def _format_observability_summary(records: list[CallRecord]) -> str:
    """One compact annotation for a turn's observability data: call count,
    average latency, and - the actual debugging payoff - any errors from
    *this turn* flagged inline, by name, so a problem is visible right
    where it happened instead of only in /observability."""
    if not records:
        return ""
    avg_latency = sum(r.latency_ms for r in records) / len(records)
    parts = [f"{len(records)} calls", f"avg {avg_latency:.0f}ms"]

    errors = [r for r in records if not r.success]
    if errors:
        detail = errors[-1]
        label = detail.name or "(no model - call failed)"
        parts.append(f"{len(errors)} error(s): {label}")

    return "  ↳ observability: " + " · ".join(parts)


def _format_tool_filter_summary(records: list[ToolFilterRecord]) -> str:
    """One compact annotation for a turn's tool filtering: how many tool
    definitions were withheld across the turn's sends, and which. Silent
    when nothing was withheld - the safe fallback kept everything."""
    withheld: dict[str, int] = {}
    for record in records:
        for name in record.filtered_names:
            withheld[name] = withheld.get(name, 0) + 1
    if not withheld:
        return ""
    total = sum(withheld.values())
    names = ", ".join(sorted(withheld))
    return (
        f"  \u21b3 tool-filter: {len(records)} sends \u00b7 "
        f"withheld {total} definition(s) ({names})"
    )


def _format_compression_summary(records: list[CompressionRecord]) -> str:
    """One compact annotation for a turn's prompt compression: the
    deterministic size cut applied to every send this turn. Token effect
    is /usage's job - these are byte facts about text we swapped."""
    if not records:
        return ""
    latest = records[-1]
    return (
        f"  \u21b3 compression: {len(records)} sends \u00b7 "
        f"system {latest.system_chars_before:,}->{latest.system_chars_after:,} chars \u00b7 "
        f"tool docs {latest.tool_chars_before:,}->{latest.tool_chars_after:,} chars"
    )


def _format_dedup_summary(records: list[DedupRecord]) -> str:
    """One compact annotation for a turn's deduplication: duplicates
    replaced and their size. Silent on a turn with no duplicates - most
    turns, since exact repeats only happen when content is revisited."""
    if not records:
        return ""
    chars = sum(record.chars_removed for record in records)
    plural = "s" if len(records) != 1 else ""
    return (
        f"  \u21b3 dedup: replaced {len(records)} duplicate{plural} "
        f"({chars:,} chars)"
    )


def _format_turn_summary(
    by_model_before: dict[str, Usage],
    calls_before: int,
    tracker: UsageTracker,
    pricing: PricingTable,
    config: Config,
    elapsed_ms: float,
) -> str:
    """One compact annotation for a turn in any non-routing mode.

    Shows the same at-a-glance data the routing summary gives - model,
    calls, tokens, time, cost - minus the fields that only mean something
    when routing is active (difficulty, quality gate, escalation path).
    Each mode shows only the data that actually applies to it; a new mode
    with its own extra signals should print its own line (see AGENTS.md).
    """
    calls = tracker.llm_calls - calls_before
    if calls == 0:
        return ""

    models: list[str] = []
    turn_tokens = 0
    turn_cost = 0.0
    for model, usage in tracker.by_model.items():
        before = by_model_before.get(model, Usage())
        delta = Usage(
            input_tokens=usage.input_tokens - before.input_tokens,
            output_tokens=usage.output_tokens - before.output_tokens,
        )
        if delta.total_tokens == 0:
            continue
        models.append(model or config.model)
        turn_tokens += delta.total_tokens
        turn_cost += pricing.cost_for(delta, model or config.model)

    label = ", ".join(models) or config.model
    calls_label = f"{calls} LLM call" + ("s" if calls != 1 else "")
    return (
        f"  \u21b3 {label} \u00b7 {calls_label} \u00b7 {turn_tokens:,} tokens \u00b7 "
        f"{elapsed_ms:.0f}ms \u00b7 ${turn_cost:.4f}"
    )


def _format_routing_summary(
    records: list[RoutingRecord], pricing: PricingTable
) -> str:
    """One annotation for a turn's routing decisions.

    A single-send turn is the detailed per-path line. A multi-send turn (the
    tool loop) gets a header roll-up plus a numbered breakdown, one line per
    send - so the difficulty and answering model are always visible, even
    across many internal sends, rather than being collapsed away.
    """
    if not records:
        return ""
    if len(records) == 1:
        return f"  \u21b3 {_routing_detail(records[0], pricing)}"

    total_latency = sum(r.latency_ms for r in records)
    total_cost = sum(pricing.cost_for(r.usage, r.model) for r in records)
    breakdown: dict[str, int] = {}
    for record in records:
        breakdown[record.path] = breakdown.get(record.path, 0) + 1
    paths = ", ".join(f"{count} {path}" for path, count in breakdown.items())
    header = (
        f"  \u21b3 routing: {len(records)} sends \u00b7 {paths} \u00b7 "
        f"{total_latency:.0f}ms \u00b7 ${total_cost:.4f}"
    )
    lines = [header]
    lines.extend(
        f"      {index}. {_routing_detail(record, pricing)}"
        for index, record in enumerate(records, 1)
    )
    return "\n".join(lines)


def _routing_detail(record: RoutingRecord, pricing: PricingTable) -> str:
    """The per-send detail (path, tier/model, difficulty, gate, latency, cost)
    without the leading marker, so both the single-send line and each row of
    the multi-send breakdown share exactly one formatting."""
    cost = pricing.cost_for(record.usage, record.model)
    model = record.model.removeprefix("ollama/")
    tier = record.tier or record.path
    latency = f"{record.latency_ms:.0f}ms"
    price = f"${cost:.4f}"
    difficulty = f"difficulty {record.difficulty:.2f}"

    if record.path == "cheap_escalated":
        reason = ", ".join(record.gate_failed_checks) or "gate_failed"
        hops = f"+{record.hops} tier" + ("s" if record.hops != 1 else "")
        return (
            f"cheap_escalated \u00b7 {reason} \u2192 escalated {hops} \u00b7 "
            f"{tier}/{model} \u00b7 {difficulty} \u00b7 {latency} \u00b7 {price}"
        )

    if record.path == "cheap":
        gate = "quality gate PASS" if record.gate_passed else "gate skipped"
        if record.gate_passed is False:
            gate = "quality gate FAIL (top of ladder, kept)"
        return (
            f"cheap \u00b7 {tier}/{model} \u00b7 {difficulty} \u00b7 "
            f"{gate} \u00b7 {latency} \u00b7 {price}"
        )

    return (
        f"direct_powerful \u00b7 {tier}/{model} \u00b7 {difficulty} \u00b7 "
        f"{latency} \u00b7 {price}"
    )


def _print_tool_call(name: str, tool_input: dict[str, Any]) -> None:
    print(_color(f"  [tool] {name}({tool_input})", _YELLOW))
