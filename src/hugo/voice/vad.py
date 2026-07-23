"""Speech-activity detection via Silero VAD, used in two contexts by the
voice loop: end-of-utterance detection while LISTENING, and barge-in
speech-onset detection while SPEAKING (see docs/adr/0003)."""

from typing import Literal

import numpy as np
import torch
from silero_vad import VADIterator, load_silero_vad

SAMPLE_RATE_HZ = 16_000
DEFAULT_THRESHOLD = 0.5

# How long the user must stay silent before their utterance is considered
# finished. Silero's default is 100ms, which ends the turn at any natural
# mid-sentence pause — live 2026-07-23, HUGO answered a thinking-pause
# "uh" as if it were the whole question and talked over the rest of the
# sentence ("keeps cutting me off"). The cost of patience is added
# response latency (exactly this much), so it's a balance, not a maximum.
DEFAULT_MIN_SILENCE_MS = 800

# Silero's ONNX model hard-requires exactly this many samples per call at
# 16kHz (confirmed by reading OnnxWrapper.__call__ on dgx1: it raises
# ValueError on any other size) — but mic frames from ReachyMiniClient
# arrive in whatever size the media backend's poll happens to hand back,
# not necessarily 512 samples. feed() below re-buffers to this fixed size
# so callers can pass frames of any length, the same way WakeWordDetector
# already tolerates arbitrary chunk sizes.
WINDOW_SAMPLES = 512
WINDOW_BYTES = WINDOW_SAMPLES * 2  # int16 mono

SpeechEvent = Literal["speech_start", "speech_end"]


class SpeechActivityDetector:
    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
        min_silence_duration_ms: int = DEFAULT_MIN_SILENCE_MS,
    ) -> None:
        model = load_silero_vad(onnx=True)
        self._iterator = VADIterator(
            model,
            sampling_rate=SAMPLE_RATE_HZ,
            threshold=threshold,
            min_silence_duration_ms=min_silence_duration_ms,
        )
        self._buffer = bytearray()

    def feed(self, pcm16_chunk: bytes) -> SpeechEvent | None:
        """Feed any amount of 16kHz mono int16 PCM audio. Buffers internally
        and runs Silero once per complete 512-sample window, so a chunk
        larger, smaller, or misaligned with that window size is still
        handled correctly. Returns the most recent "speech_start"/
        "speech_end" transition detected across the window(s) completed by
        this call, or None if none of them transitioned."""
        self._buffer.extend(pcm16_chunk)
        event: SpeechEvent | None = None
        while len(self._buffer) >= WINDOW_BYTES:
            window = bytes(self._buffer[:WINDOW_BYTES])
            del self._buffer[:WINDOW_BYTES]
            event = self._feed_window(window) or event
        return event

    def _feed_window(self, window: bytes) -> SpeechEvent | None:
        samples = np.frombuffer(window, dtype=np.int16).astype(np.float32) / 32768.0
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
        self._buffer.clear()
