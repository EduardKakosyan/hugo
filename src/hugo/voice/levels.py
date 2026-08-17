"""One RMS-dBFS meter, shared by the sleeping ear and the awake voice loop.

Lifted out of wake_listener.py, where it was the *only* signal-level
measurement in the system: the awake path logged wake-word scores but never
levels, so "HUGO couldn't hear me" was undiagnosable after the fact — there
was no way to separate a quiet/muffled capture path from a model that
simply didn't fire. Both paths now report the same number computed the same
way, so their journal lines are directly comparable.
"""

import math

import numpy as np

# Where a running peak starts, and what it resets to. Digital silence
# actually scores 20*log10(1e-9) = -180 dBFS; -120 is the readable floor
# the sleeping listener has always used, kept so its log line is unchanged.
SILENCE_DBFS = -120.0


def peak_dbfs(pcm16: bytes, current_peak: float = SILENCE_DBFS) -> float:
    """RMS level of one PCM16 mono chunk in dBFS, maxed with `current_peak`
    so callers can keep a running peak across frames.

    Total by construction: this runs on every mic frame in the voice loop's
    hot path, and a metering call must never be the thing that kills a turn.
    An empty chunk returns the peak unchanged, and a trailing odd byte
    (never produced by the real capture path, which is always whole
    samples) is dropped — half a sample carries no level information.
    """
    usable = pcm16[: len(pcm16) - len(pcm16) % 2]
    samples = np.frombuffer(usable, dtype=np.int16).astype(np.float32) / 32768.0
    if not samples.size:
        return current_peak
    rms = float(np.sqrt(np.mean(samples * samples)))
    return max(current_peak, 20.0 * math.log10(rms + 1e-9))
