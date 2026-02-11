"""Reachy Mini robot controller — wraps the SDK for HUGO."""

from __future__ import annotations

import asyncio
import logging

import numpy as np

from src.models.schemas import Emotion, RobotState

logger = logging.getLogger(__name__)


class ReachyController:
    """High-level wrapper around the Reachy Mini SDK.

    Uses the `reachy-mini` package (ReachyMini class) for hardware control.
    Supports a simulation mode for development without hardware.
    """

    def __init__(self, host: str = "localhost", port: int = 50051, *, sim: bool = False) -> None:
        self._host = host
        self._port = port
        self._sim = sim
        self._robot: object | None = None
        self._state = RobotState()

    async def connect(self) -> None:
        """Connect to the Reachy Mini robot (or enter simulation mode)."""
        if self._sim:
            logger.info("Robot controller running in SIMULATION mode")
            self._state.connected = True
            return

        try:
            from reachy_mini import ReachyMini  # type: ignore[import-untyped]

            self._robot = ReachyMini()
            self._state.connected = True
            logger.info("Connected to Reachy Mini")
        except Exception:
            logger.exception("Failed to connect to Reachy Mini")
            raise

    async def disconnect(self) -> None:
        """Disconnect from the robot."""
        if self._robot is not None:
            try:
                if hasattr(self._robot, "disconnect"):
                    self._robot.disconnect()  # type: ignore[union-attr]
            except Exception:
                logger.exception("Error disconnecting from robot")
        self._state.connected = False
        logger.info("Disconnected from Reachy Mini")

    @property
    def state(self) -> RobotState:
        return self._state

    @property
    def is_sim(self) -> bool:
        return self._sim

    async def speak(self, text: str) -> None:
        """Make the robot 'speak' via its built-in TTS."""
        self._state.is_speaking = True
        self._state.is_idle = False

        if self._sim:
            logger.info("[SIM] Speaking: %s", text)
            await asyncio.sleep(len(text) * 0.03)  # Simulate speech duration
        else:
            if self._robot is not None and hasattr(self._robot, "say"):
                try:
                    self._robot.say(text)  # type: ignore[union-attr]
                except Exception:
                    logger.exception("Robot TTS failed")

        self._state.is_speaking = False
        self._state.is_idle = True

    async def look_at(self, x: float, y: float, z: float) -> None:
        """Move the robot's head to look at coordinates (x, y, z) in cm."""
        self._state.is_idle = False

        if self._sim:
            logger.info("[SIM] Looking at (%.2f, %.2f, %.2f)", x, y, z)
        else:
            if self._robot is not None and hasattr(self._robot, "head"):
                try:
                    self._robot.head.look_at(x, y, z)  # type: ignore[union-attr]
                except Exception:
                    logger.exception("Failed to move head")

        self._state.head_position = (x, y, z)
        self._state.is_idle = True

    async def express(self, emotion: Emotion) -> None:
        """Express an emotion through antenna animations."""
        self._state.current_emotion = emotion

        if self._sim:
            logger.info("[SIM] Expressing: %s", emotion.value)
            await asyncio.sleep(0.5)
            return

        if self._robot is not None and hasattr(self._robot, "antennas"):
            try:
                antennas = self._robot.antennas  # type: ignore[union-attr]
                if emotion == Emotion.HAPPY:
                    antennas.happy()  # type: ignore[union-attr]
                elif emotion == Emotion.SAD:
                    antennas.sad()  # type: ignore[union-attr]
                elif emotion == Emotion.THINKING:
                    # Tilt head slightly to simulate thinking
                    await self.look_at(0.5, 3.0, 0.0)
                elif emotion == Emotion.WIGGLE:
                    # Use goto_target for a fun wiggle
                    if hasattr(self._robot, "goto_target"):
                        for _ in range(3):
                            self._robot.goto_target(  # type: ignore[union-attr]
                                antennas=[0.5, -0.5], duration=0.15
                            )
                            await asyncio.sleep(0.2)
                            self._robot.goto_target(  # type: ignore[union-attr]
                                antennas=[-0.5, 0.5], duration=0.15
                            )
                            await asyncio.sleep(0.2)
                        self._robot.goto_target(  # type: ignore[union-attr]
                            antennas=[0, 0], duration=0.3
                        )
                elif emotion == Emotion.SURPRISED and hasattr(self._robot, "goto_target"):
                    self._robot.goto_target(  # type: ignore[union-attr]
                        antennas=[0.7, 0.7], duration=0.2
                    )
                    await asyncio.sleep(0.5)
                    self._robot.goto_target(  # type: ignore[union-attr]
                        antennas=[0, 0], duration=0.5
                    )
            except Exception:
                logger.exception("Failed to express emotion")

    async def rotate(self, degrees: float) -> None:
        """Rotate the robot's body by the given degrees."""
        if self._sim:
            logger.info("[SIM] Rotating %.1f degrees", degrees)
            return

        if self._robot is not None and hasattr(self._robot, "goto_target"):
            try:
                self._robot.goto_target(  # type: ignore[union-attr]
                    body_yaw=np.deg2rad(degrees), duration=1.0
                )
            except Exception:
                logger.exception("Failed to rotate")

    async def capture_frame(self) -> bytes | None:
        """Capture a frame from the robot's camera. Returns JPEG bytes."""
        if self._sim:
            logger.info("[SIM] Capturing frame (returning None in sim mode)")
            return None

        if self._robot is not None and hasattr(self._robot, "media"):
            try:
                import io

                from PIL import Image  # type: ignore[import-untyped]

                frame = self._robot.media.get_frame()  # type: ignore[union-attr]
                if frame is not None:
                    img = Image.fromarray(np.array(frame))
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG")
                    return buf.getvalue()
            except Exception:
                logger.exception("Failed to capture frame")
        return None

    async def idle_animation(self) -> None:
        """Run a gentle idle animation (subtle head movements)."""
        if not self._state.is_idle:
            return

        if self._sim:
            logger.debug("[SIM] Idle animation tick")
            return

        import random

        x = random.uniform(-1.0, 1.0)
        y = random.uniform(-1.0, 1.0)
        await self.look_at(x, y, 30.0)
