"""The REPL: reads user input, runs one agent turn, prints the answer.

This file's only job is wiring things together and talking to the
terminal. All the actual logic lives in config/, llm/, tools/, agent/,
metrics/, commands/, and optimizations/ - this stays thin on purpose so
it's obvious where to look for behavior versus where to look for I/O.
"""

from collections.abc import Callable
from typing import Any

from coding_agent.agent.loop import AgentLoop
from coding_agent.cli_args import parse_enabled_optimizations
from coding_agent.commands.registry import SlashCommandRegistry
from coding_agent.commands.usage_command import UsageCommand
from coding_agent.config import Config, MissingConfigError
from coding_agent.llm.base import LLMClient, LLMError
from coding_agent.llm.factory import build_llm_client
from coding_agent.metrics.pricing import MissingPricingError, PricingTable
from coding_agent.metrics.usage import UsageTracker
from coding_agent.optimizations.bundle import ConflictingOptimizationsError, OptimizationBundle
from coding_agent.optimizations.history_policy import DefaultHistoryPolicy
from coding_agent.optimizations.registry import OptimizationRegistry, UnknownOptimizationError
from coding_agent.system_prompt import SYSTEM_PROMPT
from coding_agent.tools.bash import BashTool
from coding_agent.tools.edit_file import EditFileTool
from coding_agent.tools.list_files import ListFilesTool
from coding_agent.tools.read_file import ReadFileTool
from coding_agent.tools.registry import ToolRegistry
from coding_agent.tools.write_file import WriteFileTool

_EXIT_COMMANDS = {"exit", "quit"}

# Every optimization the base agent currently knows how to enable via
# --enable NAME. Adding a new optimization means: build it in
# optimizations/your_optimization.py, then add one line here - see
# AGENTS.md's "How to add a new optimization".
_AVAILABLE_OPTIMIZATIONS: dict[str, Callable[[], OptimizationBundle]] = {}


def run() -> None:
    """Entry point: parse flags, build the agent from config, then loop."""
    enabled_names = parse_enabled_optimizations()

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

    try:
        optimizations = OptimizationRegistry(_AVAILABLE_OPTIMIZATIONS).resolve(enabled_names)
    except (UnknownOptimizationError, ConflictingOptimizationsError) as error:
        print(f"Configuration error: {error}")
        raise SystemExit(1) from error

    usage_tracker = UsageTracker()
    agent = _build_agent(config, usage_tracker, optimizations)
    command_registry = SlashCommandRegistry(
        commands=[
            UsageCommand(
                tracker=usage_tracker,
                pricing=pricing,
                config=config,
                enabled_optimizations=enabled_names,
            ),
        ]
    )

    optimizations_label = ", ".join(enabled_names) or "none"
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


def _build_agent(
    config: Config,
    usage_tracker: UsageTracker,
    optimizations: OptimizationBundle,
) -> AgentLoop:
    llm_client: LLMClient = build_llm_client(config)
    if optimizations.wrap_llm_client is not None:
        llm_client = optimizations.wrap_llm_client(llm_client)

    system_prompt = SYSTEM_PROMPT
    if optimizations.system_prompt_suffix:
        system_prompt = f"{SYSTEM_PROMPT}\n\n{optimizations.system_prompt_suffix}"

    history_policy = optimizations.history_policy or DefaultHistoryPolicy()

    tool_registry = ToolRegistry(
        tools=[
            ReadFileTool(),
            WriteFileTool(),
            EditFileTool(),
            BashTool(timeout_seconds=config.bash_timeout_seconds),
            ListFilesTool(),
        ]
    )
    return AgentLoop(
        llm_client=llm_client,
        tool_registry=tool_registry,
        system_prompt=system_prompt,
        max_iterations=config.max_iterations,
        usage_tracker=usage_tracker,
        history_policy=history_policy,
    )


def _print_tool_call(name: str, tool_input: dict[str, Any]) -> None:
    print(f"  [tool] {name}({tool_input})")
