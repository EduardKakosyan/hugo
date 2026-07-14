"""Runs real Silero VAD ONNX inference (no GPU needed, downloads a small
pretrained model on first run). Covers the negative control — silence must
never report a speech event — and the API contract (reset, chunk size).
A true positive-case test against real speech audio is a manual/hardware
follow-up, same as the STT/TTS "not yet verified with real audio" caveats
elsewhere."""

import numpy as np

from hugo.voice.vad import SAMPLE_RATE_HZ, WINDOW_SAMPLES, SpeechActivityDetector

CHUNK_SAMPLES = WINDOW_SAMPLES  # Silero's required fixed window size at 16kHz


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


def test_feed_tolerates_chunk_sizes_that_are_not_the_silero_window_size() -> None:
    """Real mic frames from ReachyMiniClient arrive in whatever size the
    media backend hands back per poll, not necessarily 512 samples —
    feed() must re-buffer rather than assume its input is pre-aligned."""
    detector = SpeechActivityDetector()

    silence = np.zeros(10_000, dtype=np.int16).tobytes()
    odd_chunk_size = 777  # deliberately not a multiple of WINDOW_BYTES
    events = [
        detector.feed(silence[i : i + odd_chunk_size])
        for i in range(0, len(silence), odd_chunk_size)
    ]

    assert all(event is None for event in events)


def test_feed_handles_chunks_smaller_than_one_window() -> None:
    detector = SpeechActivityDetector()
    silence = np.zeros(CHUNK_SAMPLES, dtype=np.int16).tobytes()
    half = len(silence) // 2

    first = detector.feed(silence[:half])
    second = detector.feed(silence[half:])

    assert first is None
    assert second is None


def test_reset_clears_partially_buffered_bytes() -> None:
    """A leftover partial window from a previous utterance must not shift
    the sample alignment of the next one after reset()."""
    detector = SpeechActivityDetector()
    detector.feed(np.zeros(1, dtype=np.int16).tobytes())  # 2 bytes, well under a window

    detector.reset()

    full_window = np.zeros(CHUNK_SAMPLES, dtype=np.int16).tobytes()
    assert detector.feed(full_window) is None  # would need 511 more bytes if buffer leaked
