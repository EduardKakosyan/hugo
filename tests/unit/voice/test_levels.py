"""The shared dBFS meter — the number both the sleeping ear and the awake
voice loop report for "how loud were you". Pure function, no hardware."""

import numpy as np

from hugo.voice.levels import SILENCE_DBFS, peak_dbfs


def _pcm16(samples: list[float]) -> bytes:
    return (np.array(samples, dtype=np.float32) * 32767).astype(np.int16).tobytes()


def test_digital_silence_stays_at_the_floor() -> None:
    assert peak_dbfs(b"\x00\x00" * 160) == SILENCE_DBFS


def test_full_scale_square_is_about_zero_dbfs() -> None:
    assert abs(peak_dbfs(_pcm16([1.0, -1.0] * 80))) < 0.1


def test_half_scale_square_is_about_minus_six_dbfs() -> None:
    assert abs(peak_dbfs(_pcm16([0.5, -0.5] * 80)) - (-6.02)) < 0.1


def test_running_peak_never_decreases() -> None:
    # Callers thread the previous peak back in to accumulate across frames
    # (every 500 frames while asleep, every listening window while awake).
    loud = peak_dbfs(_pcm16([0.5, -0.5] * 80))
    quiet = _pcm16([0.001, -0.001] * 80)
    assert peak_dbfs(quiet, loud) == loud
    assert peak_dbfs(_pcm16([1.0, -1.0] * 80), loud) > loud


def test_empty_and_partial_frames_return_the_peak_unchanged() -> None:
    # Metering runs on every mic frame in the loop's hot path; it must never
    # be the call that kills a turn.
    assert peak_dbfs(b"", -20.0) == -20.0
    assert peak_dbfs(b"\x00", -20.0) == -20.0


def test_a_trailing_odd_byte_is_dropped_rather_than_raising() -> None:
    full_scale_plus_half_a_sample = _pcm16([1.0] * 8) + b"\x7f"
    assert abs(peak_dbfs(full_scale_plus_half_a_sample)) < 0.1
