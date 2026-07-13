"""Protocol for the robot's mic/speaker audio I/O, so the voice loop can be
built and tested against a fake without the reachy_mini SDK installed."""

from collections.abc import AsyncIterator
from typing import Protocol


class RobotAudioIO(Protocol):
    input_sample_rate_hz: int
    output_sample_rate_hz: int

    async def start_recording(self) -> None: ...
    async def stop_recording(self) -> None: ...

    def read_mic_frames(self) -> AsyncIterator[bytes]:
        """Yields raw int16 PCM16 mono chunks as they become available."""
        ...

    async def start_playing(self) -> None: ...
    async def stop_playing(self) -> None: ...
    async def play_audio(self, pcm16_chunk: bytes) -> None:
        """Pushes one chunk of int16 PCM16 mono audio to the speaker."""
        ...

    def close(self) -> None: ...
