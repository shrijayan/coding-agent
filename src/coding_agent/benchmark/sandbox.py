"""Sets up an isolated, Docker-free environment for one benchmark task.

No Docker: each task gets a real `git clone` into a fresh temporary
directory and a real virtual environment (via `uv`, already this
project's tool of choice for managing Python versions) with the exact
pinned dependencies from tasks.py - see that module's docstring for why
those exact pins matter and how they were found.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from coding_agent.benchmark.tasks import BenchmarkTask

# A safety net against a hung network call or install, not a tunable
# per-environment setting - same reasoning as list_files.py's ignored
# directory names: a sensible internal default, not user-facing config.
_SETUP_TIMEOUT_SECONDS = 300


class SandboxSetupError(RuntimeError):
    """Raised when a task's repo/environment could not be prepared.

    A broken environment should stop that task clearly, with the
    failing command's actual output - not silently continue and let the
    agent get blamed for a failure that was never its fault.
    """


@dataclass(frozen=True)
class Sandbox:
    """A cloned repo + isolated venv, ready for the agent to work in."""

    task: BenchmarkTask
    repo_dir: Path
    python_bin: Path

    def run_tests(self, test_ids: list[str]) -> bool:
        """Run the given pytest node IDs inside this sandbox.

        Returns True only if every one of them passes - matching
        SWE-bench's own "resolved" definition (all FAIL_TO_PASS tests
        now pass, and no PASS_TO_PASS test was broken along the way).
        """
        result = subprocess.run(
            [str(self.python_bin), "-m", "pytest", *self.task.pytest_args, *test_ids],
            cwd=self.repo_dir,
            capture_output=True,
            text=True,
            timeout=_SETUP_TIMEOUT_SECONDS,
        )
        return result.returncode == 0


def prepare(task: BenchmarkTask, root: Path) -> Sandbox:
    """Clone the repo at base_commit, install pinned deps, apply the test patch."""
    repo_dir = root / task.instance_id
    _run(["git", "clone", "--quiet", task.repo_url, str(repo_dir)])
    _run(["git", "checkout", "--quiet", task.base_commit], cwd=repo_dir)

    _run(["uv", "python", "install", task.python_version])
    venv_dir = repo_dir / ".venv"
    _run(["uv", "venv", "--python", task.python_version, str(venv_dir)])
    python_bin = venv_dir / "bin" / "python"

    _run(["uv", "pip", "install", "--python", str(python_bin), *task.install_args], cwd=repo_dir)
    if task.pip_packages:
        _run(
            ["uv", "pip", "install", "--python", str(python_bin), *task.pip_packages],
            cwd=repo_dir,
        )

    _apply_test_patch(task, repo_dir)

    return Sandbox(task=task, repo_dir=repo_dir, python_bin=python_bin)


def _apply_test_patch(task: BenchmarkTask, repo_dir: Path) -> None:
    patch_file = repo_dir / ".benchmark_test_patch.diff"
    patch_file.write_text(task.test_patch)
    try:
        _run(["git", "apply", str(patch_file)], cwd=repo_dir)
    finally:
        patch_file.unlink(missing_ok=True)


def _run(command: list[str], cwd: Path | None = None) -> None:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_SETUP_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise SandboxSetupError(
            f"Command timed out after {_SETUP_TIMEOUT_SECONDS}s: {' '.join(command)}"
        ) from error

    if completed.returncode != 0:
        raise SandboxSetupError(
            f"Command failed: {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
