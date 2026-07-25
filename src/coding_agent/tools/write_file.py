"""Tool: create a new file, or overwrite an existing one entirely."""

from pathlib import Path
from typing import Any

from coding_agent.tools.base import Tool, ToolResult


class WriteFileTool(Tool):
    """Writes full content to a file, creating parent directories as needed."""

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Create a file with the given content, or completely overwrite "
            "it if it already exists. Use edit_file instead when you only "
            "want to change part of an existing file."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file, relative to the project's current working directory.",
                },
                "content": {
                    "type": "string",
                    "description": "The full content to write into the file.",
                },
            },
            "required": ["path", "content"],
        }

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        path = Path(tool_input["path"])
        content = tool_input["content"]

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        except OSError as error:
            return ToolResult.error(f"Could not write to '{path}': {error}")

        return ToolResult.ok(f"Wrote {len(content)} characters to {path}")
