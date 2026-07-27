"""Runs the coding agent against one benchmark task and checks the result."""

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from coding_agent.agent.factory import build_agent
from coding_agent.agent.loop import AgentLoopSafetyLimitError
from coding_agent.benchmark.sandbox import SandboxSetupError, prepare
from coding_agent.benchmark.tasks import BenchmarkTask
from coding_agent.config import Config
from coding_agent.llm.base import LLMError
from coding_agent.metrics.usage import Usage, UsageTracker
from coding_agent.optimizations.bundle import OptimizationBundle

ToolCallObserver = Callable[[str, dict], None]

# SWE-bench's problem_statement is the *raw* GitHub issue as originally
# filed - often phrased as a question or bug report ("am I misunderstanding
# something?"), not an instruction. Tested with this passed to the agent
# completely unwrapped: it answered the question conversationally and
# made zero tool calls, instead of exploring the repo and fixing the
# code - a real failure mode found by actually running it, not assumed.
# This wrapper makes the task explicit without changing the issue text
# itself (that stays exactly as SWE-bench provides it, for fidelity).
_TASK_PROMPT_TEMPLATE = (
    "You are working inside a real, already-cloned repository in the "
    "current directory. Below is a real GitHub issue filed against this "
    "exact codebase. Resolve it: explore the repository, find the "
    "relevant code, and make the changes needed to fix the issue. Make "
    "actual edits to the code - do not just explain or discuss the "
    "issue.\n\n"
    "A separate validation step will check your fix afterwards, so you "
    "do not need to run the test suite yourself to confirm it - focus "
    "your effort on understanding the issue and making the correct code "
    "change, then briefly summarize what you changed.\n\n"
    "--- GitHub issue ---\n"
    "{problem_statement}"
)


@dataclass(frozen=True)
class TaskResult:
    """The outcome of running one benchmark task."""

    instance_id: str
    resolved: bool
    usage: Usage
    user_messages: int
    llm_calls: int
    tool_calls: int
    duration_seconds: float
    error: str | None = None


def run_task(
    task: BenchmarkTask,
    root: Path,
    config: Config,
    optimizations: OptimizationBundle,
    on_tool_call: ToolCallObserver | None = None,
) -> TaskResult:
    """Prepare a sandbox, let the agent attempt the task, and check the result.

    Never raises for an expected failure (setup error, agent error,
    safety-limit hit) - those become a TaskResult with resolved=False
    and an error message, the same "recover gracefully" pattern used
    for tool/LLM errors everywhere else in this project, so one bad task
    doesn't stop the rest of the benchmark suite from running.
    """
    start = time.monotonic()
    usage_tracker = UsageTracker()

    try:
        sandbox = prepare(task, root)
    except SandboxSetupError as error:
        return _result(task, usage_tracker, start, resolved=False, error=f"Sandbox setup failed: {error}")

    agent = build_agent(config, usage_tracker, optimizations)

    original_cwd = Path.cwd()
    os.chdir(sandbox.repo_dir)
    agent_error: str | None = None
    try:
        prompt = _TASK_PROMPT_TEMPLATE.format(problem_statement=task.problem_statement)
        agent.run_turn(prompt, on_tool_call=on_tool_call)
    except LLMError as error:
        # Never actually reached the model - there's no meaningful code
        # state to check, so skip straight to a failed result.
        os.chdir(original_cwd)
        return _result(task, usage_tracker, start, resolved=False, error=str(error))
    except AgentLoopSafetyLimitError as error:
        # The agent didn't converge on a final answer, but its tool
        # calls already ran and may have edited the code correctly
        # before it ran out of iterations - check the tests anyway
        # rather than assuming failure. Found by testing: an agent that
        # made the right fix but then burned its remaining iterations
        # re-verifying it (with the wrong Python interpreter, in one
        # observed case) would otherwise be wrongly counted as failed.
        agent_error = str(error)
    finally:
        os.chdir(original_cwd)

    resolved = sandbox.run_tests(task.fail_to_pass + task.pass_to_pass)
    return _result(task, usage_tracker, start, resolved=resolved, error=agent_error)


def _result(
    task: BenchmarkTask,
    usage_tracker: UsageTracker,
    start: float,
    *,
    resolved: bool,
    error: str | None = None,
) -> TaskResult:
    return TaskResult(
        instance_id=task.instance_id,
        resolved=resolved,
        usage=usage_tracker.total,
        user_messages=usage_tracker.user_messages,
        llm_calls=usage_tracker.llm_calls,
        tool_calls=usage_tracker.tool_calls,
        duration_seconds=time.monotonic() - start,
        error=error,
    )
