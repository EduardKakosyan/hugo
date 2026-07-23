"""Streaming sample-rate conversion for mono PCM16 audio.

Exists because Qwen3-TTS synthesizes at 24kHz while the Reachy Mini's
speaker pipeline runs at 16kHz — pushing 24kHz samples into the 16kHz
appsrc plays them slow and pitched-down (2/3 speed). Found on real
hardware 2026-07-22; the fake robot's output rate is deliberately
mismatched from TTS in tests to keep this honest.

Anti-aliasing added after the first live VEN-56 session (2026-07-23):
bare linear interpolation folds everything above the 8kHz output Nyquist
back into the audible band, which smears sibilants and made HUGO's voice
sound slurred/harsh through the robot speaker. Downsampling now runs a
streaming kaiser-windowed FIR low-pass first, with its group delay
compensated so output stays sample-aligned with input (the last ~1ms of
a stream is traded away for that — inaudible for speech).
"""

import numpy as np

# 61 taps at 24kHz input ≈ 2.5ms window: enough for ~60dB of stopband
# rejection with a kaiser(beta=8.6) design while keeping per-chunk
# convolution cost trivial.
_FIR_TAPS = 61
_KAISER_BETA = 8.6


def _design_low_pass(cutoff_hz: float, rate_hz: int) -> np.ndarray:
    n = np.arange(_FIR_TAPS) - (_FIR_TAPS - 1) / 2
    taps = np.sinc(2.0 * cutoff_hz / rate_hz * n) * np.kaiser(_FIR_TAPS, _KAISER_BETA)
    return np.asarray(taps / taps.sum())


class StreamingPcm16Resampler:
    """Chunk-streaming resampler; safe to feed arbitrary chunk sizes.

    Carries filter state, fractional read position, and unconsumed tail
    samples across process() calls, so resampling a stream chunk-by-chunk
    yields the exact same bytes as resampling it in one call — no seams at
    chunk boundaries. A fresh instance is needed per utterance (state is
    cumulative).
    """

    def __init__(self, in_rate_hz: int, out_rate_hz: int) -> None:
        self._step = in_rate_hz / out_rate_hz
        self._identity = in_rate_hz == out_rate_hz
        self._pos = 0.0
        self._carry = np.empty(0, dtype=np.float64)
        self._taps: np.ndarray | None = None
        if not self._identity and out_rate_hz < in_rate_hz:
            # Cut just under the output Nyquist so folded energy is gone
            # before the interpolation stage.
            self._taps = _design_low_pass(0.45 * out_rate_hz, in_rate_hz)
            self._filter_carry = np.zeros(_FIR_TAPS - 1, dtype=np.float64)
            # Linear-phase FIR delays by (taps-1)/2 samples; discard that
            # many once so output stays time-aligned with input.
            self._delay_to_discard = (_FIR_TAPS - 1) // 2

    def process(self, pcm16_chunk: bytes) -> bytes:
        if self._identity:
            return pcm16_chunk
        samples = np.frombuffer(pcm16_chunk, dtype=np.int16).astype(np.float64)
        if self._taps is not None:
            samples = self._low_pass(samples)
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

    def _low_pass(self, samples: np.ndarray) -> np.ndarray:
        assert self._taps is not None
        extended = np.concatenate([self._filter_carry, samples])
        filtered = np.convolve(extended, self._taps, mode="valid")
        self._filter_carry = extended[len(extended) - (_FIR_TAPS - 1) :]
        if self._delay_to_discard > 0:
            drop = min(self._delay_to_discard, len(filtered))
            filtered = filtered[drop:]
            self._delay_to_discard -= drop
        return filtered
