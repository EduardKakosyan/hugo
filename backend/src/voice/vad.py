"""Silero VAD wrapper – detects speech start/end in audio chunks."""

import logging

import numpy as np
import torch

from src.config import settings

logger = logging.getLogger("hugo.vad")


class VoiceActivityDetector:
    def __init__(self, threshold: float = settings.vad_threshold) -> None:
        self.threshold = threshold
        self._model: torch.jit.ScriptModule | None = None
        self._is_speaking = False

    def load(self) -> None:
        model, _ = torch.hub.load("snakers4/silero-vad", "silero_vad", trust_repo=True)
        self._model = model
        logger.info("Silero VAD loaded (threshold=%.2f)", self.threshold)

    def reset(self) -> None:
        if self._model is not None:
            self._model.reset_states()
        self._is_speaking = False

    def process_chunk(self, audio: np.ndarray) -> dict[str, bool]:
        """Process a 512-sample chunk at 16kHz. Returns speech state transitions."""
        if self._model is None:
            raise RuntimeError("VAD model not loaded – call load() first")

        tensor = torch.from_numpy(audio).float()
        if tensor.dim() == 1:
            tensor = tensor.unsqueeze(0)

        confidence = self._model(tensor, settings.sample_rate).item()

        was_speaking = self._is_speaking
        self._is_speaking = confidence >= self.threshold

        return {
            "is_speaking": self._is_speaking,
            "speech_start": not was_speaking and self._is_speaking,
            "speech_end": was_speaking and not self._is_speaking,
            "confidence": confidence,
        }

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking


vad = VoiceActivityDetector()
