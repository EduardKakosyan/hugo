"""Logic-only tests for ProcessManager's start/health-check/teardown behavior.

These tests mock out os.setpgid/os.getpgrp and subprocess creation entirely:
calling the real os.setpgid(0, 0) here would change *this test process's own*
process group, which would be dangerous if any test then killed that group.
The real, OS-level group-kill guarantee is exercised separately in
test_process_manager_group_kill.py against an isolated subprocess, never
against the pytest process itself.
"""

import asyncio
import signal
from pathlib import Path
from typing import Any

import pytest

from hugo.supervisor.pidfile import Pidfile
from hugo.supervisor.process_manager import (
    HealthCheckFailed,
    ManagedProcessSpec,
    ProcessDied,
    ProcessManager,
)


class FakeProcess:
    """returncode only becomes non-None once the process has actually been
    observed to exit (via wait()), matching real asyncio.subprocess.Process
    semantics — terminate() sending SIGTERM does not itself guarantee exit."""

    def __init__(self) -> None:
        self.returncode: int | None = None
        self.terminated = False
        self.killed = False

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    async def wait(self) -> int:
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


@pytest.fixture(autouse=True)
def _isolate_process_group(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, int]]:
    """Prevent start_all()/stop_all() from touching this test process's real
    group — including the group-wide killpg sweep stop_all() now does,
    which would otherwise call the real os.killpg(4242, ...) using this
    fixture's fake pgid. killpg_calls records (pgid, sig) for tests that
    want to assert the sweep happened, without it ever executing for real."""
    killpg_calls: list[tuple[int, int]] = []
    monkeypatch.setattr("hugo.supervisor.process_manager.os.setpgid", lambda pid, pgid: None)
    monkeypatch.setattr("hugo.supervisor.process_manager.os.getpgrp", lambda: 4242)
    monkeypatch.setattr(
        "hugo.supervisor.process_manager.os.killpg",
        lambda pgid, sig: killpg_calls.append((pgid, sig)),
    )
    return killpg_calls


