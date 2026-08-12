"""Tool: load the full content of one named skill on demand.

Part of the context-window optimization (optimizations/context_window.py):
the system prompt only ever carries the skills menu (names + one-line
descriptions); a skill's actual guidance only enters context when the model
decides it's relevant and calls this tool - see
optimizations/skills_library.py's module docstring for the full rationale.
"""

from collections.abc import Callable
from typing import Any

from coding_agent.optimizations.skills_library import SkillsLibrary
from coding_agent.tools.base import Tool, ToolResult

# Called as on_load(skill_name) right after a successful load, so the
# context-window optimization can record it into its shared tracker without
# this tool needing to know that tracker's shape.
SkillLoadObserver = Callable[[str], None]


class LoadSkillTool(Tool):
    """Loads one skill's full body by name, recording the load for /context."""

    def __init__(self, library: SkillsLibrary, on_load: SkillLoadObserver) -> None:
        self._library = library
        self._on_load = on_load

    @property
    def name(self) -> str:
        return "load_skill"

    @property
    def description(self) -> str:
        return (
            "Load the full guidance for one named skill from the Skills menu "
            "in your instructions. Only call this when a skill's description "
            "actually matches what you're about to do - don't load one you "
            "won't use."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The exact skill name from the Skills menu.",
                }
            },
            "required": ["name"],
        }

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        name = tool_input["name"]
        skill = self._library.get(name)
        if skill is None:
            available = ", ".join(self._library.names()) or "(none)"
            return ToolResult.error(f"No skill named '{name}'. Available: {available}")
        self._on_load(name)
        return ToolResult.ok(skill.body)
