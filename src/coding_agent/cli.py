"""The REPL: reads user input, runs one agent turn, prints the answer.

This file's only job is wiring things together and talking to the
terminal. All the actual logic lives in config/, llm/, tools/, and
agent/ - this stays thin on purpose so it's obvious where to look for
behavior versus where to look for I/O.
"""

from typing import Any

from coding_agent.agent.loop import AgentLoop
from coding_agent.config import Config, MissingConfigError
from coding_agent.llm.anthropic_client import AnthropicClient
from coding_agent.system_prompt import SYSTEM_PROMPT
from coding_agent.tools.bash import BashTool
from coding_agent.tools.edit_file import EditFileTool
from coding_agent.tools.list_files import ListFilesTool
from coding_agent.tools.read_file import ReadFileTool
from coding_agent.tools.registry import ToolRegistry
from coding_agent.tools.write_file import WriteFileTool

_EXIT_COMMANDS = {"exit", "quit"}


def run() -> None:
    """Entry point: build the agent from config, then loop on user input."""
    try:
        config = Config.from_env()
    except MissingConfigError as error:
        print(f"Configuration error: {error}")
        raise SystemExit(1) from error

    agent = _build_agent(config)

    print("Coding Agent ready. Type 'exit' to quit.\n")
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

        answer = agent.run_turn(user_input, on_tool_call=_print_tool_call)
        print(f"\nagent> {answer}\n")


def _build_agent(config: Config) -> AgentLoop:
    llm_client = AnthropicClient(
        api_key=config.api_key,
        model=config.model,
        max_tokens=config.max_tokens,
    )
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
        system_prompt=SYSTEM_PROMPT,
        max_iterations=config.max_iterations,
    )


def _print_tool_call(name: str, tool_input: dict[str, Any]) -> None:
    print(f"  [tool] {name}({tool_input})")
