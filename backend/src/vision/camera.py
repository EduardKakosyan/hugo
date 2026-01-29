"""Camera frame capture and streaming via the Reachy Mini SDK."""

from __future__ import annotations

import asyncio
import io
import logging

import numpy as np
from PIL import Image

from src.robot.controller import RobotController

logger = logging.getLogger(__name__)


class CameraStream:
    """Captures frames from the robot camera and encodes them for WebSocket streaming."""

    def __init__(self, robot: RobotController, quality: int = 80) -> None:
        self._robot = robot
        self._quality = quality
        self._running = False

    async def capture_jpeg(self) -> bytes | None:
        """Capture a single frame and encode as JPEG bytes."""
        frame = await self._robot.get_frame()
        if frame is None:
            return None
        return await asyncio.to_thread(self._encode_jpeg, frame)

    def _encode_jpeg(self, frame: np.ndarray) -> bytes:
        """Encode a numpy frame to JPEG bytes."""
        image = Image.fromarray(frame)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=self._quality)
        return buffer.getvalue()

    async def stream_frames(self, interval: float = 0.05) -> None:
        """Generator that yields JPEG frames at the specified interval.

        Default interval of 0.05s = 20 FPS.
        """
        self._running = True
        while self._running:
            frame_data = await self.capture_jpeg()
            if frame_data is not None:
                yield frame_data
            await asyncio.sleep(interval)

    def stop(self) -> None:
        """Stop the frame streaming loop."""
        self._running = False
