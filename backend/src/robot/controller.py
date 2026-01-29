"""Thin wrapper around the Reachy Mini SDK."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np

from src.config import RobotSettings

logger = logging.getLogger(__name__)


class RobotController:
    """Manages connection and interaction with the Reachy Mini robot."""

    def __init__(self, config: RobotSettings) -> None:
        self._config = config
        self._mini: Any | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        """Connect to the Reachy Mini daemon."""
        try:
            from reachy_mini import ReachyMini

            self._mini = ReachyMini(
                host=self._config.host,
                port=self._config.port,
            )
            await asyncio.to_thread(self._mini.connect)
            self._connected = True
            logger.info(
                "Connected to Reachy Mini at %s:%d",
                self._config.host,
                self._config.port,
            )
        except Exception:
            logger.warning("Could not connect to Reachy Mini — running in disconnected mode")
            self._connected = False

    async def disconnect(self) -> None:
        """Disconnect from the robot."""
        if self._mini is not None:
            try:
                await asyncio.to_thread(self._mini.disconnect)
            except Exception:
                pass
            self._connected = False
            logger.info("Disconnected from Reachy Mini")

    async def get_state(self) -> dict[str, Any]:
        """Get current robot state (head angles, body yaw, etc.)."""
        if not self._connected or self._mini is None:
            return {"connected": False}
        try:
            state = await asyncio.to_thread(lambda: self._mini.state)
            return {
                "connected": True,
                "head": {
                    "roll": getattr(state, "roll", 0.0),
                    "pitch": getattr(state, "pitch", 0.0),
                    "yaw": getattr(state, "yaw", 0.0),
                },
            }
        except Exception:
            return {"connected": True, "error": "Failed to read state"}

    async def goto_target(
        self,
        roll: float = 0.0,
        pitch: float = 0.0,
        yaw: float = 0.0,
        duration: float = 1.0,
    ) -> None:
        """Move the robot head to target angles."""
        if not self._connected or self._mini is None:
            return
        await asyncio.to_thread(
            self._mini.head.goto,
            roll=roll,
            pitch=pitch,
            yaw=yaw,
            duration=duration,
        )

    async def set_target(self, roll: float = 0.0, pitch: float = 0.0, yaw: float = 0.0) -> None:
        """Set immediate head target (no interpolation)."""
        if not self._connected or self._mini is None:
            return
        await asyncio.to_thread(
            self._mini.head.set_target,
            roll=roll,
            pitch=pitch,
            yaw=yaw,
        )

    async def get_frame(self) -> np.ndarray | None:
        """Capture a frame from the robot's camera."""
        if not self._connected or self._mini is None:
            return None
        try:
            frame = await asyncio.to_thread(self._mini.media.get_frame)
            return frame
        except Exception:
            logger.warning("Failed to capture camera frame")
            return None

    async def get_audio(self) -> bytes | None:
        """Get audio data from the robot's microphone."""
        if not self._connected or self._mini is None:
            return None
        try:
            audio = await asyncio.to_thread(self._mini.media.get_audio)
            return audio
        except Exception:
            return None

    async def push_audio(self, audio_data: bytes) -> None:
        """Send audio data to the robot's speaker."""
        if not self._connected or self._mini is None:
            return
        try:
            await asyncio.to_thread(self._mini.media.push_audio, audio_data)
        except Exception:
            logger.warning("Failed to push audio to robot")
