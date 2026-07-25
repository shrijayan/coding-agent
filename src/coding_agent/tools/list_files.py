"""Tool: list files and directories under a given path."""

from pathlib import Path
from typing import Any

from coding_agent.tools.base import Tool, ToolResult

# Directories every dev tool skips: not project config, just universal noise
# (version control internals, caches, virtualenvs) that would drown out the
# actually useful listing if we included them.
_IGNORED_DIR_NAMES = {".git", "__pycache__", ".venv", "venv", "node_modules"}


class ListFilesTool(Tool):
    """Recursively lists files and directories under a path."""

    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return (
            "List files and directories under the given path, recursively. "
            "Use this to explore the project structure before reading files."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory to list, relative to the project's current working directory. Use '.' for the project root.",
                }
            },
            "required": ["path"],
        }

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        path = Path(tool_input["path"])

        if not path.exists():
            return ToolResult.error(f"Path not found: {path}")
        if not path.is_dir():
            return ToolResult.error(f"Not a directory: {path}")

        entries = sorted(
            entry for entry in path.rglob("*") if not _is_ignored(entry)
        )

        if not entries:
            return ToolResult.ok("(empty directory)")

        lines = [f"{'d' if entry.is_dir() else 'f'}  {entry}" for entry in entries]
        return ToolResult.ok("\n".join(lines))


def _is_ignored(entry: Path) -> bool:
    return any(part in _IGNORED_DIR_NAMES for part in entry.parts)
