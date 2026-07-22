"""A short confirmation tone played when the wake word is detected --
lets you tell "HUGO heard the wake word" apart from "something later in
the pipeline failed silently" when testing on real hardware (see
voice/loop.py's _run_idle)."""

import numpy as np

_FREQUENCY_HZ = 880.0
_DURATION_S = 0.15
_AMPLITUDE = 0.3


def wake_chime_pcm16(sample_rate_hz: int) -> bytes:
    sample_count = int(sample_rate_hz * _DURATION_S)
    t = np.arange(sample_count) / sample_rate_hz
    tone = _AMPLITUDE * np.sin(2 * np.pi * _FREQUENCY_HZ * t)
    return (tone * 32767).astype(np.int16).tobytes()
