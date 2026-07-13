"""Runs real pyaec adaptive-filter cancellation (no hardware needed — pure
signal processing). Covers the convergence property that matters for
barge-in: a signal that's pure echo (mic == a scaled copy of what was just
played) must be suppressed toward silence after the filter warms up. Real
speech + real acoustic conditions still need on-hardware validation, per
aec.py's module docstring."""

import numpy as np
import pytest

from hugo.voice.aec import EchoCanceller

SAMPLE_RATE_HZ = 16_000
FRAME_SAMPLES = 256


def _tone_frame(freq_hz: float, amplitude: float) -> np.ndarray:
    t = np.arange(FRAME_SAMPLES) / SAMPLE_RATE_HZ
    return (np.sin(2 * np.pi * freq_hz * t) * amplitude).astype(np.int16)


def _rms(samples: bytes) -> float:
    arr = np.frombuffer(samples, dtype=np.int16).astype(np.float64)
    return float(np.sqrt(np.mean(arr**2)))


def test_pure_echo_converges_toward_silence() -> None:
    canceller = EchoCanceller(sample_rate_hz=SAMPLE_RATE_HZ, frame_samples=FRAME_SAMPLES)
    tone = _tone_frame(440.0, 8000.0)
    echo = tone.tobytes()
    mic_with_echo = (tone * 0.6).astype(np.int16).tobytes()
    raw_input_rms = _rms(mic_with_echo)

    chunks = [canceller.cancel(mic_with_echo, echo) for _ in range(60)]
    converged_rms = float(np.mean([_rms(chunk) for chunk in chunks[-5:]]))

    # The adaptive filter's warm-up is non-monotonic frame-to-frame (observed
    # on real hardware: an initial near-zero frame, then a transient spike,
    # before converging) — so this only asserts the settled end state, not
    # any specific early-frame value.
    assert converged_rms < raw_input_rms * 0.05


def test_mismatched_frame_lengths_raise() -> None:
    canceller = EchoCanceller(sample_rate_hz=SAMPLE_RATE_HZ, frame_samples=FRAME_SAMPLES)
    right_length = _tone_frame(440.0, 1000.0).tobytes()
    wrong_length = _tone_frame(440.0, 1000.0)[:128].tobytes()

    with pytest.raises(ValueError, match="frame size mismatch"):
        canceller.cancel(wrong_length, right_length)

    with pytest.raises(ValueError, match="frame size mismatch"):
        canceller.cancel(right_length, wrong_length)
