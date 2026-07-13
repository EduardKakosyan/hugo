"""Logic-only tests for ProcessManager's start/health-check/teardown behavior.

These tests mock out os.setpgid/os.getpgrp and subprocess creation entirely:
calling the real os.setpgid(0, 0) here would change *this test process's own*
process group, which would be dangerous if any test then killed that group.
The real, OS-level group-kill guarantee is exercised separately in
test_process_manager_group_kill.py against an isolated subprocess, never
against the pytest process itself.
"""

import asyncio
from pathlib import Path
from typing import Any

import pytest

from hugo.supervisor.pidfile import Pidfile
from hugo.supervisor.process_manager import HealthCheckFailed, ManagedProcessSpec, ProcessManager


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
def _isolate_process_group(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent start_all() from touching this test process's real group."""
    monkeypatch.setattr("hugo.supervisor.process_manager.os.setpgid", lambda pid, pgid: None)
    monkeypatch.setattr("hugo.supervisor.process_manager.os.getpgrp", lambda: 4242)


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
