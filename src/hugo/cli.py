"""HUGO command-line entrypoint: `hugo start` / `hugo sleep` / `hugo stop`
/ `hugo status` / `hugo forget`."""

import asyncio
import os
import signal
import time

import typer

from hugo.config import load_config
from hugo.dev_cli import dev_app
from hugo.logging_setup import configure_logging
from hugo.supervisor.process_manager import kill_group

app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(dev_app, name="dev")


def _read_pid(pidfile_path: os.PathLike[str]) -> int | None:
    try:
        with open(pidfile_path) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but is owned by someone else — still running.
        return True
    return True


@app.command()
def status() -> None:
    """Report whether HUGO is currently running."""
    config = load_config()
    pid = _read_pid(config.pidfile_path)
    if pid is not None and _is_running(pid):
        typer.echo(f"hugo is running (pid {pid})")
        raise typer.Exit(code=0)
    typer.echo("hugo is not running")
    raise typer.Exit(code=1)


@app.command()
def start() -> None:
    """Load all models and start the voice loop (foreground)."""
    from hugo import orchestrator  # deferred: heavy import chain, only needed here

    config = load_config()
    configure_logging(config.log_level)
    asyncio.run(orchestrator.run(config))


@app.command()
def sleep(timeout: float = 90.0) -> None:
    """Gracefully put a running HUGO to sleep: models unload, memory is
    released, the robot moves to its rest posture. The CLI twin of the
    spoken "go to sleep" (CONTEXT.md: Sleep)."""
    config = load_config()
    configure_logging(config.log_level)
    pid = _read_pid(config.pidfile_path)
    if pid is None or not _is_running(pid):
        typer.echo("hugo is not running")
        raise typer.Exit(code=1)
    # SIGTERM to the orchestrator only (the pidfile holds its pid, which is
    # also the group id): its handler runs the full graceful path — rest
    # posture, then subprocess teardown. `hugo stop`'s group-kill remains
    # the hard safety net when this doesn't finish.
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _is_running(pid):
            typer.echo("hugo is asleep, all model memory released")
            return
        time.sleep(0.5)
    typer.echo("hugo did not shut down in time — try `hugo stop`")
    raise typer.Exit(code=1)


@app.command()
def stop() -> None:
    """Stop a running HUGO instance and release all model memory."""
    config = load_config()
    configure_logging(config.log_level)
    pid = _read_pid(config.pidfile_path)
    if pid is None:
        typer.echo("hugo is not running")
        raise typer.Exit(code=1)
    kill_group(pid)
    typer.echo("hugo stopped")


@app.command()
def forget(yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation.")) -> None:
    """Delete HUGO's persistent facts. Deliberate and explicit — sleep
    never does this (CONTEXT.md: Sleep clears the conversation only)."""
    config = load_config()
    pid = _read_pid(config.pidfile_path)
    if pid is not None and _is_running(pid):
        typer.echo("hugo is running — put it to sleep first (`hugo sleep`)")
        raise typer.Exit(code=1)
    db_path = config.memory_db_path
    if not db_path.exists():
        typer.echo("no persistent facts to forget")
        return
    if not yes:
        typer.confirm(f"Delete all persistent facts at {db_path}?", abort=True)
    db_path.unlink()
    typer.echo("all persistent facts forgotten")


if __name__ == "__main__":
    app()
