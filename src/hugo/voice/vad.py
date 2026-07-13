"""Speech-activity detection via Silero VAD, used in two contexts by the
voice loop: end-of-utterance detection while LISTENING, and barge-in
speech-onset detection while SPEAKING (see docs/adr/0003)."""

from typing import Literal

import numpy as np
import torch
from silero_vad import VADIterator, load_silero_vad

SAMPLE_RATE_HZ = 16_000
DEFAULT_THRESHOLD = 0.5

SpeechEvent = Literal["speech_start", "speech_end"]


class SpeechActivityDetector:
    def __init__(self, threshold: float = DEFAULT_THRESHOLD) -> None:
        model = load_silero_vad(onnx=True)
        self._iterator = VADIterator(model, sampling_rate=SAMPLE_RATE_HZ, threshold=threshold)

    def feed(self, pcm16_chunk: bytes) -> SpeechEvent | None:
        """Feed one chunk of 16kHz mono int16 PCM audio (Silero expects
        fixed-size chunks — 512 samples at 16kHz). Returns "speech_start"/
        "speech_end" on a detected transition, or None otherwise."""
        samples = np.frombuffer(pcm16_chunk, dtype=np.int16).astype(np.float32) / 32768.0
        result = self._iterator(torch.from_numpy(samples))
        if result is None:
            return None
        if "start" in result:
            return "speech_start"
        if "end" in result:
            return "speech_end"
        return None

    def reset(self) -> None:
        self._iterator.reset_states()
