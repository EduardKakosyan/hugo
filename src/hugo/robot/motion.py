"""Single-writer motion behavior layer: HUGO's body language (VEN-57).

Maps conversation state (cues from the voice loop) to expressive motion:

    idle              STILL at neutral — motion is communication, not
                      ambient decoration (live user feedback 2026-07-23:
                      idle breathing read as senseless movement; HUGO
                      only moves when listening/thinking/speaking)
    attentive         perk (goto) then hold still; face tracking active
    user_speech_hold  frozen: pose held, tracking paused at weight 0
    thinking          subtle one-antenna sway filling STT+LLM latency
    speaking          antenna wag; head = held anchor + the SDK's wobbler

Amplitudes are deliberately small: the ecosystem-canonical values were
tried live and read as far too much motion on a desk at arm's length —
current values are roughly half or less (same feedback session).

Hard rules encoded here — every one is a documented Reachy Mini hardware
failure mode (VEN-57 research, 2026-07-23), not taste:

- ONE writer: this manager's task is the only motor commander while it
  runs, and transition moves (goto) are awaited inline so nothing ever
  preempts an in-flight interpolation — a fast cancel/replay desyncs the
  daemon's 100Hz serial stream into an all-motor fault.
- ~25Hz ticks, not 100: per-tick micro-deltas at high rate visibly
  jitter the Stewart platform (conversation-app issue #224).
- Send-deadband: targets that barely changed are not re-sent — constant
  idle bus traffic caused real "motor communication error"s in community
  projects.
- Slew limit on head targets, so a bug can't command a violent swing.
- Stillness while the user speaks: head/antenna servos are audible
  centimeters from the mics and HUGO has no AEC. Every shipped Reachy
  Mini assistant converged on freeze-while-listening to protect STT.

What is deliberately NOT here: speech-synced head bobbing (the SDK's
wobbler, enabled once at start(), analyses the TTS audio we push and
composes offsets daemon-side on top of whatever this manager commands)
and face detection (daemon-side head tracking; this manager only toggles
its blend weight). Idle breathing and randomized "presence" emotes were
in the original VEN-57 design and are intentionally absent — see the
idle-means-still feedback above before reintroducing anything ambient.
"""

import asyncio
import contextlib
import logging
import math
from typing import Literal

from hugo.robot.motion_io import HeadOffsets, MotionCue, RobotMotion

logger = logging.getLogger(__name__)

MotionState = Literal["idle", "attentive", "user_speech_hold", "thinking", "speaking"]

TICK_S = 0.04  # 25Hz

# (right, left) — the SDK's neutral, ~10° off-vertical (vertical resonates).
NEUTRAL_ANTENNAS = (-0.1745, 0.1745)
NEUTRAL_HEAD = HeadOffsets()

# Attentive perk: slight rise and nose-up, antennas nearly vertical.
ATTENTIVE_HEAD = HeadOffsets(z_m=0.004, pitch_rad=math.radians(-4))
ATTENTIVE_ANTENNAS = (-0.06, 0.06)
PERK_DURATION_S = 0.4
# Follow-up listening reuses the antenna pose without the head perk.
REJOIN_DURATION_S = 0.3
NEUTRAL_RETURN_S = 1.0

# Thinking: the right antenna droops a little and sways slowly — "hmm".
THINKING_ANTENNA_CENTER_RAD = -0.2
THINKING_ANTENNA_AMPLITUDE_RAD = math.radians(3)
THINKING_ANTENNA_FREQ_HZ = 0.4

# Speaking wag: brisk but small, on top of the attentive pose.
WAG_AMPLITUDE_RAD = math.radians(5)
WAG_FREQ_HZ = 1.2

# Send-deadband and slew limits (community-measured values).
TRANSLATION_DEADBAND_M = 0.0005
ROTATION_DEADBAND_RAD = math.radians(0.35)
ANTENNA_DEADBAND_RAD = math.radians(1.5)
MAX_TRANSLATION_PER_TICK_M = 0.005
MAX_ROTATION_PER_TICK_RAD = math.radians(2.0)

_ERROR_LOG_INTERVAL_S = 5.0


