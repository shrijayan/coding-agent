"""Tests for context-window optimization (context_window.py, skills_library.py,
tools/load_skill.py)."""

from pathlib import Path

from coding_agent.commands.context_command import ContextWindowCommand
from coding_agent.llm.messages import Message, TextPart, ToolResultPart, ToolUsePart
from coding_agent.optimizations import context_window
from coding_agent.optimizations.context_window import (
    ContextPruningPolicy,
    ContextWindowTracker,
)
from coding_agent.optimizations.history_policy import HistoryContext
from coding_agent.optimizations.skills_library import (
    InvalidSkillFileError,
    Skill,
    SkillsLibrary,
    load_skills_dir,
)
from coding_agent.tools.load_skill import LoadSkillTool

_BIG_OUTPUT = "x" * 500  # over the 400-char test threshold
_SMALL_OUTPUT = "short"


def _user(text: str) -> Message:
    return Message(role="user", parts=[TextPart(text)])


def _call_pair(output: str, path: str = "big.py") -> list[Message]:
    return [
        Message(
            role="assistant",
            parts=[ToolUsePart(id=f"call-{path}", name="read_file", input={"path": path})],
        ),
        Message(
            role="user",
            parts=[ToolResultPart(tool_use_id=f"call-{path}", output=output, is_error=False)],
        ),
    ]


def _context() -> HistoryContext:
    return HistoryContext(llm_client=None, usage_tracker=None)  # unused by this policy


# --- Pruning -----------------------------------------------------------------


def test_short_history_is_left_untouched() -> None:
    tracker = ContextWindowTracker()
    policy = ContextPruningPolicy(keep_recent_messages=6, min_chars_to_prune=400, tracker=tracker)
    messages = [_user("hi"), *_call_pair(_BIG_OUTPUT)]

    result = policy.prepare(messages, _context())

    assert result == messages
    assert tracker.events == []


def test_prunes_old_bulky_output_with_specific_placeholder() -> None:
    tracker = ContextWindowTracker()
    policy = ContextPruningPolicy(keep_recent_messages=1, min_chars_to_prune=400, tracker=tracker)
    old_pair = _call_pair(_BIG_OUTPUT, path="calculator.py")
    messages = [_user("hi"), *old_pair, _user("what's next")]

    result = policy.prepare(messages, _context())

    pruned_result_part = result[2].parts[0]
    assert isinstance(pruned_result_part, ToolResultPart)
    assert "pruned" in pruned_result_part.output
    assert "calculator.py" in pruned_result_part.output
    assert str(len(_BIG_OUTPUT)) in pruned_result_part.output
    assert _BIG_OUTPUT not in pruned_result_part.output
    assert tracker.total_prunes == 1
    assert tracker.total_chars_pruned == len(_BIG_OUTPUT)


def test_leaves_small_output_alone_even_outside_keep_window() -> None:
    tracker = ContextWindowTracker()
    policy = ContextPruningPolicy(keep_recent_messages=1, min_chars_to_prune=400, tracker=tracker)
    messages = [_user("hi"), *_call_pair(_SMALL_OUTPUT), _user("what's next")]

    result = policy.prepare(messages, _context())

    assert result[2].parts[0].output == _SMALL_OUTPUT
    assert tracker.events == []


def test_never_splits_a_tool_use_from_its_tool_result() -> None:
    tracker = ContextWindowTracker()
    policy = ContextPruningPolicy(keep_recent_messages=1, min_chars_to_prune=400, tracker=tracker)
    # keep_recent_messages=1 would naively cut right between the tool_use and
    # tool_result of the last pair - safe_keep_from must push the cut earlier.
    messages = [_user("hi"), *_call_pair(_BIG_OUTPUT)]

    result = policy.prepare(messages, _context())

    # The trailing pair must stay together and untouched (still the raw
    # output, not a placeholder), since it can't safely be separated.
    assert result[-1].parts[0].output == _BIG_OUTPUT
    assert tracker.events == []


def test_repeated_prepare_calls_do_not_double_count_the_same_prune() -> None:
    """AgentLoop calls prepare() again on every send() within a session,
    always from the same untouched, growing conversation - the same old
    bulky output must not get "pruned" and recorded again each time."""
    tracker = ContextWindowTracker()
    policy = ContextPruningPolicy(keep_recent_messages=1, min_chars_to_prune=400, tracker=tracker)
    old_pair = _call_pair(_BIG_OUTPUT, path="calculator.py")
    messages = [_user("hi"), *old_pair, _user("what's next")]

    policy.prepare(messages, _context())
    policy.prepare(messages, _context())
    policy.prepare(messages, _context())

    assert tracker.total_prunes == 1
    assert tracker.total_chars_pruned == len(_BIG_OUTPUT)


def test_never_mutates_the_original_conversation() -> None:
    tracker = ContextWindowTracker()
    policy = ContextPruningPolicy(keep_recent_messages=1, min_chars_to_prune=400, tracker=tracker)
    original = [_user("hi"), *_call_pair(_BIG_OUTPUT, path="calculator.py"), _user("next")]
    snapshot = list(original)

    policy.prepare(original, _context())

    assert original == snapshot


# --- Skills library ----------------------------------------------------------


