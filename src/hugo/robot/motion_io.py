"""Protocol for the robot's expressive motion (VEN-57), so the motion
layer can be built and tested against a fake without the reachy_mini SDK
installed — the same seam pattern as RobotAudioIO.

Motion rides the daemon's WebSocket control channel, which is independent
of the single-owner media pipeline — commanding motors while audio
capture/playback is live is safe (verified across the Reachy Mini
ecosystem and by the wake listener's stand-up, 2026-07-23).

Units are the SDK's: meters and radians. Head offsets are relative to the
neutral upright pose (the SDK's INIT_HEAD_POSE identity). Antennas are
(right, left) joint angles; the SDK's neutral is (-0.1745, +0.1745) —
the ~10° off-vertical offset is deliberate (dead-vertical resonates).
"""

from dataclasses import dataclass
from typing import Literal, Protocol

# Conversation-state cues the voice loop emits for the motion layer.
# "wake" is a fresh wake word (or barge-in) and gets the attentive perk;
# "listening" is the follow-up window reopening after HUGO spoke.
MotionCue = Literal[
    "wake",
    "listening",
    "user_speech_start",
    "thinking",
    "speaking",
    "conversation_end",
]


@dataclass(frozen=True)
class HeadOffsets:
    """A head pose as offsets from neutral upright: translation in meters,
    rotation in radians (roll about x/forward, pitch about y/left —
    positive pitch is nose-down — yaw about z/up)."""

    x_m: float = 0.0
    y_m: float = 0.0
    z_m: float = 0.0
    roll_rad: float = 0.0
    pitch_rad: float = 0.0
    yaw_rad: float = 0.0


class RobotMotion(Protocol):
    async def set_motion_target(
        self, head: HeadOffsets | None, antennas: tuple[float, float] | None
    ) -> None:
        """Immediate target for the ~25Hz motion loop. Pass None to leave
        that subsystem's target untouched."""
        ...

    async def goto(
        self,
        head: HeadOffsets | None,
        antennas: tuple[float, float] | None,
        duration_s: float,
    ) -> None:
        """Server-interpolated transition move; returns when it completes."""
        ...

    async def hold_current_head_pose(self) -> None:
        """Re-commands the head's *current* pose as the app target, so that
        pausing daemon face tracking (which blends back toward the app
        target) doesn't snap the head away from wherever tracking left it."""
        ...

    async def enable_wobbling(self) -> None:
        """Daemon-composed audio-reactive head motion, driven by the audio
        we push to the speaker (speech-synced talking bob)."""
        ...

    async def disable_wobbling(self) -> None: ...

    async def set_head_tracking(self, weight: float) -> None:
        """Daemon-side face tracking blend: 1.0 = tracking owns the head,
        0.0 = paused (app target owns the head) but warm for cheap resume."""
        ...

    async def stop_head_tracking(self) -> None: ...
