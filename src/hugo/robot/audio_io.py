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
    async def clear_playback(self) -> None:
        """Immediately drops any queued-but-unplayed speaker audio (barge-in).

        Unlike stop_playing() this must be safe to call while recording is
        live: reachy_mini's local backend uses ONE gstreamer pipeline for
        both directions, and stop_playing() sets that whole pipeline to
        NULL — killing capture (and deadlocking against the capture
        streaming thread; two real hangs on dgx1, 2026-07-16). clear_player
        is the SDK's sanctioned flush-without-teardown for this case.
        """
        ...

    async def play_audio(self, pcm16_chunk: bytes) -> None:
        """Pushes one chunk of int16 PCM16 mono audio to the speaker."""
        ...

    def close(self) -> None: ...
