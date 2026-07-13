"""Tracks the orchestrator's process group ID on disk so a later `hugo stop`
(possibly a fresh process, e.g. after a crash) can recover and kill it."""

from pathlib import Path


class Pidfile:
    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, pgid: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(str(pgid))

    def read(self) -> int | None:
        try:
            return int(self.path.read_text().strip())
        except (FileNotFoundError, ValueError):
            return None

    def remove(self) -> None:
        self.path.unlink(missing_ok=True)
