"""The REPL: reads user input, runs one agent turn, prints the answer.

This file's only job is wiring things together and talking to the
terminal. All the actual logic lives in config/, llm/, tools/, agent/,
metrics/, commands/, and optimizations/ - this stays thin on purpose so
it's obvious where to look for behavior versus where to look for I/O.
"""

from typing import Any

from coding_agent.agent.factory import build_agent
from coding_agent.cli_args import parse_args
from coding_agent.commands.registry import SlashCommandRegistry
from coding_agent.commands.usage_command import UsageCommand
from coding_agent.config import Config, MissingConfigError
from coding_agent.llm.base import LLMError
from coding_agent.metrics.pricing import MissingPricingError, PricingTable
from coding_agent.metrics.usage import UsageTracker
from coding_agent.optimizations.available import AVAILABLE_OPTIMIZATIONS
from coding_agent.optimizations.bundle import ConflictingOptimizationsError
from coding_agent.optimizations.registry import OptimizationRegistry, UnknownOptimizationError

_EXIT_COMMANDS = {"exit", "quit"}


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
    except MissingPricingError as error:
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
    agent = build_agent(config, usage_tracker, optimizations)
    command_registry = SlashCommandRegistry(
        commands=[
            UsageCommand(
                tracker=usage_tracker,
                pricing=pricing,
                config=config,
                enabled_optimizations=args.enabled_optimizations,
            ),
        ]
    )

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

        try:
            answer = agent.run_turn(user_input, on_tool_call=_print_tool_call)
        except LLMError as error:
            print(f"\nerror> {error}\n")
            continue

        print(f"\nagent> {answer}\n")


def _print_tool_call(name: str, tool_input: dict[str, Any]) -> None:
    print(f"  [tool] {name}({tool_input})")
