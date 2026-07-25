"""Holds every tool the agent knows about and dispatches calls by name."""

from typing import Any

from coding_agent.tools.base import Tool, ToolResult


class ToolRegistry:
    """A lookup table from tool name -> Tool, built once at startup.

    Tools are passed in from outside (constructor injection) rather than
    created here. That keeps this class from needing to know how to build
    a BashTool or a ReadFileTool - it only needs to know how to store and
    find them. It also makes testing easy: pass in fake tools instead.
    """

    def __init__(self, tools: list[Tool]) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            if tool.name in self._tools:
                raise ValueError(f"Duplicate tool name registered: '{tool.name}'")
            self._tools[tool.name] = tool

    def definitions(self) -> list[dict[str, Any]]:
        """Schemas for every registered tool, sent to the model each turn."""
        return [tool.definition() for tool in self._tools.values()]

    def execute(self, name: str, tool_input: dict[str, Any]) -> ToolResult:
        """Run the named tool. Unknown tool names are a recoverable error,
        not a crash - the model gets told and can correct itself."""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult.error(f"Unknown tool requested: '{name}'")
        return tool.run(tool_input)
