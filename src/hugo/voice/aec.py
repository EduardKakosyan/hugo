"""Acoustic echo cancellation, required for true barge-in (docs/adr/0003):
cancels HUGO's own voice out of the mic signal, referenced against the
exact audio actually sent to the speaker, so it doesn't hear itself and
false-trigger a self-interruption.

Uses pyaec (a small ctypes-wrapped NLMS adaptive filter). VERIFIED on dgx1
(2026-07-13, aarch64): a synthetic pure-echo tone (RMS ~3384) converges to
near-silence (RMS ~6) within ~50 frames of the adaptive filter warming up.
Real speech + real acoustic conditions (mic/speaker physically close
together on the Reachy Mini) still needs iteration once the robot is
connected — synthetic single-tone convergence is a real but limited signal,
not a full substitute for on-hardware tuning. If pyaec's cancellation
proves insufficient in practice, WebRTC's AEC3 is the documented fallback
(its Python bindings need `swig` + a C++ build, which is why pyaec was
tried first — see the plan's M1.7 notes).
"""

import numpy as np
from pyaec import Aec

FRAME_SAMPLES = 256
FILTER_LENGTH = 1024


class EchoCanceller:
    def __init__(
        self,
        sample_rate_hz: int,
        frame_samples: int = FRAME_SAMPLES,
        filter_length: int = FILTER_LENGTH,
    ) -> None:
        self._aec = Aec(
            frame_size=frame_samples, filter_length=filter_length, sample_rate=sample_rate_hz
        )
        self._frame_samples = frame_samples

    def cancel(self, mic_chunk: bytes, reference_chunk: bytes) -> bytes:
        """Removes the known reference_chunk audio (what was just sent to
        the speaker) from mic_chunk, returning cleaned int16 PCM16 mono
        bytes. Both chunks must be exactly frame_samples samples long —
        buffering/alignment to that fixed size is the caller's job."""
        mic = np.frombuffer(mic_chunk, dtype=np.int16)
        reference = np.frombuffer(reference_chunk, dtype=np.int16)
        if len(mic) != self._frame_samples or len(reference) != self._frame_samples:
            raise ValueError(
                f"AEC frame size mismatch: expected {self._frame_samples} samples, "
                f"got mic={len(mic)}, reference={len(reference)}"
            )
        cleaned = self._aec.cancel_echo(mic.tolist(), reference.tolist())
        return np.array(cleaned, dtype=np.int16).tobytes()
