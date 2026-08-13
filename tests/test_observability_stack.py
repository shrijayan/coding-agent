"""Tests for the local Docker observability stack helper
(observability_stack.py).

No real Docker, no real network: subprocess.run and urllib.request.urlopen
are monkeypatched so the branching logic (missing Docker, container
exists/running/neither, health-check timeout) is verified deterministically.
"""

import subprocess

import coding_agent.optimizations.observability_stack as stack


class _FakeCompletedProcess:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _fake_run_factory(*, docker_info_ok: bool, ps_stdout: str = "", ps_a_stdout: str = ""):
    """Builds a fake subprocess.run that dispatches on the docker
    subcommand, so each test only needs to describe what matters to it."""

    def _fake_run(command, **kwargs):
        if command[:2] == ["docker", "info"]:
            return _FakeCompletedProcess(returncode=0 if docker_info_ok else 1)
        if command[:3] == ["docker", "ps", "--filter"]:
            return _FakeCompletedProcess(stdout=ps_stdout)
        if command[:4] == ["docker", "ps", "-a", "--filter"]:
            return _FakeCompletedProcess(stdout=ps_a_stdout)
        if command[:2] == ["docker", "run"] or command[:2] == ["docker", "start"]:
            return _FakeCompletedProcess(returncode=0)
        raise AssertionError(f"unexpected command: {command}")

    return _fake_run


def _patch_docker_available(monkeypatch, available: bool) -> None:
    monkeypatch.setattr(stack.shutil, "which", lambda _name: "/usr/bin/docker" if available else None)


def _patch_healthy(monkeypatch, *, healthy: bool) -> None:
    class _FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _fake_urlopen(url, timeout=5):
        if healthy:
            return _FakeResponse()
        raise OSError("connection refused")

    monkeypatch.setattr(stack.urllib.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(stack.time, "sleep", lambda _seconds: None)


# --- Docker availability ---------------------------------------------------------


def test_returns_false_and_prints_guidance_when_docker_binary_missing(monkeypatch, capsys) -> None:
    _patch_docker_available(monkeypatch, available=False)

    assert stack.start_local_observability_stack() is False
    assert "Docker isn't available" in capsys.readouterr().out


def test_returns_false_when_docker_installed_but_not_running(monkeypatch, capsys) -> None:
    _patch_docker_available(monkeypatch, available=True)
    monkeypatch.setattr(
        subprocess, "run", _fake_run_factory(docker_info_ok=False)
    )
    monkeypatch.setattr(stack, "subprocess", subprocess)

    assert stack.start_local_observability_stack() is False
    assert "Docker isn't available" in capsys.readouterr().out


# --- Container start/reuse idempotency -------------------------------------------


def test_starts_a_fresh_container_when_none_exists(monkeypatch) -> None:
    _patch_docker_available(monkeypatch, available=True)
    calls = []

    def _fake_run(command, **kwargs):
        calls.append(command)
        if command[:2] == ["docker", "info"]:
            return _FakeCompletedProcess(returncode=0)
        if command[:3] == ["docker", "ps", "--filter"]:
            return _FakeCompletedProcess(stdout="")  # not running
        if command[:4] == ["docker", "ps", "-a", "--filter"]:
            return _FakeCompletedProcess(stdout="")  # doesn't exist at all
        if command[:2] == ["docker", "run"]:
            return _FakeCompletedProcess(returncode=0)
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(stack, "subprocess", _Module(_fake_run))
    _patch_healthy(monkeypatch, healthy=True)

    assert stack.start_local_observability_stack() is True
    assert any(c[:2] == ["docker", "run"] for c in calls)
    assert not any(c[:2] == ["docker", "start"] for c in calls)


def test_reuses_a_stopped_container_instead_of_creating_a_new_one(monkeypatch) -> None:
    _patch_docker_available(monkeypatch, available=True)
    calls = []

    def _fake_run(command, **kwargs):
        calls.append(command)
        if command[:2] == ["docker", "info"]:
            return _FakeCompletedProcess(returncode=0)
        if command[:3] == ["docker", "ps", "--filter"]:
            return _FakeCompletedProcess(stdout="")  # not currently running
        if command[:4] == ["docker", "ps", "-a", "--filter"]:
            return _FakeCompletedProcess(stdout=stack._CONTAINER_NAME)  # exists, stopped
        if command[:2] == ["docker", "start"]:
            return _FakeCompletedProcess(returncode=0)
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(stack, "subprocess", _Module(_fake_run))
    _patch_healthy(monkeypatch, healthy=True)

    assert stack.start_local_observability_stack() is True
    assert any(c[:2] == ["docker", "start"] for c in calls)
    assert not any(c[:2] == ["docker", "run"] for c in calls)


def test_skips_starting_anything_when_already_running(monkeypatch) -> None:
    _patch_docker_available(monkeypatch, available=True)
    calls = []

    def _fake_run(command, **kwargs):
        calls.append(command)
        if command[:2] == ["docker", "info"]:
            return _FakeCompletedProcess(returncode=0)
        if command[:3] == ["docker", "ps", "--filter"]:
            return _FakeCompletedProcess(stdout=stack._CONTAINER_NAME)  # already running
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(stack, "subprocess", _Module(_fake_run))
    _patch_healthy(monkeypatch, healthy=True)

    assert stack.start_local_observability_stack() is True
    assert not any(c[:2] in (["docker", "run"], ["docker", "start"]) for c in calls)


def test_sets_otlp_endpoint_env_var_on_success(monkeypatch) -> None:
    _patch_docker_available(monkeypatch, available=True)
    monkeypatch.setattr(
        stack,
        "subprocess",
        _Module(lambda command, **kwargs: _FakeCompletedProcess(
            returncode=0, stdout=stack._CONTAINER_NAME
        )),
    )
    _patch_healthy(monkeypatch, healthy=True)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    assert stack.start_local_observability_stack() is True
    assert stack.os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://localhost:4318"


# --- Health check timeout ---------------------------------------------------------


def test_returns_false_when_health_check_never_succeeds(monkeypatch, capsys) -> None:
    _patch_docker_available(monkeypatch, available=True)
    monkeypatch.setattr(
        stack,
        "subprocess",
        _Module(lambda command, **kwargs: _FakeCompletedProcess(
            returncode=0, stdout=stack._CONTAINER_NAME
        )),
    )
    _patch_healthy(monkeypatch, healthy=False)
    monkeypatch.setattr(stack, "_HEALTH_TIMEOUT_SECONDS", 0)

    assert stack.start_local_observability_stack() is False
    assert "never became healthy" in capsys.readouterr().out


class _Module:
    """A tiny stand-in for the `subprocess` module: only `.run` is ever
    called on it in observability_stack.py, so only that needs faking."""

    def __init__(self, run) -> None:
        self.run = run
