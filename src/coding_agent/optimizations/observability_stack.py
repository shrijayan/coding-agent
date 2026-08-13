"""Spin up (or reuse) a local, fully-isolated OTel + Grafana stack.

The advanced observability tier (optimizations/observability_otel.py) needs
somewhere to export traces/metrics/logs to. This module is the *local*
half of that: one Docker image, `grafana/otel-lgtm`, which already bundles
a Collector + Tempo (traces) + Prometheus (metrics) + Loki (logs) +
Grafana, all pre-wired to each other - no manual wiring of datasources.

Callable identically from a plain terminal script or a notebook cell under
Colab's "connect to local runtime" mode (see AGENTS.md's Observability
section for why hosted Colab can't reach this at all - there's no branch
for "hosted vs local" here, hosted Colab simply has no `docker` binary to
find, so the same check below naturally explains itself either way).

Never raises on a missing/unavailable Docker - that's an expected,
recoverable outcome (the whole point of the cloud path existing alongside
this one), not a bug. Prints clear, OS-aware guidance and returns False.
"""

import os
import platform
import shutil
import subprocess
import time
import urllib.error
import urllib.request

_CONTAINER_NAME = "coding-agent-otel"
_IMAGE = "grafana/otel-lgtm"
_GRAFANA_URL = "http://localhost:3000"
_OTLP_HTTP_ENDPOINT = "http://localhost:4318"
_HEALTH_URL = f"{_GRAFANA_URL}/api/health"
_HEALTH_TIMEOUT_SECONDS = 60
_HEALTH_POLL_INTERVAL_SECONDS = 2


def start_local_observability_stack() -> bool:
    """Ensure the local stack is running and export env vars pointing at
    it. Returns True if it's up and ready, False if Docker isn't
    available/running (with guidance already printed either way)."""
    if not _docker_available():
        _print_docker_missing_guidance()
        return False

    if not _container_running() and not _start_container():
        return False

    if not _wait_for_health():
        print(
            f"{_IMAGE} started but Grafana never became healthy at "
            f"{_HEALTH_URL} within {_HEALTH_TIMEOUT_SECONDS}s. Check "
            f"`docker logs {_CONTAINER_NAME}`."
        )
        return False

    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = _OTLP_HTTP_ENDPOINT
    print(
        f"Local observability stack ready.\n"
        f"  Grafana:       {_GRAFANA_URL}\n"
        f"  OTLP endpoint: {_OTLP_HTTP_ENDPOINT} (set for this process)\n"
        f"Now run with --enable observability-otel."
    )
    return True


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _container_running() -> bool:
    result = subprocess.run(
        ["docker", "ps", "--filter", f"name=^{_CONTAINER_NAME}$", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return _CONTAINER_NAME in result.stdout.split()


def _container_exists() -> bool:
    result = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"name=^{_CONTAINER_NAME}$", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return _CONTAINER_NAME in result.stdout.split()


def _start_container() -> bool:
    """Idempotent: reuses a stopped container if one already exists (e.g.
    from a previous run), otherwise creates a fresh one."""
    command = (
        ["docker", "start", _CONTAINER_NAME]
        if _container_exists()
        else [
            "docker", "run", "-d",
            "--name", _CONTAINER_NAME,
            "-p", "4317:4317",
            "-p", "4318:4318",
            "-p", "3000:3000",
            _IMAGE,
        ]
    )
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(f"Failed to start {_IMAGE}:\n{result.stderr.strip()}")
        return False
    return True


def _wait_for_health() -> bool:
    deadline = time.monotonic() + _HEALTH_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(_HEALTH_URL, timeout=5) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(_HEALTH_POLL_INTERVAL_SECONDS)
    return False


def _print_docker_missing_guidance() -> None:
    system = platform.system()
    if system == "Darwin":
        install = "https://docs.docker.com/desktop/setup/install/mac-install/"
    elif system == "Windows":
        install = "https://docs.docker.com/desktop/setup/install/windows-install/"
    else:
        install = "https://docs.docker.com/engine/install/"

    print(
        "Docker isn't available (or isn't running) here, so the local "
        "observability stack can't start.\n"
        f"  Install/start Docker for {system or 'your OS'}: {install}\n"
        "Alternatively, use the cloud path instead: sign up for a free "
        "Grafana Cloud stack and paste its OTEL_EXPORTER_OTLP_* values - "
        "see AGENTS.md's Observability section."
    )