@pytest.fixture
def fake_processes(monkeypatch: pytest.MonkeyPatch) -> list[FakeProcess]:
    created: list[FakeProcess] = []

    async def fake_create_subprocess_exec(*_command: str, **_kwargs: Any) -> FakeProcess:
        proc = FakeProcess()
        created.append(proc)
        return proc

    monkeypatch.setattr(
        "hugo.supervisor.process_manager.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )
    return created


async def test_start_all_writes_pgid_to_pidfile(
    tmp_path: Path, fake_processes: list[FakeProcess]
) -> None:
    manager = ProcessManager(pidfile=Pidfile(tmp_path / "hugo.pid"))

    await manager.start_all([ManagedProcessSpec(name="a", command=["true"])])

    assert manager.pidfile.read() == 4242


async def test_start_all_waits_for_health_check_to_pass(
    tmp_path: Path, fake_processes: list[FakeProcess]
) -> None:
    attempts = 0

    async def health_check() -> bool:
        nonlocal attempts
        attempts += 1
        return attempts >= 3

    manager = ProcessManager(pidfile=Pidfile(tmp_path / "hugo.pid"))

    await manager.start_all(
        [
            ManagedProcessSpec(
                name="slow-to-boot",
                command=["true"],
                health_check=health_check,
                health_check_interval=0.001,
            )
        ]
    )

    assert attempts == 3


async def test_after_healthy_runs_between_this_spec_and_the_next(
    tmp_path: Path, fake_processes: list[FakeProcess]
) -> None:
    order: list[str] = []

    async def healthy() -> bool:
        order.append("health")
        return True

    async def after_healthy() -> None:
        order.append("after_healthy")

    async def second_health() -> bool:
        order.append("second-spec-health")
        return True

    manager = ProcessManager(pidfile=Pidfile(tmp_path / "hugo.pid"))
    await manager.start_all(
        [
            ManagedProcessSpec(
                name="a", command=["true"], health_check=healthy, after_healthy=after_healthy
            ),
            ManagedProcessSpec(name="b", command=["true"], health_check=second_health),
        ]
    )

    # The hook (page-cache eviction in production) must complete before the
    # next spec starts loading its model — that ordering IS the fix.
    assert order == ["health", "after_healthy", "second-spec-health"]


async def test_failed_health_check_tears_down_already_started_processes(
    tmp_path: Path, fake_processes: list[FakeProcess]
) -> None:
    manager = ProcessManager(pidfile=Pidfile(tmp_path / "hugo.pid"))

    with pytest.raises(HealthCheckFailed):
        await manager.start_all(
            [
                ManagedProcessSpec(name="starts-fine", command=["true"]),
                ManagedProcessSpec(
                    name="never-healthy",
                    command=["true"],
                    health_check=lambda: _never(),
                    health_check_timeout=0.02,
                    health_check_interval=0.005,
                ),
            ]
        )

    assert all(proc.terminated for proc in fake_processes)
    assert manager.pidfile.read() is None


async def test_extra_env_is_merged_onto_the_current_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # extra_env should extend, not replace, the orchestrator's own
    # environment — e.g. capping MAX_JOBS for vLLM's flashinfer JIT
    # compilation without losing PATH, HOME, etc.
    monkeypatch.setenv("SOME_EXISTING_VAR", "still-here")
    captured_env: dict[str, str] | None = None

    async def fake_create_subprocess_exec(*_command: str, **kwargs: Any) -> FakeProcess:
        nonlocal captured_env
        captured_env = kwargs.get("env")
        return FakeProcess()

    monkeypatch.setattr(
        "hugo.supervisor.process_manager.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    manager = ProcessManager(pidfile=Pidfile(tmp_path / "hugo.pid"))
    await manager.start_all(
        [ManagedProcessSpec(name="a", command=["true"], extra_env={"MAX_JOBS": "4"})]
    )

    assert captured_env is not None
    assert captured_env["MAX_JOBS"] == "4"
    assert captured_env["SOME_EXISTING_VAR"] == "still-here"


async def test_no_extra_env_leaves_env_kwarg_as_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured_kwargs: dict[str, Any] = {}

    async def fake_create_subprocess_exec(*_command: str, **kwargs: Any) -> FakeProcess:
        captured_kwargs.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr(
        "hugo.supervisor.process_manager.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    manager = ProcessManager(pidfile=Pidfile(tmp_path / "hugo.pid"))
    await manager.start_all([ManagedProcessSpec(name="a", command=["true"])])

    assert captured_kwargs["env"] is None


async def test_dead_process_fails_fast_instead_of_polling_full_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Regression test for a real bug found on real hardware: vLLM crashed
    # immediately (port collision with an unrelated server), but the health
    # check kept innocuously polling — hitting the *other* server on the
    # same port and getting 404s — for the full 30-minute timeout budget,
    # never noticing the actual vLLM subprocess had already died.
    manager = ProcessManager(pidfile=Pidfile(tmp_path / "hugo.pid"))

    async def always_false_health_check() -> bool:
        return False

    async def fake_create_subprocess_exec(*_command: str, **_kwargs: object) -> FakeProcess:
        proc = FakeProcess()
        proc.returncode = 1  # already dead by the time health-checking starts
        return proc

    monkeypatch.setattr(
        "hugo.supervisor.process_manager.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    with pytest.raises(ProcessDied) as exc_info:
        await manager.start_all(
            [
                ManagedProcessSpec(
                    name="crashes-immediately",
                    command=["true"],
                    health_check=always_false_health_check,
                    health_check_timeout=999.0,  # would hang for ~17 min if not fixed
                    health_check_interval=0.001,
                )
            ]
        )

    assert exc_info.value.name == "crashes-immediately"
    assert exc_info.value.returncode == 1


async def test_stop_all_terminates_in_reverse_order_then_clears_pidfile(
    tmp_path: Path, fake_processes: list[FakeProcess]
) -> None:
    manager = ProcessManager(pidfile=Pidfile(tmp_path / "hugo.pid"))
    await manager.start_all(
        [
            ManagedProcessSpec(name="first", command=["true"]),
            ManagedProcessSpec(name="second", command=["true"]),
        ]
    )

    await manager.stop_all()

    assert all(proc.terminated for proc in fake_processes)
    assert not any(proc.killed for proc in fake_processes)
    assert manager.pidfile.read() is None


async def test_stop_all_sweeps_the_whole_process_group(
    tmp_path: Path,
    fake_processes: list[FakeProcess],
    _isolate_process_group: list[tuple[int, int]],
) -> None:
    # Regression test for a real bug found on real hardware: vLLM spawns
    # its own "EngineCore" child process that outlived its terminated
    # parent (reparented to init), still holding ~70GB of GPU memory —
    # per-proc terminate()/kill() only reaches the top-level process we
    # spawned directly, not that kind of descendant. stop_all() must also
    # sweep the whole process group unconditionally.
    manager = ProcessManager(pidfile=Pidfile(tmp_path / "hugo.pid"))
    await manager.start_all([ManagedProcessSpec(name="a", command=["true"])])

    await manager.stop_all()

    assert (4242, signal.SIGKILL) in _isolate_process_group


async def test_stop_all_escalates_to_kill_for_stragglers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stuck = FakeProcess()

    async def fake_terminate_then_never_exit() -> int:
        await asyncio.sleep(999)
        return 0

    stuck.wait = fake_terminate_then_never_exit  # type: ignore[method-assign]

    async def fake_create_subprocess_exec(*_command: str, **_kwargs: Any) -> FakeProcess:
        return stuck

    monkeypatch.setattr(
        "hugo.supervisor.process_manager.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    manager = ProcessManager(pidfile=Pidfile(tmp_path / "hugo.pid"))
    await manager.start_all([ManagedProcessSpec(name="stuck", command=["true"])])

    await manager.stop_all(grace_period=0.02)

    assert stuck.terminated
    assert stuck.killed


async def _never() -> bool:
    return False
