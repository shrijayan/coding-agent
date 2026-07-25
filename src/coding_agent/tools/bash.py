"""Tool: run a shell command and capture its output."""

import subprocess
from typing import Any

from coding_agent.tools.base import Tool, ToolResult


class BashTool(Tool):
    """Runs a shell command in the project directory.

    timeout_seconds is injected from Config rather than hardcoded here, so
    changing it (e.g. for a slow test suite) is an env var change, not a
    code change.
    """

    def __init__(self, timeout_seconds: int) -> None:
        self._timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return "bash"

    @property
    def description(self) -> str:
        return (
            "Run a shell command and return its combined stdout/stderr. "
            "Use it to run tests, search files, install packages, or "
            "anything else a terminal can do."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to run.",
                }
            },
            "required": ["command"],
        }

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        command = tool_input["command"]

        try:
            completed = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return ToolResult.error(
                f"Command timed out after {self._timeout_seconds} seconds: {command}"
            )

        output = completed.stdout + completed.stderr

        if completed.returncode != 0:
            return ToolResult.error(
                f"Command exited with code {completed.returncode}:\n{output}"
            )
        return ToolResult.ok(output or "(command produced no output)")
