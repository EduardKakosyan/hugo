"""MLX vision provider – calls a local OpenAI-compatible server (LM Studio / Ollama)."""

import base64
import logging

import cv2
import httpx
import numpy as np

from src.config import settings
from src.vision.camera import camera

logger = logging.getLogger("hugo.vision.mlx")

_MAX_IMAGE_DIM = 512


def _downscale_jpeg(jpeg_bytes: bytes, max_dim: int = _MAX_IMAGE_DIM) -> bytes:
    """Decode JPEG, downscale so the longest side <= max_dim, re-encode."""
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return jpeg_bytes
    h, w = img.shape[:2]
    if max(h, w) <= max_dim:
        return jpeg_bytes
    scale = max_dim / max(h, w)
    img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        return jpeg_bytes
    return buf.tobytes()


class MLXVision:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=settings.mlx_vision_base_url,
                timeout=60.0,
            )
        return self._client

    async def analyze(self, query: str = "Describe what you see in detail.") -> str:
        """Capture a frame and analyze via local vision model server."""
        jpeg_bytes = camera.capture_jpeg()
        jpeg_bytes = _downscale_jpeg(jpeg_bytes)
        b64_image = base64.b64encode(jpeg_bytes).decode("ascii")

        client = self._ensure_client()
        resp = await client.post(
            "/chat/completions",
            json={
                "model": settings.mlx_vision_model,
                "max_tokens": settings.mlx_vision_max_tokens,
                "temperature": 0.0,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64_image}",
                                },
                            },
                            {"type": "text", "text": query},
                        ],
                    }
                ],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        logger.info("MLX analysis: %s", text[:200])
        return text


mlx_vision = MLXVision()
