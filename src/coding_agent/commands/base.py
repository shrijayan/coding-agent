"""The contract every slash command must follow.

A "slash command" is input starting with '/' that the CLI intercepts
and handles itself - e.g. /usage - instead of sending it to the model
as a message. Keeping every command behind this same small interface
mirrors tools/base.py's Tool interface on purpose: it's the same
"registry of named, pluggable things" shape already used for tools,
applied to a different part of the REPL.
"""

from abc import ABC, abstractmethod


class SlashCommand(ABC):
    """Base class for every slash command the REPL understands."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The command's name, without the leading slash (e.g. "usage")."""

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line summary, e.g. for a future /help command."""

    @abstractmethod
    def run(self) -> str:
        """Execute the command and return the text to print to the user."""
