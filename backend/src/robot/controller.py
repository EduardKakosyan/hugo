"""Thin wrapper around the Reachy Mini SDK."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np

from src.config import RobotSettings

logger = logging.getLogger(__name__)


class RobotController:
    """Manages connection and interaction with the Reachy Mini robot.

    The ReachyMini SDK auto-connects in the constructor.
    The constructor takes connection_mode, use_sim, spawn_daemon, etc.
    There is no separate connect()/disconnect() — instantiation IS connection.
    """

    def __init__(self, config: RobotSettings) -> None:
        self._config = config
        self._mini: Any | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        """Connect to the Reachy Mini daemon by instantiating the SDK client."""
        try:
            from reachy_mini import ReachyMini

            connection_mode = "localhost_only" if self._config.simulation else "auto"

            self._mini = await asyncio.to_thread(
                ReachyMini,
                connection_mode=connection_mode,
                timeout=5.0,
            )
            self._connected = True
            logger.info(
                "Connected to Reachy Mini (simulation=%s, mode=%s)",
                self._config.simulation,
                connection_mode,
            )
        except Exception as e:
            logger.warning(
                "Could not connect to Reachy Mini — running in disconnected mode: %s",
                e,
            )
            self._connected = False

    async def disconnect(self) -> None:
        """Disconnect from the robot."""
        if self._mini is not None:
            try:
                if hasattr(self._mini, "media") and self._mini.media:
                    await asyncio.to_thread(self._mini.media.close)
            except Exception as e:
                logger.warning("Error closing Reachy Mini media: %s", e)
            self._mini = None
            self._connected = False
            logger.info("Disconnected from Reachy Mini")

    async def get_state(self) -> dict[str, Any]:
        """Get current robot state (head pose as roll/pitch/yaw)."""
        if not self._connected or self._mini is None:
            return {"connected": False}
        try:
            pose = await asyncio.to_thread(self._mini.get_current_head_pose)
            # pose is a numpy array [roll, pitch, yaw] in radians
            return {
                "connected": True,
                "head": {
                    "roll": float(np.degrees(pose[0])),
                    "pitch": float(np.degrees(pose[1])),
                    "yaw": float(np.degrees(pose[2])),
                },
            }
        except Exception as e:
            logger.error("Failed to read robot state: %s", e)
            return {"connected": True, "error": f"Failed to read state: {e}"}

    async def goto_target(
        self,
        roll: float = 0.0,
        pitch: float = 0.0,
        yaw: float = 0.0,
        duration: float = 0.5,
    ) -> None:
        """Move the robot head to target angles (degrees)."""
        if not self._connected or self._mini is None:
            return
        head_target = np.radians([roll, pitch, yaw]).astype(np.float64)
        await asyncio.to_thread(
            self._mini.goto_target,
            head=head_target,
            duration=duration,
        )

    async def set_target(
        self, roll: float = 0.0, pitch: float = 0.0, yaw: float = 0.0
    ) -> None:
        """Set immediate head target (no interpolation). Angles in degrees."""
        if not self._connected or self._mini is None:
            return
        head_target = np.radians([roll, pitch, yaw]).astype(np.float64)
        await asyncio.to_thread(
            self._mini.set_target,
            head=head_target,
        )

    async def get_frame(self) -> np.ndarray | None:
        """Capture a frame from the robot's camera."""
        if not self._connected or self._mini is None:
            return None
        try:
            frame = await asyncio.to_thread(self._mini.media.get_frame)
            return frame
        except Exception as e:
            logger.warning("Failed to capture camera frame: %s", e)
            return None

    async def get_audio(self) -> bytes | np.ndarray | None:
        """Get audio sample from the robot's microphone."""
        if not self._connected or self._mini is None:
            return None
        try:
            audio = await asyncio.to_thread(self._mini.media.get_audio_sample)
            return audio
        except Exception as e:
            logger.warning("Failed to capture audio from robot mic: %s", e)
            return None

    async def push_audio(self, audio_data: np.ndarray) -> None:
        """Send audio data to the robot's speaker."""
        if not self._connected or self._mini is None:
            return
        try:
            await asyncio.to_thread(
                self._mini.media.push_audio_sample, audio_data
            )
        except Exception as e:
            logger.warning("Failed to push audio to robot speaker: %s", e)
