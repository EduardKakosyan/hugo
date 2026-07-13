"""Runs real Silero VAD ONNX inference (no GPU needed, downloads a small
pretrained model on first run). Covers the negative control — silence must
never report a speech event — and the API contract (reset, chunk size).
A true positive-case test against real speech audio is a manual/hardware
follow-up, same as the STT/TTS "not yet verified with real audio" caveats
elsewhere."""

import numpy as np

from hugo.voice.vad import SAMPLE_RATE_HZ, SpeechActivityDetector

CHUNK_SAMPLES = 512  # Silero's required fixed chunk size at 16kHz


def test_sample_rate_constant_matches_silero_requirement() -> None:
    assert SAMPLE_RATE_HZ == 16_000


def test_silence_never_reports_a_speech_event() -> None:
    detector = SpeechActivityDetector()
    silence = (np.zeros(CHUNK_SAMPLES, dtype=np.int16)).tobytes()

    events = [detector.feed(silence) for _ in range(20)]

    assert all(event is None for event in events)


def test_reset_does_not_raise() -> None:
    detector = SpeechActivityDetector()
    detector.feed((np.zeros(CHUNK_SAMPLES, dtype=np.int16)).tobytes())

    detector.reset()  # must not raise
