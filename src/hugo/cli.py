"""HUGO command-line entrypoint: `hugo start` / `hugo stop` / `hugo status`."""

import asyncio
import os

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


if __name__ == "__main__":
    app()
