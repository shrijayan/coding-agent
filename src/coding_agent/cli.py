"""The REPL: reads user input, runs one agent turn, prints the answer.

This file's only job is wiring things together and talking to the
terminal. All the actual logic lives in config/, llm/, tools/, agent/,
metrics/, commands/, and optimizations/ - this stays thin on purpose so
it's obvious where to look for behavior versus where to look for I/O.
"""

import time
from typing import Any

from coding_agent.agent.factory import build_agent
from coding_agent.cli_args import parse_args
from coding_agent.commands.metrics_command import RoutingMetricsCommand
from coding_agent.commands.registry import SlashCommandRegistry
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
from coding_agent.optimizations import hybrid_routing
from coding_agent.optimizations.available import AVAILABLE_OPTIMIZATIONS
from coding_agent.optimizations.bundle import ConflictingOptimizationsError
from coding_agent.optimizations.registry import (
    OptimizationRegistry,
    UnknownOptimizationError,
)
from coding_agent.optimizations.routing.metrics import RoutingRecord, RoutingTracker
from coding_agent.optimizations.routing.tiers import InvalidTierConfigError, load_tiers

_EXIT_COMMANDS = {"exit", "quit"}
_HYBRID_ROUTING = "hybrid-routing"


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
            tiers = load_tiers()
            for tier in tiers:
                pricing.require(tier.model or config.model)
        except (MissingPricingError, InvalidTierConfigError) as error:
            print(f"Configuration error: {error}")
            raise SystemExit(1) from error
        configured_models = [tier.model or config.model for tier in tiers]
        routing_tracker = hybrid_routing.get_tracker()
        for warning in hybrid_routing.get_warnings():
            print(f"warning> {warning}")

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

    command_registry = SlashCommandRegistry(commands=commands)

    optimizations_label = ", ".join(args.enabled_optimizations) or "none"
    print(
        f"Coding Agent ready ({config.provider} / {config.model}, "
        f"optimizations: {optimizations_label}). Type 'exit' to quit.\n"
    )
    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return

        if not user_input:
            continue
        if user_input.lower() in _EXIT_COMMANDS:
            print("Bye.")
            return

        if command_registry.is_command(user_input):
            print(f"\n{command_registry.run(user_input)}\n")
            continue

        # Snapshot the routing log so we can show just this turn's decisions
        # afterward - a turn can span many internal send()s (the tool loop),
        # so we summarize the records it produced rather than printing from
        # inside the wrapper on every send().
        routing_mark = len(routing_tracker.records) if routing_tracker else 0
        # Same snapshot idea for the plain-mode turn summary: diff the
        # usage tracker before/after rather than instrumenting the loop.
        calls_before = usage_tracker.llm_calls
        by_model_before = dict(usage_tracker.by_model)
        turn_start = time.perf_counter()

        try:
            answer = agent.run_turn(user_input, on_tool_call=_print_tool_call)
        except LLMError as error:
            print(f"\nerror> {error}\n")
            continue

        turn_ms = (time.perf_counter() - turn_start) * 1000.0
        print(f"\nagent> {answer}\n")

        if routing_tracker is not None:
            new_records = routing_tracker.records[routing_mark:]
            summary = _format_routing_summary(new_records, pricing)
        else:
            summary = _format_turn_summary(
                by_model_before, calls_before, usage_tracker, pricing, config, turn_ms
            )
        if summary:
            print(f"{summary}\n")


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
    """One compact annotation for a turn's routing decisions.

    A single-send turn gets the detailed per-path line from the brief's
    examples; a multi-send turn (tool loop) gets a compact roll-up instead
    of one noisy line per internal send().
    """
    if not records:
        return ""
    if len(records) == 1:
        return _format_single_record(records[0], pricing)

    total_latency = sum(r.latency_ms for r in records)
    total_cost = sum(pricing.cost_for(r.usage, r.model) for r in records)
    breakdown: dict[str, int] = {}
    for record in records:
        breakdown[record.path] = breakdown.get(record.path, 0) + 1
    paths = ", ".join(f"{count} {path}" for path, count in breakdown.items())
    return (
        f"  \u21b3 routing: {len(records)} sends \u00b7 {paths} \u00b7 "
        f"{total_latency:.0f}ms \u00b7 ${total_cost:.4f}"
    )


def _format_single_record(record: RoutingRecord, pricing: PricingTable) -> str:
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
            f"  \u21b3 cheap_escalated \u00b7 {reason} \u2192 escalated {hops} \u00b7 "
            f"{tier}/{model} \u00b7 {difficulty} \u00b7 {latency} \u00b7 {price}"
        )

    if record.path == "cheap":
        gate = "quality gate PASS" if record.gate_passed else "gate skipped"
        if record.gate_passed is False:
            gate = "quality gate FAIL (top of ladder, kept)"
        return (
            f"  \u21b3 cheap \u00b7 {tier}/{model} \u00b7 {difficulty} \u00b7 "
            f"{gate} \u00b7 {latency} \u00b7 {price}"
        )

    return (
        f"  \u21b3 direct_powerful \u00b7 {tier}/{model} \u00b7 {difficulty} \u00b7 "
        f"{latency} \u00b7 {price}"
    )


def _print_tool_call(name: str, tool_input: dict[str, Any]) -> None:
    print(f"  [tool] {name}({tool_input})")
