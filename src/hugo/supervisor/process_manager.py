"""Spawns and supervises HUGO's model-serving subprocesses.

Every large memory holder (vLLM, STT, TTS, VLM) runs as its own OS process so
that killing the process is a hard guarantee of memory release, even if the
orchestrator itself has already crashed (see docs/adr/0002). The orchestrator
makes itself the leader of a fresh process group on start; every subprocess it
spawns inherits that group automatically. `kill_group` is the safety net a
*different* process (a fresh `hugo stop` invocation, or a teammate) can use to
recover the machine even if the orchestrator that started the group is gone.
"""

import asyncio
import contextlib
import os
import signal
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from hugo.supervisor.pidfile import Pidfile

HealthCheck = Callable[[], Awaitable[bool]]


@dataclass(frozen=True)
class ManagedProcessSpec:
    name: str
    command: list[str]
    health_check: HealthCheck | None = None
    health_check_timeout: float = 30.0
    health_check_interval: float = 0.5


class HealthCheckFailed(RuntimeError):
    def __init__(self, name: str) -> None:
        super().__init__(f"{name} failed to become healthy")
        self.name = name


@dataclass
class ProcessManager:
    pidfile: Pidfile
    _processes: list[tuple[str, asyncio.subprocess.Process]] = field(default_factory=list)

    async def start_all(self, specs: list[ManagedProcessSpec]) -> None:
        """Become our own process group leader, then spawn and health-check
        each spec in order. Tears down everything already started if any
        spec fails, so a partial start never leaks subprocesses."""
        os.setpgid(0, 0)
        self.pidfile.write(os.getpgrp())

        try:
            for spec in specs:
                proc = await asyncio.create_subprocess_exec(*spec.command)
                self._processes.append((spec.name, proc))
                if spec.health_check is not None and not await self._wait_healthy(spec):
                    raise HealthCheckFailed(spec.name)
        except Exception:
            await self.stop_all()
            raise

    async def stop_all(self, grace_period: float = 10.0) -> None:
        """Graceful shutdown: SIGTERM everything in reverse start order,
        wait, then SIGKILL any stragglers."""
        for _name, proc in reversed(self._processes):
            if proc.returncode is None:
                proc.terminate()
        await self._wait_all_exited(grace_period)

        for _name, proc in reversed(self._processes):
            if proc.returncode is None:
                proc.kill()
        await self._wait_all_exited(grace_period)

        self._processes.clear()
        self.pidfile.remove()

    async def _wait_healthy(self, spec: ManagedProcessSpec) -> bool:
        deadline = asyncio.get_running_loop().time() + spec.health_check_timeout
        while asyncio.get_running_loop().time() < deadline:
            if await spec.health_check():  # type: ignore[misc]
                return True
            await asyncio.sleep(spec.health_check_interval)
        return False

    async def _wait_all_exited(self, grace_period: float) -> None:
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(grace_period):
                for _name, proc in self._processes:
                    if proc.returncode is None:
                        await proc.wait()


def kill_group(pgid: int, grace_period: float = 10.0) -> None:
    """Synchronous safety net for a process group whose original owner may
    no longer be alive. Used by `hugo stop` when reading a pidfile left
    behind by a crashed orchestrator, or by a teammate reclaiming the box."""
    if not _group_has_members(pgid):
        return
    _safe_killpg(pgid, signal.SIGTERM)

    deadline = time.monotonic() + grace_period
    while time.monotonic() < deadline:
        if not _group_has_members(pgid):
            return
        time.sleep(0.2)

    _safe_killpg(pgid, signal.SIGKILL)


def _safe_killpg(pgid: int, sig: signal.Signals) -> None:
    # ProcessLookupError means the group is already gone — nothing to do.
    # PermissionError can occur transiently (observed on macOS) while a
    # group is mid-teardown; treat it the same way rather than crash, since
    # this function is a best-effort safety net, not a guaranteed-delivery
    # primitive — matches the PermissionError-means-still-there reasoning
    # in cli.py's _is_running.
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pgid, sig)


def _group_has_members(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
