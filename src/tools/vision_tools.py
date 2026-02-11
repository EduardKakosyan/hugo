"""CrewAI tools for vision (camera capture + VLM analysis)."""

from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING, Any

from crewai.tools import BaseTool  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from src.robot.controller import ReachyController

logger = logging.getLogger(__name__)

_controller: ReachyController | None = None
_vlm_model: object | None = None
_vlm_processor: object | None = None


def set_controller(controller: ReachyController) -> None:
    """Set the global robot controller for camera access."""
    global _controller
    _controller = controller


def _get_controller() -> ReachyController:
    if _controller is None:
        msg = "Robot controller not initialized."
        raise RuntimeError(msg)
    return _controller


def load_vlm(model_path: str = "Qwen/Qwen2.5-VL-7B-Instruct-4bit") -> None:
    """Load the Vision Language Model via MLX (lazy, called once)."""
    global _vlm_model, _vlm_processor
    if _vlm_model is not None:
        return
    try:
        from mlx_vlm import load  # type: ignore[import-untyped]

        _vlm_model, _vlm_processor = load(model_path)
        logger.info("VLM loaded: %s", model_path)
    except Exception:
        logger.exception("Failed to load VLM model")
        raise


def describe_image(image_bytes: bytes, prompt: str = "Describe what you see.") -> str:
    """Run VLM inference on image bytes. Returns text description."""
    if _vlm_model is None or _vlm_processor is None:
        load_vlm()

    try:
        from mlx_vlm import generate  # type: ignore[import-untyped]

        # Encode image to base64 for the VLM
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        image_uri = f"data:image/jpeg;base64,{b64}"

        result: str = generate(
            _vlm_model,
            _vlm_processor,
            prompt=prompt,
            image=image_uri,
            max_tokens=512,
        )
        return result
    except Exception:
        logger.exception("VLM inference failed")
        return "Vision analysis failed."


class CaptureFrameTool(BaseTool):  # type: ignore[misc]
    """Capture a frame from the robot's camera."""

    name: str = "capture_frame"
    description: str = (
        "Capture a photo from the robot's camera and return it as base64-encoded JPEG."
    )

    def _run(self, **kwargs: Any) -> str:
        import asyncio

        controller = _get_controller()
        frame = asyncio.get_event_loop().run_until_complete(controller.capture_frame())
        if frame is None:
            return "No frame captured (simulation mode or camera unavailable)."
        return base64.b64encode(frame).decode("utf-8")


class DescribeSceneTool(BaseTool):  # type: ignore[misc]
    """Capture a frame and describe what the robot sees."""

    name: str = "describe_scene"
    description: str = (
        "Capture a photo from the robot's camera and use the vision model "
        "to describe what is visible. Optionally provide a specific question."
    )

    def _run(self, question: str = "Describe what you see in detail.", **kwargs: Any) -> str:
        import asyncio

        controller = _get_controller()
        frame = asyncio.get_event_loop().run_until_complete(controller.capture_frame())
        if frame is None:
            return "Cannot analyze scene — no camera available (simulation mode)."
        return describe_image(frame, prompt=question)
