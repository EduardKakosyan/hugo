"""Thin wrapper around the Reachy Mini SDK."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np

from src.config import RobotSettings

logger = logging.getLogger(__name__)


def _rpy_to_pose(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """Build a 4x4 homogeneous pose matrix from roll/pitch/yaw in radians."""
    cr, sr = np.cos(roll), np.sin(roll)
    cp, sp = np.cos(pitch), np.sin(pitch)
    cy, sy = np.cos(yaw), np.sin(yaw)
    # ZYX Euler rotation
    r = np.array([
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp, cp * sr, cp * cr],
    ])
    pose = np.eye(4)
    pose[:3, :3] = r
    return pose


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
        self._media_available = False

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def media_available(self) -> bool:
        return self._media_available

    async def connect(self) -> None:
        """Connect to the Reachy Mini daemon by instantiating the SDK client."""
        try:
            from reachy_mini import ReachyMini

            connection_mode = "localhost_only" if self._config.simulation else "auto"
            media_backend = "no_media" if self._config.simulation else "default"

            self._mini = await asyncio.to_thread(
                ReachyMini,
                connection_mode=connection_mode,
                timeout=5.0,
                media_backend=media_backend,
            )
            self._connected = True
            self._media_available = media_backend != "no_media"
            logger.info(
                "Connected to Reachy Mini (simulation=%s, mode=%s, media=%s)",
                self._config.simulation,
                connection_mode,
                media_backend,
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
            pose_matrix = await asyncio.to_thread(self._mini.get_current_head_pose)
            # pose_matrix is a 4x4 homogeneous transformation matrix;
            # extract roll/pitch/yaw from the 3x3 rotation sub-matrix.
            r = pose_matrix[:3, :3]
            pitch = float(np.arcsin(-r[2, 0]))
            roll = float(np.arctan2(r[2, 1], r[2, 2]))
            yaw = float(np.arctan2(r[1, 0], r[0, 0]))
            return {
                "connected": True,
                "head": {
                    "roll": float(np.degrees(roll)),
                    "pitch": float(np.degrees(pitch)),
                    "yaw": float(np.degrees(yaw)),
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
        """Move the robot head to target angles (degrees) with interpolation."""
        if not self._connected or self._mini is None:
            return
        pose = _rpy_to_pose(np.radians(roll), np.radians(pitch), np.radians(yaw))
        await asyncio.to_thread(
            self._mini.goto_target,
            head=pose,
            duration=duration,
        )

    async def set_target(
        self, roll: float = 0.0, pitch: float = 0.0, yaw: float = 0.0
    ) -> None:
        """Set immediate head target (no interpolation). Angles in degrees."""
        if not self._connected or self._mini is None:
            return
        pose = _rpy_to_pose(np.radians(roll), np.radians(pitch), np.radians(yaw))
        await asyncio.to_thread(
            self._mini.set_target,
            head=pose,
        )

    async def get_frame(self) -> np.ndarray | None:
        """Capture a frame from the robot's camera."""
        if not self._connected or self._mini is None or not self._media_available:
            return None
        try:
            frame = await asyncio.to_thread(self._mini.media.get_frame)
            return frame
        except Exception as e:
            logger.warning("Failed to capture camera frame: %s", e)
            return None

    async def get_audio(self) -> bytes | np.ndarray | None:
        """Get audio sample from the robot's microphone."""
        if not self._connected or self._mini is None or not self._media_available:
            return None
        try:
            audio = await asyncio.to_thread(self._mini.media.get_audio_sample)
            return audio
        except Exception as e:
            logger.warning("Failed to capture audio from robot mic: %s", e)
            return None

    async def push_audio(self, audio_data: np.ndarray) -> None:
        """Send audio data to the robot's speaker."""
        if not self._connected or self._mini is None or not self._media_available:
            return
        try:
            await asyncio.to_thread(
                self._mini.media.push_audio_sample, audio_data
            )
        except Exception as e:
            logger.warning("Failed to push audio to robot speaker: %s", e)
