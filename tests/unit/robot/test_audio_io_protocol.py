"""Confirms a plain fake structurally satisfies RobotAudioIO, and exercises
the PCM16<->float32 conversion helpers reachy_client.py relies on — those
are pure functions testable without the reachy_mini SDK installed."""

from collections.abc import AsyncIterator

import numpy as np

from hugo.robot.audio_io import RobotAudioIO
from hugo.robot.reachy_client import (
    _downmix_to_mono,
    _float32_to_pcm16,
    _pcm16_to_float32,
    _upmix_mono,
)


class FakeRobotAudioIO:
    input_sample_rate_hz = 16_000
    output_sample_rate_hz = 24_000

    def __init__(self) -> None:
        self.recording = False
        self.playing = False
        self.played_chunks: list[bytes] = []
        self.closed = False

    async def start_recording(self) -> None:
        self.recording = True

    async def stop_recording(self) -> None:
        self.recording = False

    async def read_mic_frames(self) -> AsyncIterator[bytes]:
        yield b"\x00\x01" * 10

    async def start_playing(self) -> None:
        self.playing = True

    async def stop_playing(self) -> None:
        self.playing = False

    async def play_audio(self, pcm16_chunk: bytes) -> None:
        self.played_chunks.append(pcm16_chunk)

    def close(self) -> None:
        self.closed = True


def test_fake_satisfies_the_protocol() -> None:
    audio_io: RobotAudioIO = FakeRobotAudioIO()
    assert audio_io is not None


async def test_fake_lifecycle() -> None:
    audio_io = FakeRobotAudioIO()

    await audio_io.start_recording()
    frames = [frame async for frame in audio_io.read_mic_frames()]
    await audio_io.stop_recording()
    await audio_io.start_playing()
    await audio_io.play_audio(frames[0])
    await audio_io.stop_playing()
    audio_io.close()

    assert audio_io.played_chunks == frames
    assert audio_io.closed


def test_pcm16_float32_round_trip_is_lossless_within_int16_precision() -> None:
    original = np.array([0.0, 0.5, -0.5, 0.999, -1.0], dtype=np.float32)
    pcm16 = _float32_to_pcm16(original)
    recovered = _pcm16_to_float32(pcm16)

    assert np.allclose(original, recovered, atol=1e-3)


def test_float32_to_pcm16_clips_out_of_range_values() -> None:
    loud = np.array([2.0, -2.0], dtype=np.float32)

    pcm16 = _float32_to_pcm16(loud)
    ints = np.frombuffer(pcm16, dtype=np.int16)

    assert ints[0] == 32767
    assert ints[1] == -32767  # -1.0 * 32767, matching this module's clip-then-scale order


def test_downmix_averages_multichannel_capture_to_mono() -> None:
    # left=1.0, right=-1.0 throughout — averaging must not just take channel 0
    stereo = np.array([[1.0, -1.0], [1.0, -1.0], [1.0, -1.0]], dtype=np.float32)

    mono = _downmix_to_mono(stereo)

    assert mono.ndim == 1
    assert np.allclose(mono, 0.0)


def test_downmix_is_lossless_when_channels_are_identical() -> None:
    # matches what was actually observed on dgx1's ReSpeaker: channels equal
    identical_stereo = np.array([[0.5, 0.5], [-0.25, -0.25]], dtype=np.float32)

    mono = _downmix_to_mono(identical_stereo)

    assert np.allclose(mono, [0.5, -0.25])


def test_downmix_passes_through_already_mono_input_unchanged() -> None:
    mono_in = np.array([0.1, -0.2, 0.3], dtype=np.float32)

    assert np.array_equal(_downmix_to_mono(mono_in), mono_in)


def test_upmix_duplicates_mono_across_every_output_channel() -> None:
    mono = np.array([0.1, -0.2, 0.3], dtype=np.float32)

    stereo = _upmix_mono(mono, channels=2)

    assert stereo.shape == (3, 2)
    assert np.array_equal(stereo[:, 0], mono)
    assert np.array_equal(stereo[:, 1], mono)


def test_upmix_passes_through_single_channel_output_unchanged() -> None:
    mono = np.array([0.1, -0.2, 0.3], dtype=np.float32)

    assert np.array_equal(_upmix_mono(mono, channels=1), mono)


def test_downmix_then_upmix_round_trips_when_channels_were_identical() -> None:
    """The exact shape HUGO's real capture->playback path relies on:
    identical-channel capture (as observed on dgx1) survives a full
    downmix-then-upmix unchanged."""
    stereo_in = np.array([[0.5, 0.5], [-0.25, -0.25], [0.75, 0.75]], dtype=np.float32)

    mono = _downmix_to_mono(stereo_in)
    round_tripped = _upmix_mono(mono, channels=2)

    assert np.allclose(round_tripped, stereo_in)