def _clamped(value: float, last: float, max_delta: float) -> float:
    return max(last - max_delta, min(last + max_delta, value))


def slew_limited_head(last: HeadOffsets | None, desired: HeadOffsets) -> HeadOffsets:
    """Caps how far a head target may move from the last sent one in a
    single tick, so no single command can demand a violent swing."""
    if last is None:
        return desired
    return HeadOffsets(
        x_m=_clamped(desired.x_m, last.x_m, MAX_TRANSLATION_PER_TICK_M),
        y_m=_clamped(desired.y_m, last.y_m, MAX_TRANSLATION_PER_TICK_M),
        z_m=_clamped(desired.z_m, last.z_m, MAX_TRANSLATION_PER_TICK_M),
        roll_rad=_clamped(desired.roll_rad, last.roll_rad, MAX_ROTATION_PER_TICK_RAD),
        pitch_rad=_clamped(desired.pitch_rad, last.pitch_rad, MAX_ROTATION_PER_TICK_RAD),
        yaw_rad=_clamped(desired.yaw_rad, last.yaw_rad, MAX_ROTATION_PER_TICK_RAD),
    )


def head_if_changed(last: HeadOffsets | None, desired: HeadOffsets) -> HeadOffsets | None:
    """None if the target moved less than the send-deadband."""
    if last is None:
        return desired
    translations_close = (
        abs(desired.x_m - last.x_m) < TRANSLATION_DEADBAND_M
        and abs(desired.y_m - last.y_m) < TRANSLATION_DEADBAND_M
        and abs(desired.z_m - last.z_m) < TRANSLATION_DEADBAND_M
    )
    rotations_close = (
        abs(desired.roll_rad - last.roll_rad) < ROTATION_DEADBAND_RAD
        and abs(desired.pitch_rad - last.pitch_rad) < ROTATION_DEADBAND_RAD
        and abs(desired.yaw_rad - last.yaw_rad) < ROTATION_DEADBAND_RAD
    )
    return None if translations_close and rotations_close else desired


def antennas_if_changed(
    last: tuple[float, float] | None, desired: tuple[float, float]
) -> tuple[float, float] | None:
    """None if both antenna targets moved less than the send-deadband."""
    if last is None:
        return desired
    if (
        abs(desired[0] - last[0]) < ANTENNA_DEADBAND_RAD
        and abs(desired[1] - last[1]) < ANTENNA_DEADBAND_RAD
    ):
        return None
    return desired


