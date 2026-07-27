"""The fixed set of real-world coding tasks the benchmark runs.

Each task is a real GitHub issue from SWE-bench Lite (a well-known,
publicly verifiable benchmark of real software engineering problems),
with a real hidden test that only passes once the issue is actually
fixed - see https://www.swebench.com. The task's prompt is never
whatever a user happens to type interactively; it's always this same
fixed problem_statement, every time, for every optimization
configuration - that's what makes "40% fewer tokens with this
optimization on" a comparison you can trust instead of an artifact of
two different tasks being run.

Unlike the official SWE-bench harness (which builds a Docker image per
task - see https://www.swebench.com/SWE-bench/guides/docker_setup/,
~120GB disk, 16GB+ RAM, ~60 environment images), this project runs
tasks directly in a plain virtual environment (see benchmark/sandbox.py)
for a fast, live-workshop-friendly loop. That trade costs some
environment fidelity, which is exactly why every field below
(python_version, pip_packages, pytest_args) was hand-verified to
actually work before being added here - not copied blind from the
dataset. python_version and pip_packages come from swebench's own
hand-maintained per-repo-version install specs (github.com/SWE-bench/
SWE-bench, swebench/harness/constants/python.py - used here only as a
data source, no Docker/harness code from that package is used) plus,
in a couple of cases, an additional pin found necessary by actually
running the instance on a modern machine (see devxdocs/agentlog.md for
what and why).

Only 3 tasks are curated here (of the 534 in SWE-bench Lite) - each one
individually verified end-to-end (environment installs cleanly, the
FAIL_TO_PASS tests genuinely fail before a fix and genuinely pass after
one) rather than a general "run any instance" loader, matching this
project's normal "narrow scope now, generalize later if needed" bias.
"""

import json
from dataclasses import dataclass
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "data"


@dataclass(frozen=True)
class BenchmarkTask:
    """One hand-verified SWE-bench Lite instance."""

    instance_id: str
    repo_url: str
    base_commit: str
    problem_statement: str
    test_patch: str
    fail_to_pass: list[str]
    pass_to_pass: list[str]
    python_version: str
    install_args: list[str]
    """Args after `pip install`, e.g. ["-e", "."] or ["."]."""
    pip_packages: list[str]
    """Exact pinned packages installed after install_args - order
    matters (later pins can correct versions the main install pulled in
    too loosely)."""
    pytest_args: list[str]
    """Extra pytest flags needed for this instance, e.g. disabling a
    plugin that's incompatible with a modern Python/package combo."""


def _load(instance_id: str, **overrides: object) -> BenchmarkTask:
    task_dir = _DATA_DIR / instance_id
    tests = json.loads((task_dir / "tests.json").read_text())
    return BenchmarkTask(
        instance_id=instance_id,
        problem_statement=(task_dir / "problem_statement.txt").read_text(),
        test_patch=(task_dir / "test_patch.diff").read_text(),
        fail_to_pass=tests["fail_to_pass"],
        pass_to_pass=tests["pass_to_pass"],
        **overrides,  # type: ignore[arg-type]
    )


TASKS: list[BenchmarkTask] = [
    _load(
        "pallets__flask-4045",
        repo_url="https://github.com/pallets/flask.git",
        base_commit="d8c37f43724cd9fb0870f77877b7c4c7e38a19e0",
        python_version="3.9",
        install_args=["-e", "."],
        pip_packages=[
            "setuptools==70.0.0",
            "Werkzeug==2.3.7",
            "Jinja2==3.0.1",
            "itsdangerous==2.1.2",
            "click==8.0.1",
            "MarkupSafe==2.1.3",
            "pytest==6.2.4",
            "asgiref==3.3.4",
            "python-dotenv==0.17.1",
            # blinker==1.4 (the repo's own pinned version at this commit)
            # fails to even import on a modern Python 3.9 patch release -
            # a SyntaxError from an unescaped backslash in a docstring
            # that only became a hard error in later 3.9.x. Found by
            # actually running this instance, not assumed.
            "blinker==1.6.2",
        ],
        pytest_args=[],
    ),
    _load(
        "psf__requests-3362",
        repo_url="https://github.com/psf/requests.git",
        base_commit="36453b95b13079296776d11b09cab2567ea3e703",
        python_version="3.9",
        install_args=["."],
        pip_packages=["pytest"],
        pytest_args=[],
    ),
    _load(
        "pylint-dev__pylint-5859",
        repo_url="https://github.com/pylint-dev/pylint.git",
        base_commit="182cc539b8154c0710fcea7e522267e42eba8899",
        python_version="3.9",
        install_args=["-e", ".[testutil]"],
        pip_packages=[
            "astroid==2.9.3",
            "pytest~=7.0",
            "pytest-benchmark~=3.4",
        ],
        # pytest-benchmark's bundled version here is incompatible with a
        # modern `py` package (AttributeError: module 'py' has no
        # attribute 'io') - the plugin isn't needed to run this specific
        # test, so it's simplest to just disable it, found the same way
        # as the blinker pin above: by actually running it.
        pytest_args=["-p", "no:benchmark"],
    ),
]
