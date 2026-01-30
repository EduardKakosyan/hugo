"""Helpers for launching the Reachy Mini simulator daemon."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


class SimulatorManager:
    """Manages the Reachy Mini simulator daemon process."""

    def __init__(self) -> None:
        self._process: subprocess.Popen[Any] | None = None

    async def start(
        self, port: int = 8000, backend_port: int = 8080
    ) -> None:
        """Launch the simulator daemon with --sim flag.

        Args:
            port: The daemon's own FastAPI port.
            backend_port: The backend port the daemon streams video to.
        """
        if self._process is not None:
            logger.warning("Simulator already running")
            return

        self._process = await asyncio.to_thread(
            subprocess.Popen,
            [
                "reachy-mini-daemon",
                "--sim",
                "--headless",
                "--deactivate-audio",
                "--fastapi-port",
                str(port),
                "--websocket-uri",
                f"ws://localhost:{backend_port}",
                "--stream-media",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        pid = self._process.pid if self._process is not None else -1
        logger.info("Started Reachy Mini simulator on port %d (PID: %d)", port, pid)
        # Give the daemon a moment to initialize
        await asyncio.sleep(3)

    async def stop(self) -> None:
        """Stop the simulator daemon."""
        if self._process is None:
            return
        self._process.terminate()
        await asyncio.to_thread(self._process.wait, timeout=5)
        logger.info("Stopped Reachy Mini simulator")
        self._process = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None
