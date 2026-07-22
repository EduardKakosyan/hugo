import numpy as np

from hugo.voice.resample import LinearPcm16Resampler


def _sine_pcm16(freq_hz: float, rate_hz: int, seconds: float) -> bytes:
    t = np.arange(int(rate_hz * seconds)) / rate_hz
    return (0.5 * np.sin(2 * np.pi * freq_hz * t) * 32767).astype(np.int16).tobytes()


def test_identity_when_rates_match() -> None:
    chunk = _sine_pcm16(440, 16_000, 0.1)
    assert LinearPcm16Resampler(16_000, 16_000).process(chunk) == chunk


def test_24k_to_16k_produces_two_thirds_the_samples() -> None:
    pcm = _sine_pcm16(440, 24_000, 1.0)
    out = LinearPcm16Resampler(24_000, 16_000).process(pcm)
    assert abs(len(out) // 2 - 16_000) <= 2


def test_chunked_processing_matches_one_shot_exactly() -> None:
    # The property the voice loop depends on: TTS delivers arbitrary chunk
    # sizes, and resampling them incrementally must introduce no seams.
    pcm = _sine_pcm16(300, 24_000, 0.5)
    one_shot = LinearPcm16Resampler(24_000, 16_000).process(pcm)

    chunked = LinearPcm16Resampler(24_000, 16_000)
    pieces = []
    for size in (7, 64, 501, 1200, 2400):  # deliberately awkward sizes
        pieces.append(chunked.process(pcm[: size * 2]))
        pcm = pcm[size * 2 :]
    pieces.append(chunked.process(pcm))
    assert b"".join(pieces) == one_shot


def test_waveform_is_preserved() -> None:
    resampled = LinearPcm16Resampler(24_000, 16_000).process(
        _sine_pcm16(200, 24_000, 0.25)
    )
    got = np.frombuffer(resampled, dtype=np.int16).astype(np.float64) / 32767
    t = np.arange(len(got)) / 16_000
    expected = 0.5 * np.sin(2 * np.pi * 200 * t)
    assert np.max(np.abs(got - expected)) < 0.01
