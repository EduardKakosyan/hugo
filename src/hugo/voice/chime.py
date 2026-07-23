"""Short earcons marking conversation boundaries. The wake chime lets you
tell "HUGO heard the wake word" apart from "something later in the pipeline
failed silently" when testing on real hardware (see voice/loop.py's
_run_idle); the conversation-end chime is the audible cue that the mic is
no longer hot (CONTEXT.md: Follow-up window)."""

import numpy as np

_DURATION_S = 0.15
_AMPLITUDE = 0.3

_WAKE_FREQUENCY_HZ = 880.0
# Lower pitch reads as "closing" against the wake chime's rising 880Hz —
# the two must be audibly distinct or neither carries information.
_END_FREQUENCY_HZ = 440.0


def _tone_pcm16(sample_rate_hz: int, frequency_hz: float) -> bytes:
    sample_count = int(sample_rate_hz * _DURATION_S)
    t = np.arange(sample_count) / sample_rate_hz
    tone = _AMPLITUDE * np.sin(2 * np.pi * frequency_hz * t)
    return (tone * 32767).astype(np.int16).tobytes()


def wake_chime_pcm16(sample_rate_hz: int) -> bytes:
    return _tone_pcm16(sample_rate_hz, _WAKE_FREQUENCY_HZ)


def conversation_end_chime_pcm16(sample_rate_hz: int) -> bytes:
    return _tone_pcm16(sample_rate_hz, _END_FREQUENCY_HZ)
