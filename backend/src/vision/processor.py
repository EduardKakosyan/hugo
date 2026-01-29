"""Vision analysis — send frames to a multimodal LLM for scene understanding."""

from __future__ import annotations

import base64
import io
import logging

import numpy as np
from PIL import Image

from src.agent.providers import LLMProvider

logger = logging.getLogger(__name__)


class VisionProcessor:
    """Processes camera frames through a multimodal LLM for scene understanding."""

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def analyze_frame(
        self,
        frame: np.ndarray,
        prompt: str = "Describe what you see in this image.",
    ) -> str:
        """Analyze a camera frame using the multimodal LLM."""
        image = Image.fromarray(frame)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        image_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        try:
            result = await self._llm.vision_analysis(image_b64, prompt)
            return result
        except Exception as e:
            logger.error("Vision analysis failed: %s", e)
            return f"Vision analysis failed: {e}"
