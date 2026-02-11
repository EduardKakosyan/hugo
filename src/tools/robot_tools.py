"""CrewAI tools for robot interaction."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from crewai.tools import BaseTool  # type: ignore[import-untyped]
from pydantic import Field

if TYPE_CHECKING:
    from src.robot.controller import ReachyController

# Module-level reference set by the flow at startup
_controller: ReachyController | None = None


def set_controller(controller: ReachyController) -> None:
    """Set the global robot controller reference."""
    global _controller
    _controller = controller


def _get_controller() -> ReachyController:
    if _controller is None:
        msg = "Robot controller not initialized. Call set_controller() first."
        raise RuntimeError(msg)
    return _controller


class SpeakTool(BaseTool):  # type: ignore[misc]
    """Make the robot speak a text aloud."""

    name: str = "speak"
    description: str = "Make the robot speak the given text aloud via TTS."

    text: str = Field(default="", description="Text to speak")

    def _run(self, text: str = "", **kwargs: Any) -> str:
        import asyncio

        controller = _get_controller()
        asyncio.get_event_loop().run_until_complete(controller.speak(text))
        return f"Spoke: {text}"


class LookAtTool(BaseTool):  # type: ignore[misc]
    """Direct the robot's gaze to specific coordinates."""

    name: str = "look_at"
    description: str = (
        "Move the robot's head to look at (x, y, z) coordinates. "
        "x=forward distance, y=left-right, z=up-down."
    )

    def _run(self, x: float = 0.5, y: float = 0.0, z: float = 0.0, **kwargs: Any) -> str:
        import asyncio

        controller = _get_controller()
        asyncio.get_event_loop().run_until_complete(controller.look_at(x, y, z))
        return f"Looking at ({x}, {y}, {z})"


class ExpressTool(BaseTool):  # type: ignore[misc]
    """Express an emotion through robot body language."""

    name: str = "express"
    description: str = (
        "Express an emotion on the robot. "
        "Valid emotions: happy, sad, thinking, surprised, neutral, wiggle."
    )

    def _run(self, emotion: str = "neutral", **kwargs: Any) -> str:
        import asyncio

        from src.models.schemas import Emotion

        controller = _get_controller()
        emo = Emotion(emotion.lower())
        asyncio.get_event_loop().run_until_complete(controller.express(emo))
        return f"Expressing: {emotion}"


class RotateTool(BaseTool):  # type: ignore[misc]
    """Rotate the robot's head."""

    name: str = "rotate"
    description: str = (
        "Rotate the robot's head by the given degrees (positive = right, negative = left)."
    )

    def _run(self, degrees: float = 0.0, **kwargs: Any) -> str:
        import asyncio

        controller = _get_controller()
        asyncio.get_event_loop().run_until_complete(controller.rotate(degrees))
        return f"Rotated {degrees} degrees"
