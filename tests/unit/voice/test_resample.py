import numpy as np

from hugo.voice.resample import StreamingPcm16Resampler


def _sine_pcm16(freq_hz: float, rate_hz: int, seconds: float) -> bytes:
    t = np.arange(int(rate_hz * seconds)) / rate_hz
    return (0.5 * np.sin(2 * np.pi * freq_hz * t) * 32767).astype(np.int16).tobytes()


def _rms(pcm16: bytes, skip: int = 200) -> float:
    samples = np.frombuffer(pcm16, dtype=np.int16).astype(np.float64)[skip:] / 32767
    return float(np.sqrt(np.mean(samples**2))) if len(samples) else 0.0


def test_identity_when_rates_match() -> None:
    chunk = _sine_pcm16(440, 16_000, 0.1)
    assert StreamingPcm16Resampler(16_000, 16_000).process(chunk) == chunk


def test_24k_to_16k_produces_two_thirds_the_samples() -> None:
    pcm = _sine_pcm16(440, 24_000, 1.0)
    out = StreamingPcm16Resampler(24_000, 16_000).process(pcm)
    # The FIR's compensated group delay trades away ~30 input samples at
    # the stream tail (~1ms) — inaudible for speech.
    assert abs(len(out) // 2 - 16_000) <= 40


def test_chunked_processing_matches_one_shot_exactly() -> None:
    # The property the voice loop depends on: TTS delivers arbitrary chunk
    # sizes, and resampling them incrementally must introduce no seams.
    pcm = _sine_pcm16(300, 24_000, 0.5)
    one_shot = StreamingPcm16Resampler(24_000, 16_000).process(pcm)

    chunked = StreamingPcm16Resampler(24_000, 16_000)
    pieces = []
    for size in (7, 64, 501, 1200, 2400):  # deliberately awkward sizes
        pieces.append(chunked.process(pcm[: size * 2]))
        pcm = pcm[size * 2 :]
    pieces.append(chunked.process(pcm))
    assert b"".join(pieces) == one_shot


def test_waveform_is_preserved() -> None:
    resampled = StreamingPcm16Resampler(24_000, 16_000).process(_sine_pcm16(200, 24_000, 0.25))
    got = np.frombuffer(resampled, dtype=np.int16).astype(np.float64) / 32767
    t = np.arange(len(got)) / 16_000
    expected = 0.5 * np.sin(2 * np.pi * 200 * t)
    # Skip the FIR's brief startup transient, then the delay-compensated
    # output must be sample-aligned with the input waveform.
    assert np.max(np.abs(got[100:] - expected[100 : len(got)])) < 0.01


def test_passband_speech_frequencies_survive() -> None:
    out = StreamingPcm16Resampler(24_000, 16_000).process(_sine_pcm16(3_000, 24_000, 0.5))
    assert abs(_rms(out) - 0.5 / np.sqrt(2)) < 0.02  # ~unity gain at 3kHz


def test_frequencies_above_output_nyquist_are_rejected_not_aliased() -> None:
    # 11kHz is inaudible garbage after a 16kHz resample: bare linear
    # interpolation folded it back to 5kHz at high energy (the slurred/
    # harsh voice from the first live session, VEN-56). The FIR must kill
    # it instead.
    out = StreamingPcm16Resampler(24_000, 16_000).process(_sine_pcm16(11_000, 24_000, 0.5))
    assert _rms(out) < 0.02  # >25dB down from the 0.35 RMS input
