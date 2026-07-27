"""Recognizes and dispatches slash commands typed in the REPL."""

from coding_agent.commands.base import SlashCommand


class SlashCommandRegistry:
    """A lookup table from command name -> SlashCommand.

    Mirrors ToolRegistry: commands are passed in from outside (constructor
    injection), and this class only knows how to store and dispatch them,
    not how to build any particular command.
    """

    def __init__(self, commands: list[SlashCommand]) -> None:
        self._commands: dict[str, SlashCommand] = {}
        for command in commands:
            if command.name in self._commands:
                raise ValueError(f"Duplicate slash command registered: '/{command.name}'")
            self._commands[command.name] = command

    def is_command(self, user_input: str) -> bool:
        """True if this input should be handled as a command, not sent to the model."""
        return user_input.startswith("/")

    def run(self, user_input: str) -> str:
        """Execute the command named in user_input and return its output."""
        remainder = user_input[1:].strip()
        name = remainder.split()[0] if remainder else ""

        command = self._commands.get(name)
        if command is None:
            known = ", ".join(f"/{n}" for n in sorted(self._commands)) or "(none registered)"
            return f"Unknown command: '{user_input}'. Available: {known}"
        return command.run()
