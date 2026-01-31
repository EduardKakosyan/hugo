"""MLX vision provider – local VLM analysis using mlx-vlm."""

import asyncio
import logging
import os
import tempfile

from src.config import settings
from src.vision.camera import camera

logger = logging.getLogger("hugo.vision.mlx")


class MLXVision:
    def __init__(self) -> None:
        self._model: object | None = None
        self._processor: object | None = None
        self._config: object | None = None

    def _ensure_model(self) -> None:
        if self._model is None:
            from mlx_vlm import load
            from mlx_vlm.utils import load_config

            model_name = settings.mlx_vision_model
            logger.info("Loading MLX vision model: %s", model_name)
            self._model, self._processor = load(model_name)
            self._config = load_config(model_name)
            logger.info("MLX vision model loaded: %s", model_name)

    def _run_inference(self, query: str, image_path: str) -> str:
        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template

        self._ensure_model()
        prompt = apply_chat_template(self._processor, self._config, query, num_images=1)
        output = generate(self._model, self._processor, prompt, [image_path], verbose=False)
        return output

    async def analyze(self, query: str = "Describe what you see in detail.") -> str:
        """Capture a frame and analyze with local MLX VLM."""
        jpeg_bytes = camera.capture_jpeg()

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(jpeg_bytes)
            tmp_path = f.name

        try:
            text = await asyncio.to_thread(self._run_inference, query, tmp_path)
        finally:
            os.unlink(tmp_path)

        logger.info("MLX analysis: %s", text[:200])
        return text


mlx_vision = MLXVision()
