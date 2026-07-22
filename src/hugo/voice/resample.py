"""Streaming sample-rate conversion for mono PCM16 audio.

Exists because Qwen3-TTS synthesizes at 24kHz (servers/qwen_tts_synthesizer
.SAMPLE_RATE_HZ) while the Reachy Mini's speaker pipeline runs at 16kHz —
pushing 24kHz samples into the 16kHz appsrc plays them slow and
pitched-down (2/3 speed). Found on real hardware 2026-07-22; unit tests
never caught it because the fake robot's output rate happened to match the
TTS rate. Linear interpolation is plenty for speech at these rates.
"""

import numpy as np


class LinearPcm16Resampler:
    """Chunk-streaming linear resampler; safe to feed arbitrary chunk sizes.

    Carries fractional read position and unconsumed tail samples across
    process() calls, so resampling a stream chunk-by-chunk yields the exact
    same bytes as resampling it in one call — no seams at chunk boundaries.
    A fresh instance is needed per utterance (state is cumulative).
    """

    def __init__(self, in_rate_hz: int, out_rate_hz: int) -> None:
        self._step = in_rate_hz / out_rate_hz
        self._identity = in_rate_hz == out_rate_hz
        self._pos = 0.0
        self._carry = np.empty(0, dtype=np.float64)

    def process(self, pcm16_chunk: bytes) -> bytes:
        if self._identity:
            return pcm16_chunk
        samples = np.frombuffer(pcm16_chunk, dtype=np.int16).astype(np.float64)
        buf = np.concatenate([self._carry, samples])
        if len(buf) < 2 or self._pos > len(buf) - 1:
            self._carry = buf
            return b""
        n_out = int(np.floor((len(buf) - 1 - self._pos) / self._step)) + 1
        idx = self._pos + self._step * np.arange(n_out)
        out = np.interp(idx, np.arange(len(buf)), buf)
        next_pos = idx[-1] + self._step
        keep_from = min(int(np.floor(next_pos)), len(buf))
        self._carry = buf[keep_from:]
        self._pos = next_pos - keep_from
        return bytes(np.clip(np.rint(out), -32768, 32767).astype(np.int16).tobytes())
