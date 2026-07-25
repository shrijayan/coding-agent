"""The contract every tool must follow.

A "tool" is one capability we let the model use, e.g. reading a file.
Keeping every tool behind this same small interface is what lets the
agent loop call any of them without knowing which one it's talking to
(that's polymorphism doing the work for us).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    """What a tool hands back after it runs.

    A tool should never raise an exception for an expected failure (file
    not found, bad input, command failed, ...). Instead it returns a
    ToolResult with is_error=True. That result gets sent back to the model
    as text, so the model can see what went wrong and try something else -
    the same way a human developer reads an error and adjusts.

    Unexpected failures (bugs) still raise normally and stop the program;
    fail fast rather than hide a real bug behind a friendly message.
    """

    output: str
    is_error: bool = False

    @classmethod
    def ok(cls, output: str) -> "ToolResult":
        return cls(output=output, is_error=False)

    @classmethod
    def error(cls, message: str) -> "ToolResult":
        return cls(output=message, is_error=True)


class Tool(ABC):
    """Base class for every tool the agent can call."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name the model uses to request this tool."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Tells the model what this tool does and when to use it.

        This is part of the prompt the model sees, so be specific - vague
        descriptions lead to the model picking the wrong tool.
        """

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]:
        """JSON schema for this tool's expected input arguments."""

    @abstractmethod
    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        """Execute the tool with the given input and return the result."""

    def definition(self) -> dict[str, Any]:
        """The shape the Anthropic API expects when listing available tools."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
