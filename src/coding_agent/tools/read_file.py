"""Tool: read the contents of a file."""

from pathlib import Path
from typing import Any

from coding_agent.tools.base import Tool, ToolResult


class ReadFileTool(Tool):
    """Reads a text file from disk so the model can see its exact content."""

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read the full contents of a text file at the given path. "
            "Always do this before editing a file, so you know its exact "
            "current content."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file, relative to the project's current working directory.",
                }
            },
            "required": ["path"],
        }

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        path = Path(tool_input["path"])

        if not path.exists():
            return ToolResult.error(f"File not found: {path}")
        if path.is_dir():
            return ToolResult.error(f"Path is a directory, not a file: {path}")

        try:
            content = path.read_text()
        except UnicodeDecodeError:
            return ToolResult.error(f"Cannot read '{path}': it is not a text file")

        return ToolResult.ok(content)