def test_load_skills_dir_parses_shipped_skill_files() -> None:
    library = load_skills_dir()
    names = library.names()
    assert "pytest-conventions" in names
    assert "docstring-style" in names
    assert "git-commit-style" in names
    skill = library.get("pytest-conventions")
    assert skill is not None
    assert "arrange" in skill.body.lower()


def test_load_skills_dir_parses_frontmatter_and_body(tmp_path: Path) -> None:
    (tmp_path / "example.md").write_text(
        "---\nname: example\ndescription: An example skill.\n---\nDo the thing.\n"
    )
    library = load_skills_dir(tmp_path)
    assert library.names() == ["example"]
    skill = library.get("example")
    assert skill == Skill(name="example", description="An example skill.", body="Do the thing.")


def test_load_skills_dir_rejects_missing_frontmatter(tmp_path: Path) -> None:
    (tmp_path / "broken.md").write_text("Just some text, no frontmatter.")
    try:
        load_skills_dir(tmp_path)
        assert False, "expected InvalidSkillFileError"
    except InvalidSkillFileError:
        pass


def test_menu_lists_name_and_description_only() -> None:
    library = SkillsLibrary(skills=[Skill(name="a", description="does a thing", body="secret body")])
    menu = library.menu()
    assert "a: does a thing" in menu
    assert "secret body" not in menu


# --- LoadSkillTool ------------------------------------------------------------


def test_load_skill_tool_returns_body_and_records_load() -> None:
    library = SkillsLibrary(skills=[Skill(name="a", description="d", body="the body")])
    loaded: list[str] = []
    tool = LoadSkillTool(library=library, on_load=loaded.append)

    result = tool.run({"name": "a"})

    assert not result.is_error
    assert result.output == "the body"
    assert loaded == ["a"]


def test_load_skill_tool_errors_clearly_on_unknown_name() -> None:
    library = SkillsLibrary(skills=[Skill(name="a", description="d", body="body")])
    tool = LoadSkillTool(library=library, on_load=lambda name: None)

    result = tool.run({"name": "nonexistent"})

    assert result.is_error
    assert "nonexistent" in result.output
    assert "a" in result.output


# --- build() -------------------------------------------------------------------


def test_build_returns_bundle_with_all_three_hooks(monkeypatch) -> None:
    # build() calls Config.from_env(), which needs the whole config, not
    # just this optimization's two knobs - same as every other build().
    monkeypatch.setenv("AGENT_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "25")
    monkeypatch.setenv("AGENT_BASH_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("AGENT_SUMMARY_THRESHOLD_MESSAGES", "10")
    monkeypatch.setenv("AGENT_SUMMARY_KEEP_RECENT_MESSAGES", "4")
    monkeypatch.setenv("AGENT_LOOP_GUARD_NUDGE_AFTER", "2")
    monkeypatch.setenv("AGENT_LOOP_GUARD_HALT_AFTER", "4")
    monkeypatch.setenv("AGENT_CONTEXT_PRUNE_KEEP_RECENT_MESSAGES", "6")
    monkeypatch.setenv("AGENT_CONTEXT_PRUNE_MIN_CHARS_TO_PRUNE", "400")
    monkeypatch.setenv("AGENT_CONTEXT_WINDOW_SKILLS_ENABLED", "true")
    monkeypatch.setenv("AGENT_DEDUP_MIN_CHARS", "200")
    bundle = context_window.build()

    assert bundle.history_policy is not None
    assert bundle.extra_tools is not None and len(bundle.extra_tools) == 1
    assert bundle.system_prompt_suffix is not None
    assert "pytest-conventions" in bundle.system_prompt_suffix


def test_build_with_skills_disabled_returns_pruning_only(monkeypatch) -> None:
    # Same full env as the test above, except the skills flag - lets pruning's
    # savings be measured without the fixed menu/tool-schema tax on top.
    monkeypatch.setenv("AGENT_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "25")
    monkeypatch.setenv("AGENT_BASH_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("AGENT_SUMMARY_THRESHOLD_MESSAGES", "10")
    monkeypatch.setenv("AGENT_SUMMARY_KEEP_RECENT_MESSAGES", "4")
    monkeypatch.setenv("AGENT_LOOP_GUARD_NUDGE_AFTER", "2")
    monkeypatch.setenv("AGENT_LOOP_GUARD_HALT_AFTER", "4")
    monkeypatch.setenv("AGENT_CONTEXT_PRUNE_KEEP_RECENT_MESSAGES", "6")
    monkeypatch.setenv("AGENT_CONTEXT_PRUNE_MIN_CHARS_TO_PRUNE", "400")
    monkeypatch.setenv("AGENT_CONTEXT_WINDOW_SKILLS_ENABLED", "false")
    monkeypatch.setenv("AGENT_DEDUP_MIN_CHARS", "200")
    bundle = context_window.build()

    assert bundle.history_policy is not None
    assert bundle.extra_tools is None
    assert bundle.system_prompt_suffix is None


# --- Command -------------------------------------------------------------------


def test_command_handles_empty_and_populated() -> None:
    tracker = ContextWindowTracker()
    command = ContextWindowCommand(tracker=tracker)
    assert "No activity yet" in command.run()

    tracker.record_prune(812)
    tracker.record_skill_load("pytest-conventions")
    output = command.run()
    assert "Outputs pruned   : 1" in output
    assert "Chars removed    : 812" in output
    assert "pytest-conventions" in output
