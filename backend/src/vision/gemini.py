"""Gemini vision service – sends camera frames for analysis."""

import base64
import logging

from google import genai
from google.genai import types

from src.config import settings
from src.vision.camera import camera

logger = logging.getLogger("hugo.vision.gemini")


class GeminiVision:
    def __init__(self) -> None:
        self._client: genai.Client | None = None

    def _ensure_client(self) -> genai.Client:
        if self._client is None:
            if not settings.gemini_api_key:
                raise RuntimeError("HUGO_GEMINI_API_KEY not set")
            self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

    async def analyze(self, query: str = "Describe what you see in detail.") -> str:
        """Capture a frame and send to Gemini for analysis."""
        jpeg_bytes = camera.capture_jpeg()
        b64 = base64.b64encode(jpeg_bytes).decode("utf-8")

        client = self._ensure_client()
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Content(
                    parts=[
                        types.Part(
                            inline_data=types.Blob(mime_type="image/jpeg", data=b64)
                        ),
                        types.Part(text=query),
                    ]
                )
            ],
        )
        text = response.text or ""
        logger.info("Gemini analysis: %s", text[:200])
        return text


gemini_vision = GeminiVision()
