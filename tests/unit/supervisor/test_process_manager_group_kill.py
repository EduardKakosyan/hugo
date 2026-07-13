"""Exercises the real OS-level group-kill guarantee (ADR 0002): killing a
recorded process group terminates every process in it, even ones spawned by
a process that has since died.

This spawns an isolated subprocess session (start_new_session=True) as a
stand-in "orchestrator", distinct from pytest's own process group, so the
group-kill under test can never reach the test runner itself.
"""

import os
import signal
import subprocess
import sys
import time

from hugo.supervisor.process_manager import kill_group

_ORCHESTRATOR_STANDIN = """
import subprocess, sys
children = [subprocess.Popen(["sleep", "100"]) for _ in range(2)]
print(" ".join(str(c.pid) for c in children), flush=True)
subprocess.Popen(["sleep", "100"]).wait()
"""


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_kill_group_terminates_orchestrator_and_all_its_children() -> None:
    standin = subprocess.Popen(
        [sys.executable, "-c", _ORCHESTRATOR_STANDIN],
        start_new_session=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert standin.stdout is not None
        child_pids = [int(p) for p in standin.stdout.readline().split()]
        assert len(child_pids) == 2
        pgid = standin.pid  # session leader's pgid == its own pid

        assert standin.poll() is None
        assert all(_pid_alive(pid) for pid in child_pids)

        kill_group(pgid, grace_period=2.0)

        # standin is pytest's own child, so checking liveness must go through
        # poll()/wait() to reap it — a plain os.kill(pid, 0) would still see
        # a terminated-but-unreaped zombie as "alive". The orphaned
        # grandchildren aren't pytest's children, so os.kill is fine for them.
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and (
            standin.poll() is None or any(_pid_alive(pid) for pid in child_pids)
        ):
            time.sleep(0.05)

        assert standin.poll() is not None
        assert not any(_pid_alive(pid) for pid in child_pids)
    finally:
        if standin.poll() is None:
            os.killpg(standin.pid, signal.SIGKILL)
        standin.wait(timeout=5)


def test_kill_group_is_a_noop_when_group_already_gone() -> None:
    standin = subprocess.Popen(
        [sys.executable, "-c", "pass"],
        start_new_session=True,
    )
    pgid = standin.pid
    standin.wait(timeout=5)  # already exited by the time we get here

    kill_group(pgid, grace_period=0.1)  # must not raise
