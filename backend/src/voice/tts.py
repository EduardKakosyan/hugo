"""Kokoro TTS – synthesizes text to audio arrays."""

import logging

import numpy as np

from src.config import settings

logger = logging.getLogger("hugo.tts")


class TextToSpeech:
    def __init__(
        self,
        model_name: str = settings.tts_model,
        voice: str = settings.tts_voice,
    ) -> None:
        self.model_name = model_name
        self.voice = voice
        self._pipeline: object | None = None

    def load(self) -> None:
        from mlx_audio.tts import TTSPipeline

        self._pipeline = TTSPipeline(model=self.model_name)
        logger.info("Kokoro TTS loaded: %s (voice=%s)", self.model_name, self.voice)

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        """Synthesize text to (audio_array, sample_rate)."""
        if self._pipeline is None:
            raise RuntimeError("TTS model not loaded – call load() first")

        result = self._pipeline(text, voice=self.voice)

        if isinstance(result, tuple):
            audio, sr = result
        else:
            audio = result
            sr = 24000  # Kokoro default

        if not isinstance(audio, np.ndarray):
            audio = np.array(audio)

        return audio, sr


tts = TextToSpeech()
