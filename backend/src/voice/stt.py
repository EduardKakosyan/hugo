"""MLX Whisper STT – transcribes audio buffers to text."""

import logging

import numpy as np

from src.config import settings

logger = logging.getLogger("hugo.stt")


class SpeechToText:
    def __init__(self, model_name: str = settings.stt_model) -> None:
        self.model_name = model_name
        self._model: object | None = None

    def load(self) -> None:
        from mlx_audio.stt.generate import load_model

        self._model = load_model(self.model_name)
        logger.info("MLX Whisper STT loaded: %s", self.model_name)

    def transcribe(self, audio: np.ndarray, sample_rate: int = settings.sample_rate) -> str:
        """Transcribe audio numpy array to text."""
        if self._model is None:
            raise RuntimeError("STT model not loaded – call load() first")

        result = self._model.generate(audio, verbose=False)

        if isinstance(result, dict):
            return result.get("text", "").strip()
        return str(result).strip()


stt = SpeechToText()
