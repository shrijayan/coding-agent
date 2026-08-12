"""Loads "skills": small reference files the agent can pull into context on
demand instead of carrying permanently in the system prompt.

Each skill is one Markdown file under coding_agent/skills/ with a YAML
frontmatter block (name, description) followed by its body:

    ---
    name: pytest-conventions
    description: How this project likes pytest tests written.
    ---
    Write one test function per behavior...

Only the name+description of every skill goes into the system prompt (see
context_window.py's menu suffix) - that's the always-present cost, a few
lines. The body only enters context when the model actually calls
load_skill(name) (tools/load_skill.py), which is the whole point: reference
material the model needs occasionally shouldn't ride along on every request
the way a static system-prompt block would.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

SKILLS_DIR = Path(__file__).parent.parent / "skills"


class InvalidSkillFileError(RuntimeError):
    """Raised when a skill file is missing its frontmatter or required fields."""


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str


@dataclass(frozen=True)
class SkillsLibrary:
    """A small, named collection of skills, looked up by name."""

    skills: list[Skill]

    def menu(self) -> str:
        """A short, always-visible listing: name + one-line description for
        each skill, never the full body - that's what keeps this cheap."""
        return "\n".join(f"- {skill.name}: {skill.description}" for skill in self.skills)

    def get(self, name: str) -> Skill | None:
        for skill in self.skills:
            if skill.name == name:
                return skill
        return None

    def names(self) -> list[str]:
        return [skill.name for skill in self.skills]


def load_skills_dir(path: Path = SKILLS_DIR) -> SkillsLibrary:
    """Parse every *.md file in `path` into a Skill, sorted by filename so
    the menu order is deterministic."""
    skills = [_parse_skill_file(file) for file in sorted(path.glob("*.md"))]
    return SkillsLibrary(skills=skills)


def _parse_skill_file(path: Path) -> Skill:
    text = path.read_text()
    if not text.startswith("---"):
        raise InvalidSkillFileError(
            f"Skill file {path} must start with a '---' YAML frontmatter block."
        )
    _, frontmatter, body = text.split("---", 2)
    metadata = yaml.safe_load(frontmatter) or {}
    for field in ("name", "description"):
        if not metadata.get(field):
            raise InvalidSkillFileError(f"Skill file {path} is missing required field '{field}'.")
    return Skill(name=metadata["name"], description=metadata["description"], body=body.strip())
