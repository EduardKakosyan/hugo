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
    # Extra env vars merged on top of the orchestrator's own environment
    # (not a full replacement) — e.g. capping MAX_JOBS for vLLM's flashinfer
    # JIT kernel compilation, which otherwise defaults to nproc parallel
    # nvcc jobs and can OOM the system while a large model is also loading.
    extra_env: dict[str, str] | None = None
    # Runs after this process passes its health check, before the next spec
    # starts — e.g. evicting vLLM's checkpoint from the page cache so the
    # STT model's CUDA load doesn't OOM (see supervisor/page_cache.py).
    after_healthy: Callable[[], Awaitable[None]] | None = None


class HealthCheckFailed(RuntimeError):
    def __init__(self, name: str) -> None:
        super().__init__(f"{name} failed to become healthy")
        self.name = name


class ProcessDied(RuntimeError):
    def __init__(self, name: str, returncode: int) -> None:
        super().__init__(f"{name} exited (code {returncode}) before becoming healthy")
        self.name = name
        self.returncode = returncode


@dataclass
class ProcessManager:
    pidfile: Pidfile
    _processes: list[tuple[str, asyncio.subprocess.Process]] = field(default_factory=list)
    _pgid: int | None = None

    async def start_all(self, specs: list[ManagedProcessSpec]) -> None:
        """Spawn and health-check each spec strictly in order — a sequence
        of single-spec stages."""
        await self.start_stages([[spec] for spec in specs])

    async def start_stages(self, stages: list[list[ManagedProcessSpec]]) -> None:
        """Become our own process group leader, then bring up each stage:
        every spec within a stage spawns and health-checks concurrently
        (VEN-56 startup overlap — STT and TTS load together instead of
        back to back), and the next stage starts only once the whole stage
        is healthy. Tears down everything already started if anything
        fails, so a partial start never leaks subprocesses (ADR 0002)."""
        try:
            os.setpgid(0, 0)
        except PermissionError:
            # EPERM means we're a session leader (systemd service, setsid
            # wrapper — a real crash on dgx1, 2026-07-23). A session
            # leader is already its own process-group leader, which is
            # all this needs.
            pass
        self._pgid = os.getpgrp()
        self.pidfile.write(self._pgid)

        try:
            for stage in stages:
                started: list[tuple[ManagedProcessSpec, asyncio.subprocess.Process]] = []
                for spec in stage:
                    env = {**os.environ, **spec.extra_env} if spec.extra_env else None
                    proc = await asyncio.create_subprocess_exec(*spec.command, env=env)
                    self._processes.append((spec.name, proc))
                    started.append((spec, proc))
                try:
                    async with asyncio.TaskGroup() as group:
                        for spec, proc in started:
                            group.create_task(self._bring_up(spec, proc))
                except BaseExceptionGroup as eg:
                    # Callers (and the existing tests) expect the plain
                    # HealthCheckFailed/ProcessDied, not an ExceptionGroup.
                    raise eg.exceptions[0] from eg
        except Exception:
            await self.stop_all()
            raise

    async def _bring_up(self, spec: ManagedProcessSpec, proc: asyncio.subprocess.Process) -> None:
        if spec.health_check is not None and not await self._wait_healthy(spec, proc):
            raise HealthCheckFailed(spec.name)
        if spec.after_healthy is not None:
            await spec.after_healthy()

    async def stop_all(self, grace_period: float = 10.0) -> None:
        """Graceful shutdown: SIGTERM everything in reverse start order,
        wait, then SIGKILL any stragglers. Finishes with a group-wide
        SIGKILL sweep regardless — confirmed necessary on real hardware:
        vLLM spawns its own "EngineCore" child process that isn't reliably
        reachable by signaling just the top-level proc we tracked (observed
        directly: an EngineCore process outlived its terminated parent,
        reparented to init, still holding ~70GB of GPU memory). Per-proc
        signaling only reaches processes we spawned directly; the group
        sweep catches any descendant that inherited our process group
        without us tracking it individually — see docs/adr/0002."""
        for _name, proc in reversed(self._processes):
            if proc.returncode is None:
                proc.terminate()
        await self._wait_all_exited(grace_period)

        for _name, proc in reversed(self._processes):
            if proc.returncode is None:
                proc.kill()
        await self._wait_all_exited(grace_period)

        if self._pgid is not None:
            _safe_killpg(self._pgid, signal.SIGKILL)

        self._processes.clear()
        self.pidfile.remove()

    async def _wait_healthy(
        self, spec: ManagedProcessSpec, proc: asyncio.subprocess.Process
    ) -> bool:
        """Polls the health check until it passes or health_check_timeout
        elapses. Fails fast with ProcessDied if the subprocess exits in the
        meantime, rather than polling a dead target for the full timeout —
        confirmed as a real gap: vLLM crashing immediately on a port
        collision was masked by the health check innocuously 404ing against
        an unrelated server on the same port for the full 30-minute budget."""
        deadline = asyncio.get_running_loop().time() + spec.health_check_timeout
        while asyncio.get_running_loop().time() < deadline:
            if proc.returncode is not None:
                raise ProcessDied(spec.name, proc.returncode)
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
