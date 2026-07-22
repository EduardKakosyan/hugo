from hugo.voice.chime import wake_chime_pcm16


def test_wake_chime_is_correct_length_for_sample_rate() -> None:
    chime = wake_chime_pcm16(24_000)

    # 0.15s at 24kHz, 2 bytes/sample (int16 mono).
    assert len(chime) == int(24_000 * 0.15) * 2


def test_wake_chime_is_deterministic() -> None:
    assert wake_chime_pcm16(24_000) == wake_chime_pcm16(24_000)


def test_wake_chime_scales_with_sample_rate() -> None:
    assert len(wake_chime_pcm16(16_000)) < len(wake_chime_pcm16(24_000))