class MotionManager:
    """Owns the motion task; the voice loop only posts cues (sync, instant)
    and this task applies them — entry transitions first, then the per-state
    procedural layer at tick rate."""

    def __init__(self, robot: RobotMotion, tick_s: float = TICK_S) -> None:
        self._robot = robot
        self._tick_s = tick_s
        self.state: MotionState = "idle"
        self._pending_cue: MotionCue | None = None
        self._cue_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._sent_head: HeadOffsets | None = None
        self._sent_antennas: tuple[float, float] | None = None
        self._phase_started_at = 0.0
        self._last_error_logged_at = 0.0

    async def start(self) -> None:
        # Wobbling is a robot-level toggle, on for the manager's lifetime:
        # it only moves the head while speaker audio actually plays, so
        # there is nothing to gate. Best-effort — cosmetic motion must
        # never block startup.
        try:
            await self._robot.enable_wobbling()
        except Exception:
            logger.exception("enabling speech wobble failed; continuing without it")
        self._phase_started_at = asyncio.get_running_loop().time()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stops commanding motors (so shutdown's goto_sleep isn't fought
        by a breathing tick) and turns the daemon toggles back off."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        for cleanup in (self._robot.disable_wobbling, self._robot.stop_head_tracking):
            try:
                await cleanup()
            except Exception:
                logger.exception("motion cleanup step failed; continuing")

    def cue(self, cue: MotionCue) -> None:
        """Called by the voice loop on conversation-state transitions.
        Never blocks; the motion task applies it within a tick (or after
        the current transition move completes — in-flight gotos are never
        preempted)."""
        self._pending_cue = cue
        self._cue_event.set()

    async def _run(self) -> None:
        while True:
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(self._tick_s):
                    await self._cue_event.wait()
            cue = self._pending_cue
            self._pending_cue = None
            self._cue_event.clear()
            try:
                if cue is not None:
                    await self._enter(cue)
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Cosmetic layer: a motor hiccup must never kill the task,
                # and a persistent fault must not flood the journal.
                now = asyncio.get_running_loop().time()
                if now - self._last_error_logged_at >= _ERROR_LOG_INTERVAL_S:
                    self._last_error_logged_at = now
                    logger.exception("motion tick failed in state %s; continuing", self.state)

    async def _enter(self, cue: MotionCue) -> None:
        now = asyncio.get_running_loop().time()
        if cue == "wake":
            # Perk first, then hand the head to tracking — the other way
            # round, tracking owns the head and the perk never shows.
            await self._robot.goto(ATTENTIVE_HEAD, ATTENTIVE_ANTENNAS, PERK_DURATION_S)
            self._sent_head, self._sent_antennas = ATTENTIVE_HEAD, ATTENTIVE_ANTENNAS
            await self._robot.set_head_tracking(1.0)
            self.state = "attentive"
        elif cue == "listening":
            # Follow-up window reopening: no re-perk, just settle the
            # antennas out of the speaking wag and resume gaze corrections.
            await self._robot.goto(None, ATTENTIVE_ANTENNAS, REJOIN_DURATION_S)
            self._sent_antennas = ATTENTIVE_ANTENNAS
            await self._robot.set_head_tracking(1.0)
            self.state = "attentive"
        elif cue == "user_speech_start":
            # Freeze: hold the head where tracking aimed it (the anchor —
            # also where the head stays pointed while speaking), then pause
            # tracking so its corrections stop making servo noise into the
            # open mic.
            await self._robot.hold_current_head_pose()
            self._sent_head = None
            await self._robot.set_head_tracking(0.0)
            self.state = "user_speech_hold"
        elif cue == "thinking":
            self._phase_started_at = now
            self.state = "thinking"
        elif cue == "speaking":
            self._phase_started_at = now
            self.state = "speaking"
        elif cue == "conversation_end":
            await self._robot.stop_head_tracking()
            await self._robot.goto(NEUTRAL_HEAD, NEUTRAL_ANTENNAS, NEUTRAL_RETURN_S)
            self._sent_head, self._sent_antennas = NEUTRAL_HEAD, NEUTRAL_ANTENNAS
            self._phase_started_at = now
            self.state = "idle"

    async def _tick(self) -> None:
        t = asyncio.get_running_loop().time() - self._phase_started_at
        if self.state == "thinking":
            sway = math.sin(2 * math.pi * THINKING_ANTENNA_FREQ_HZ * t)
            await self._send(
                None,
                (
                    THINKING_ANTENNA_CENTER_RAD + THINKING_ANTENNA_AMPLITUDE_RAD * sway,
                    ATTENTIVE_ANTENNAS[1],
                ),
            )
        elif self.state == "speaking":
            wag = WAG_AMPLITUDE_RAD * math.sin(2 * math.pi * WAG_FREQ_HZ * t)
            await self._send(None, (ATTENTIVE_ANTENNAS[0] + wag, ATTENTIVE_ANTENNAS[1] + wag))
        # "idle", "attentive" and "user_speech_hold" deliberately send
        # nothing: stillness is the behavior (and while attentive/held the
        # head belongs to tracking or the held anchor).

    async def _send(self, head: HeadOffsets | None, antennas: tuple[float, float] | None) -> None:
        head_to_send: HeadOffsets | None = None
        if head is not None:
            limited = slew_limited_head(self._sent_head, head)
            head_to_send = head_if_changed(self._sent_head, limited)
        antennas_to_send = (
            None if antennas is None else antennas_if_changed(self._sent_antennas, antennas)
        )
        if head_to_send is None and antennas_to_send is None:
            return
        await self._robot.set_motion_target(head_to_send, antennas_to_send)
        if head_to_send is not None:
            self._sent_head = head_to_send
        if antennas_to_send is not None:
            self._sent_antennas = antennas_to_send
