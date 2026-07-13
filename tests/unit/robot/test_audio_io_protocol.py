"""Confirms a plain fake structurally satisfies RobotAudioIO, and exercises
the PCM16<->float32 conversion helpers reachy_client.py relies on — those
are pure functions testable without the reachy_mini SDK installed."""

from collections.abc import AsyncIterator

import numpy as np

from hugo.robot.audio_io import RobotAudioIO
from hugo.robot.reachy_client import _float32_to_pcm16, _pcm16_to_float32


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
