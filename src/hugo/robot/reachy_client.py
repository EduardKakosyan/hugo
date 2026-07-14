"""Reachy Mini robot audio I/O client, implementing RobotAudioIO.

Unlike the model servers, this runs in-process in the orchestrator rather
than as its own subprocess — it holds no significant memory, and the voice
loop needs to drive it directly on the same asyncio event loop. Install
reachy_mini on dgx1 via `uv sync --group robot`; it's deliberately not a
base dependency since it needs system packages (cairo, gobject-introspection
dev headers) unlikely to be present on a dev machine (see the lazy import
below and pyproject.toml).

FULLY VERIFIED on dgx1 (2026-07-13) against a physically-connected robot,
including a real mic-record-then-playback round trip via `hugo dev echo`:
reachy_mini==1.9.0 installs (after adding libcairo2-dev, python3-dev,
libgirepository1.0-dev system packages), the daemon starts and detects all
9 motors (after also adding the `dialout` group for /dev/ttyACM0 serial
access), and the MediaManager API matches this module.

media_backend is explicitly "local" — the daemon's own default media
server still logs "Failed to create webrtcsink element" (GStreamer's
WebRTC Rust plugin isn't packaged for Ubuntu and needs a from-source Rust
build), but that only affects the daemon's optional remote-streaming path.
Explicitly requesting the LOCAL backend uses GStreamer's local audio
pipeline directly (no WebRTC signaling needed) since the SDK client and
daemon are on the same machine — sidesteps the whole Rust-plugin problem.
(Note: "sounddevice_no_video" also worked in testing and is what
originally revealed this, but the SDK flags it as deprecated in favor of
"local", which is used here instead. Camera init still fails gracefully
under LOCAL too — a separate missing GStreamer element, `unixfdsrc` — but
that's fine for M1's audio-only scope.)

Confirmed real upstream SDK limitation, not our bug: on a cold start
(no daemon running yet), `ReachyMini(spawn_daemon=True, ...)` spawns the
daemon subprocess but does NOT reliably wait for it to finish its ~15-20s
startup (motor detection etc.) before attempting to connect — even passing
an explicit `timeout=45.0` didn't help, confirmed directly. The spawned
daemon keeps running in the background regardless, and a second
`ReachyMini(...)` call a bit later connects to it immediately (the SDK
correctly detects "daemon already running" and doesn't double-spawn) — so
we retry with a delay rather than working around it more invasively.

SUSPECTED BUG, not yet confirmed on hardware: the ReSpeaker mic/speaker are
2-channel at the reachy_mini SDK level (`get_audio_sample()` returns shape
(N, 2); `push_audio_sample()`'s pipeline sink is also 2-channel), but
`_float32_to_pcm16`/`_pcm16_to_float32` below just flatten/treat the array
as mono, and every downstream consumer (RobotAudioIO's own contract,
wake_word/vad/stt) assumes mono PCM16. That would explain garbled/quiet
audio specifically on the reachy_mini path while raw ALSA mono capture is
clean. Use `hugo dev dump-capture` to confirm before fixing — it dumps
both the untouched multi-channel capture and HUGO's current mono
conversion of the same audio for offline A/B comparison.
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 0.01
DAEMON_CONNECT_RETRIES = 3
DAEMON_CONNECT_RETRY_DELAY_S = 20.0


class ReachyMiniClient:
    def __init__(self, use_sim: bool = False) -> None:
        from reachy_mini import ReachyMini

        self._robot = self._connect_with_retries(ReachyMini, use_sim)
        self._media = self._robot.media
        self.input_sample_rate_hz: int = self._media.get_input_audio_samplerate()
        self.output_sample_rate_hz: int = self._media.get_output_audio_samplerate()
        self.input_channels: int = self._media.get_input_channels()

    @staticmethod
    def _connect_with_retries(reachy_mini_cls: Any, use_sim: bool) -> Any:
        last_error: ConnectionError | None = None
        for attempt in range(1, DAEMON_CONNECT_RETRIES + 1):
            try:
                return reachy_mini_cls(spawn_daemon=True, use_sim=use_sim, media_backend="local")
            except ConnectionError as e:
                last_error = e
                logger.warning(
                    "reachy_mini connection attempt %d/%d failed (daemon likely "
                    "still cold-starting): %s",
                    attempt,
                    DAEMON_CONNECT_RETRIES,
                    e,
                )
                if attempt < DAEMON_CONNECT_RETRIES:
                    time.sleep(DAEMON_CONNECT_RETRY_DELAY_S)
        assert last_error is not None
        raise last_error

    async def start_recording(self) -> None:
        await asyncio.to_thread(self._media.start_recording)

    async def stop_recording(self) -> None:
        await asyncio.to_thread(self._media.stop_recording)

    async def read_mic_frames(self) -> AsyncIterator[bytes]:
        async for sample in self._read_raw_samples():
            yield _float32_to_pcm16(sample)

    async def read_mic_frames_raw(self) -> AsyncIterator[np.ndarray]:
        """Diagnostic only: yields the exact float32 samples the reachy_mini
        media backend returns (shape (N, input_channels)), before HUGO's
        mono PCM16 conversion — lets `hugo dev dump-capture` isolate
        reachy_mini's own capture path from HUGO's downmixing when
        debugging audio quality."""
        async for sample in self._read_raw_samples():
            yield sample

    async def _read_raw_samples(self) -> AsyncIterator[np.ndarray]:
        while True:
            sample = await asyncio.to_thread(self._media.get_audio_sample)
            if sample is None:
                await asyncio.sleep(POLL_INTERVAL_S)
                continue
            yield sample

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
