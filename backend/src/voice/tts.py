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
        self._model: object | None = None
        self._sample_rate: int = 24000

    def load(self) -> None:
        from mlx_audio.tts.utils import load_model

        self._model = load_model(self.model_name)
        self._sample_rate = getattr(self._model, "sample_rate", 24000)
        logger.info("Kokoro TTS loaded: %s (voice=%s)", self.model_name, self.voice)

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        """Synthesize text to (audio_array, sample_rate)."""
        if self._model is None:
            raise RuntimeError("TTS model not loaded – call load() first")

        # model.generate() yields GenerationResult objects with .audio and .sample_rate
        chunks = []
        for result in self._model.generate(text, voice=self.voice):
            audio = result.audio
            if not isinstance(audio, np.ndarray):
                audio = np.array(audio)
            chunks.append(audio)

        if not chunks:
            return np.array([], dtype=np.float32), self._sample_rate

        return np.concatenate(chunks), self._sample_rate


tts = TextToSpeech()
