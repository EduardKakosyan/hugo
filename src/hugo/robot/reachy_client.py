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

CONFIRMED on dgx1 (2026-07-14) via `hugo dev dump-capture` + a live A/B
listening test: the ReSpeaker mic is 2-channel at the reachy_mini SDK level
(`get_audio_sample()` returns shape (N, 2)), but the old `read_mic_frames()`
just flattened that array and handed it to every mono-assuming downstream
consumer. Byte-for-byte, channel 0 and channel 1 were identical in the
captured WAV, so the corruption wasn't noise-like garbling — it was every
sample duplicated back-to-back, which on playback is audibly a
half-speed/one-octave-down version of the same audio (confirmed by ear:
the raw 2-channel capture sounded clean, the old mono conversion of the
exact same audio sounded slower/deeper). Fixed below by explicitly
downmixing on capture (`_downmix_to_mono`) and upmixing on playback
(`_upmix_mono`) using the real channel counts reported by the media
backend, rather than assuming 1.
"""

import asyncio
import logging
import math
import time
from collections.abc import AsyncIterator
from typing import Any

import numpy as np

from hugo.robot.motion_io import HeadOffsets

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 0.01
DAEMON_CONNECT_RETRIES = 3
DAEMON_CONNECT_RETRY_DELAY_S = 20.0


class ReachyMiniClient:
    def __init__(self, use_sim: bool = False, playback_gain: float = 1.0) -> None:
        from reachy_mini import ReachyMini

        self._robot = self._connect_with_retries(ReachyMini, use_sim)
        self._media = self._robot.media
        # Software gain on all speaker output: the media backend exposes no
        # volume control at all (confirmed by inspecting MediaManager on
        # dgx1, 2026-07-23), and the robot is audibly too quiet at unity.
        # Applied in float space with clipping (_float32_to_pcm16 clips).
        self._playback_gain = playback_gain
        self.input_sample_rate_hz: int = self._media.get_input_audio_samplerate()
        self.output_sample_rate_hz: int = self._media.get_output_audio_samplerate()
        self.input_channels: int = self._media.get_input_channels()
        self.output_channels: int = self._media.get_output_channels()

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
            yield _float32_to_pcm16(_downmix_to_mono(sample))

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

    async def clear_playback(self) -> None:
        # MediaManager doesn't proxy clear_player like it does the other
        # audio methods (confirmed live on dgx1: AttributeError mid
        # barge-in, 2026-07-22) — reach through its public `.audio`
        # backend attribute instead.
        await asyncio.to_thread(self._media.audio.clear_player)

    async def play_audio(self, pcm16_chunk: bytes) -> None:
        boosted = soft_clip(_pcm16_to_float32(pcm16_chunk) * self._playback_gain)
        samples = _upmix_mono(boosted.astype(np.float32), self.output_channels)
        await asyncio.to_thread(self._media.push_audio_sample, samples)

    async def goto_sleep(self) -> None:
        """Moves the robot to its rest posture (the SDK's own sleep pose) —
        the physical cue that HUGO is off (VEN-56; CONTEXT.md: Sleep)."""
        await asyncio.to_thread(self._robot.goto_sleep)

    async def wake_up(self) -> None:
        """Stands the robot back up from rest posture. Without this every
        start after a sleep left HUGO talking while physically slumped —
        which reads as 'still asleep' no matter what the voice does
        (live user report, 2026-07-23)."""
        await asyncio.to_thread(self._robot.wake_up)

    # --- RobotMotion (VEN-57): motor commands ride the daemon's WebSocket
    # control channel, independent of the media pipeline above, so these
    # are safe to issue while capture/playback is live.

    async def set_motion_target(
        self, head: HeadOffsets | None, antennas: tuple[float, float] | None
    ) -> None:
        await asyncio.to_thread(
            self._robot.set_target,
            head=None if head is None else _head_pose_matrix(head),
            antennas=None if antennas is None else list(antennas),
        )

    async def goto(
        self,
        head: HeadOffsets | None,
        antennas: tuple[float, float] | None,
        duration_s: float,
    ) -> None:
        await asyncio.to_thread(
            self._robot.goto_target,
            head=None if head is None else _head_pose_matrix(head),
            antennas=None if antennas is None else list(antennas),
            duration=duration_s,
            # The SDK default is 0.0 which COMMANDS zero body yaw; None
            # means keep the current yaw, which is what a head/antenna
            # transition wants.
            body_yaw=None,
        )

    async def hold_current_head_pose(self) -> None:
        def _hold() -> None:
            self._robot.set_target(head=self._robot.get_current_head_pose())

        await asyncio.to_thread(_hold)

    async def enable_wobbling(self) -> None:
        await asyncio.to_thread(self._robot.enable_wobbling)

    async def disable_wobbling(self) -> None:
        await asyncio.to_thread(self._robot.disable_wobbling)

    async def set_head_tracking(self, weight: float) -> None:
        await asyncio.to_thread(self._robot.start_head_tracking, weight)

    async def stop_head_tracking(self) -> None:
        await asyncio.to_thread(self._robot.stop_head_tracking)

    def close(self) -> None:
        self._robot.release_media()


def _head_pose_matrix(offsets: HeadOffsets) -> np.ndarray:
    """4x4 head pose from neutral-relative offsets, matching the SDK's
    frame (x forward, y left, z up; INIT_HEAD_POSE is identity):
    R = Rz(yaw) @ Ry(pitch) @ Rx(roll), translation in meters."""
    cr, sr = math.cos(offsets.roll_rad), math.sin(offsets.roll_rad)
    cp, sp = math.cos(offsets.pitch_rad), math.sin(offsets.pitch_rad)
    cy, sy = math.cos(offsets.yaw_rad), math.sin(offsets.yaw_rad)
    rx = np.array([[1.0, 0.0, 0.0], [0.0, cr, -sr], [0.0, sr, cr]])
    ry = np.array([[cp, 0.0, sp], [0.0, 1.0, 0.0], [-sp, 0.0, cp]])
    rz = np.array([[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]])
    pose = np.eye(4)
    pose[:3, :3] = rz @ ry @ rx
    pose[:3, 3] = (offsets.x_m, offsets.y_m, offsets.z_m)
    return pose


# Where the saturation curve starts. Below the knee the signal is
# untouched; above it, a tanh blend approaches 1.0 asymptotically.
_SOFT_CLIP_KNEE = 0.85


def soft_clip(samples: np.ndarray) -> np.ndarray:
    """Saturates gently instead of hard-clipping. The first live VEN-56
    session ran gain 2.0 through np.clip and every loud syllable
    distorted audibly ('annoying') — hard clipping squares off peaks into
    harmonic hash. This keeps the waveform inside [-1, 1] with a smooth
    knee instead."""
    magnitude = np.abs(samples)
    over = magnitude > _SOFT_CLIP_KNEE
    if not np.any(over):
        return samples
    headroom = 1.0 - _SOFT_CLIP_KNEE
    saturated = _SOFT_CLIP_KNEE + headroom * np.tanh((magnitude[over] - _SOFT_CLIP_KNEE) / headroom)
    out = samples.copy()
    out[over] = np.sign(samples[over]) * saturated
    return out


def _float32_to_pcm16(samples: np.ndarray) -> bytes:
    clipped = np.clip(samples, -1.0, 1.0)
    return bytes((clipped * 32767).astype(np.int16).tobytes())


def _pcm16_to_float32(pcm16: bytes) -> np.ndarray:
    ints = np.frombuffer(pcm16, dtype=np.int16)
    return ints.astype(np.float32) / 32768.0


def _downmix_to_mono(samples: np.ndarray) -> np.ndarray:
    """Averages a (N, channels) capture buffer down to mono (N,). Lossless
    for the ReSpeaker on dgx1, whose channels were confirmed byte-identical
    (2026-07-14) — averaging is still the correct general behavior if that
    ever changes (e.g. a mic with genuinely distinct L/R content)."""
    if samples.ndim == 1:
        return samples
    return samples.mean(axis=1).astype(np.float32)


def _upmix_mono(samples: np.ndarray, channels: int) -> np.ndarray:
    """Duplicates a mono (N,) playback buffer across `channels` output
    channels, matching the shape push_audio_sample's sink actually expects
    (see AudioBase.push_audio_sample: mono is (N,), multi-channel is
    (N, channels)) — HUGO only ever synthesizes mono audio, so every output
    channel gets the same content."""
    if channels == 1:
        return samples
    return np.tile(samples[:, None], (1, channels))
