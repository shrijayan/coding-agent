"""Runs the full benchmark task suite and prints an aggregate report.

This is the tool that actually answers "did this optimization help":
run once with no --enable flags, run again with one, and put the two
printed summaries side by side.
"""

import tempfile
from pathlib import Path

from coding_agent.benchmark.runner import TaskResult, ToolCallObserver, run_task
from coding_agent.benchmark.tasks import TASKS
from coding_agent.config import Config
from coding_agent.metrics.pricing import PricingTable
from coding_agent.metrics.usage import Usage
from coding_agent.optimizations.available import AVAILABLE_OPTIMIZATIONS
from coding_agent.optimizations.bundle import ConflictingOptimizationsError
from coding_agent.optimizations.registry import OptimizationRegistry, UnknownOptimizationError


def run_benchmark(
    config: Config,
    pricing: PricingTable,
    enabled_names: list[str],
) -> None:
    """Run every task in TASKS, print progress as it goes, then a summary."""
    registry = OptimizationRegistry(AVAILABLE_OPTIMIZATIONS)

    # Validate once, up front, before any (possibly slow) sandbox setup
    # runs - a typo in --enable should fail immediately, not after
    # minutes of cloning repos and installing dependencies.
    try:
        registry.resolve(enabled_names)
    except (UnknownOptimizationError, ConflictingOptimizationsError) as error:
        print(f"Configuration error: {error}")
        raise SystemExit(1) from error

    optimizations_label = ", ".join(enabled_names) or "none"
    print(
        f"Running benchmark ({len(TASKS)} tasks, {config.provider} / {config.model}, "
        f"optimizations: {optimizations_label})...\n"
    )

    results: list[TaskResult] = []
    with tempfile.TemporaryDirectory(prefix="coding-agent-benchmark-") as tmp:
        root = Path(tmp)
        for task in TASKS:
            print(f"[{task.instance_id}] setting up sandbox and running agent...")
            # Resolve a *fresh* bundle per task, not one shared across all
            # of them: a stateful optimization (e.g. conversation
            # summarization, which caches a running summary) must not
            # carry state between what are otherwise fully independent
            # tasks - each one is a clean conversation from scratch.
            optimizations = registry.resolve(enabled_names)
            result = run_task(
                task,
                root,
                config,
                optimizations,
                on_tool_call=_make_tool_observer(task.instance_id),
            )
            results.append(result)

            status = "RESOLVED" if result.resolved else "NOT RESOLVED"
            print(f"[{task.instance_id}] {status} in {result.duration_seconds:.1f}s")
            if result.error:
                print(f"  error: {result.error}")
            print()

    _print_summary(results, pricing, config.model)


def _make_tool_observer(instance_id: str) -> ToolCallObserver:
    def observer(name: str, tool_input: dict) -> None:
        print(f"  [{instance_id}] tool: {name}({tool_input})")

    return observer


def _print_summary(results: list[TaskResult], pricing: PricingTable, model: str) -> None:
    resolved_count = sum(1 for result in results if result.resolved)
    total_usage = Usage()
    for result in results:
        total_usage = total_usage + result.usage
    total_cost = pricing.cost_for(total_usage, model)
    total_duration = sum(result.duration_seconds for result in results)

    print("--- Benchmark summary ---")
    print(f"Resolved       : {resolved_count}/{len(results)}")
    print(f"Input tokens   : {total_usage.input_tokens:,}")
    print(f"Output tokens  : {total_usage.output_tokens:,}")
    print(f"Total tokens   : {total_usage.total_tokens:,}")
    print(f"Estimated cost : ${total_cost:.4f}")
    print(f"Wall-clock time: {total_duration:.1f}s")
    print()
    print("Per-task:")
    for result in results:
        status = "PASS" if result.resolved else "FAIL"
        task_cost = pricing.cost_for(result.usage, model)
        print(
            f"  [{status}] {result.instance_id:30s} "
            f"tokens={result.usage.total_tokens:>7,} "
            f"cost=${task_cost:.4f} "
            f"time={result.duration_seconds:>6.1f}s"
        )
