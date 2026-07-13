"""Reachy Mini robot audio I/O client, implementing RobotAudioIO.

Unlike the model servers, this runs in-process in the orchestrator rather
than as its own subprocess — it holds no significant memory, and the voice
loop needs to drive it directly on the same asyncio event loop. Install
reachy_mini on dgx1 via `uv sync --group robot`; it's deliberately not a
base dependency since it needs system packages (cairo, gobject-introspection
dev headers) unlikely to be present on a dev machine (see the lazy import
below and pyproject.toml).

VERIFIED on dgx1 (2026-07-13): reachy_mini==1.9.0 installs (after adding
libcairo2-dev, python3-dev, libgirepository1.0-dev system packages) and its
MediaManager API matches this module (get_audio_sample/push_audio_sample as
float32 numpy arrays, start/stop_recording, start/stop_playing,
get_input/output_audio_samplerate). NOT YET verified against a live,
physically-connected robot — none was plugged into dgx1 at the time this
was written. Re-verify with scripts/dev_mic_check.py once hardware is
available; get_audio_sample()'s exact blocking/polling behavior in
particular should be confirmed against real audio, not just inspected.
"""

import asyncio
from collections.abc import AsyncIterator

import numpy as np

POLL_INTERVAL_S = 0.01


class ReachyMiniClient:
    def __init__(self, use_sim: bool = False) -> None:
        from reachy_mini import ReachyMini

        self._robot = ReachyMini(spawn_daemon=True, use_sim=use_sim)
        self._media = self._robot.media
        self.input_sample_rate_hz: int = self._media.get_input_audio_samplerate()
        self.output_sample_rate_hz: int = self._media.get_output_audio_samplerate()

    async def start_recording(self) -> None:
        await asyncio.to_thread(self._media.start_recording)

    async def stop_recording(self) -> None:
        await asyncio.to_thread(self._media.stop_recording)

    async def read_mic_frames(self) -> AsyncIterator[bytes]:
        while True:
            sample = await asyncio.to_thread(self._media.get_audio_sample)
            if sample is None:
                await asyncio.sleep(POLL_INTERVAL_S)
                continue
            yield _float32_to_pcm16(sample)

    async def start_playing(self) -> None:
        await asyncio.to_thread(self._media.start_playing)

    async def stop_playing(self) -> None:
        await asyncio.to_thread(self._media.stop_playing)

    async def play_audio(self, pcm16_chunk: bytes) -> None:
        samples = _pcm16_to_float32(pcm16_chunk)
        await asyncio.to_thread(self._media.push_audio_sample, samples)

    def close(self) -> None:
        self._robot.release_media()


def _float32_to_pcm16(samples: np.ndarray) -> bytes:
    clipped = np.clip(samples, -1.0, 1.0)
    return bytes((clipped * 32767).astype(np.int16).tobytes())


def _pcm16_to_float32(pcm16: bytes) -> np.ndarray:
    ints = np.frombuffer(pcm16, dtype=np.int16)
    return ints.astype(np.float32) / 32768.0
