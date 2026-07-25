"""Tool: replace one exact snippet of text in a file with another.

This is the same "find exact text, fail if it's not unique" pattern used
by production coding agents: it forces precise, reviewable edits instead
of a fuzzy rewrite of the whole file.
"""

from pathlib import Path
from typing import Any

from coding_agent.tools.base import Tool, ToolResult


class EditFileTool(Tool):
    """Replaces an exact, unique snippet of text within an existing file."""

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return (
            "Replace an exact snippet of text in an existing file with new "
            "text. old_text must match the file's current content exactly "
            "(including whitespace) and must appear exactly once. Read the "
            "file first to copy old_text precisely."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to edit.",
                },
                "old_text": {
                    "type": "string",
                    "description": "Exact, unique text currently in the file to be replaced.",
                },
                "new_text": {
                    "type": "string",
                    "description": "Text to put in its place.",
                },
            },
            "required": ["path", "old_text", "new_text"],
        }

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        path = Path(tool_input["path"])
        old_text = tool_input["old_text"]
        new_text = tool_input["new_text"]

        if not path.exists():
            return ToolResult.error(f"File not found: {path}")

        content = path.read_text()
        occurrences = content.count(old_text)

        if occurrences == 0:
            return ToolResult.error(
                f"old_text not found in '{path}'. Read the file again to "
                "get its exact current content before editing."
            )
        if occurrences > 1:
            return ToolResult.error(
                f"old_text appears {occurrences} times in '{path}'; it must "
                "be unique. Include more surrounding context so it matches "
                "only one place."
            )

        path.write_text(content.replace(old_text, new_text))
        return ToolResult.ok(f"Edited {path}")
