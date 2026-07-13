"""Runs real openWakeWord ONNX inference (no GPU needed, downloads a small
pretrained model on first run). Covers the negative control — silence must
never false-positive — and the API contract (reset). A true positive-case
test against a real spoken wake phrase is a manual/hardware follow-up, same
as the STT/TTS "not yet verified with real audio" caveats elsewhere."""

import numpy as np

from hugo.voice.wake_word import WakeWordDetector

CHUNK_SAMPLES = 1280  # openWakeWord's recommended ~80ms feed size at 16kHz


def test_silence_never_triggers_detection() -> None:
    detector = WakeWordDetector()
    silence = (np.zeros(CHUNK_SAMPLES, dtype=np.int16)).tobytes()

    triggered = any(detector.feed(silence) for _ in range(10))

    assert not triggered


def test_low_level_noise_does_not_trigger_detection() -> None:
    detector = WakeWordDetector()
    rng = np.random.default_rng(seed=0)

    triggered = False
    for _ in range(10):
        noise = (rng.normal(0, 50, CHUNK_SAMPLES).astype(np.int16)).tobytes()
        if detector.feed(noise):
            triggered = True

    assert not triggered


def test_reset_does_not_raise() -> None:
    detector = WakeWordDetector()
    detector.feed((np.zeros(CHUNK_SAMPLES, dtype=np.int16)).tobytes())

    detector.reset()  # must not raise
