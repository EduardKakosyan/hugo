"""Single-writer motion behavior layer: HUGO's body language (VEN-57).

Maps conversation state (cues from the voice loop) to expressive motion:

    idle              STILL at neutral — motion is communication, not
                      ambient decoration (live user feedback 2026-07-23:
                      idle breathing read as senseless movement; HUGO
                      only moves when listening/thinking/speaking)
    attentive         perk (goto) then hold still
    user_speech_hold  frozen while the user talks
    thinking          subtle one-antenna sway filling STT+LLM latency
                      (which antenna / depth / tempo re-rolled per turn)
    speaking          mood-steered antenna wag + gentle head nod: the LLM
                      tags each reply ([cheerful], [thoughtful], ... —
                      see tool_loop) and the tag picks the SpeakingStyle

Amplitudes are deliberately small: the ecosystem-canonical values were
tried live and read as far too much motion on a desk at arm's length —
current values are roughly half or less (same feedback session).

The daemon's built-in wobbler and face tracking are OFF by default
(use_wobbler/use_head_tracking): both were tried live (2026-07-23) and
produced wild, uncontrollable movement — tracking ran BLIND because this
install's camera path is broken (unixfdsrc is an unpackaged Rust
GStreamer plugin, like the known webrtcsink gap) and swung the head at
garbage targets, and the wobbler's amplitudes are SDK-fixed (yaw 7.5°,
×1.5 gain) with our boosted playback gain pinning its loudness envelope
near max. Re-enable tracking only after the camera demonstrably works;
re-enable the wobbler only with a gain we control (port speech_tapper).

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
import random
from dataclasses import dataclass
from typing import Literal

from hugo.robot.motion_io import HeadOffsets, MotionCue, RobotMotion

logger = logging.getLogger(__name__)

MotionState = Literal["idle", "attentive", "user_speech_hold", "thinking", "speaking"]

TICK_S = 0.04  # 25Hz

# (right, left) — the SDK's neutral, ~10° off-vertical (vertical resonates).
NEUTRAL_ANTENNAS = (-0.1745, 0.1745)
NEUTRAL_HEAD = HeadOffsets()

# Rest-posture correction: the SDK sleep pose drops the head 44mm onto the
# body, right over the mic ports — with the head fully folded, the sleeping
# ear's wake scores collapsed to ~0.02 for real speech while in-session
# detection heard the same voice at 0.5+ ("no way of waking it up", live
# 2026-07-23). After the SDK fold, the head eases back up to here: still
# slumped and clearly asleep (nose down 24°, antennas stay folded), but the
# mics stay in the clear.
SLEEP_EAR_OPEN_HEAD = HeadOffsets(x_m=-0.01, z_m=-0.02, pitch_rad=math.radians(24))

# Attentive perk: slight rise and nose-up, antennas nearly vertical.
ATTENTIVE_HEAD = HeadOffsets(z_m=0.004, pitch_rad=math.radians(-4))
ATTENTIVE_ANTENNAS = (-0.06, 0.06)
PERK_DURATION_S = 0.4
# Follow-up listening reuses the antenna pose without the head perk.
REJOIN_DURATION_S = 0.3
NEUTRAL_RETURN_S = 1.0

# Thinking: one antenna droops a little and sways slowly — "hmm". Base
# values; each entry jitters them (and picks which antenna muses) via the
# manager's rng so consecutive turns don't look copy-pasted.
THINKING_ANTENNA_CENTER_RAD = -0.2
THINKING_ANTENNA_AMPLITUDE_RAD = math.radians(3)
THINKING_ANTENNA_FREQ_HZ = 0.4


@dataclass(frozen=True)
class SpeakingStyle:
    """How the body talks: antenna wag + gentle head nod around the
    attentive pose (our controllable stand-in for the SDK wobbler).
    antenna_lift_rad raises (+) or droops (-) both antennas from the
    attentive stance while the mood lasts."""

    wag_freq_hz: float
    wag_amplitude_rad: float
    nod_amplitude_rad: float
    antenna_lift_rad: float


# Keyed by the LLM's reply mood tag (tool_loop.MOODS): the model already
# knows what it's about to say, so IT picks how the body says it — no
# separate "movement model" needed (VEN-57). All values stay inside the
# small-motion discipline.
SPEAKING_STYLES: dict[str, SpeakingStyle] = {
    "neutral": SpeakingStyle(1.2, math.radians(5), math.radians(1.5), 0.0),
    "cheerful": SpeakingStyle(1.6, math.radians(6), math.radians(2.0), math.radians(4)),
    "excited": SpeakingStyle(2.0, math.radians(7), math.radians(2.5), math.radians(6)),
    "thoughtful": SpeakingStyle(0.7, math.radians(3), math.radians(1.0), -math.radians(4)),
    "apologetic": SpeakingStyle(0.6, math.radians(2.5), math.radians(1.0), -math.radians(8)),
    "curious": SpeakingStyle(1.0, math.radians(4), math.radians(1.5), math.radians(2)),
}


def speaking_style(mood: str) -> SpeakingStyle:
    """Unknown/garbled tags fall back to neutral — the LLM free-texts the
    tag, so this must never raise."""
    return SPEAKING_STYLES.get(mood, SPEAKING_STYLES["neutral"])


# Send-deadband and slew limits (community-measured values).
TRANSLATION_DEADBAND_M = 0.0005
ROTATION_DEADBAND_RAD = math.radians(0.35)
ANTENNA_DEADBAND_RAD = math.radians(1.5)
MAX_TRANSLATION_PER_TICK_M = 0.005
MAX_ROTATION_PER_TICK_RAD = math.radians(2.0)
MAX_ANTENNA_PER_TICK_RAD = math.radians(3.0)

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


def slew_limited_antennas(
    last: tuple[float, float] | None, desired: tuple[float, float]
) -> tuple[float, float]:
    """Caps antenna target jumps per tick so state changes ease in
    instead of snapping (an instant 8° droop read as a twitch live)."""
    if last is None:
        return desired
    return (
        _clamped(desired[0], last[0], MAX_ANTENNA_PER_TICK_RAD),
        _clamped(desired[1], last[1], MAX_ANTENNA_PER_TICK_RAD),
    )


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

    def __init__(
        self,
        robot: RobotMotion,
        tick_s: float = TICK_S,
        use_wobbler: bool = False,
        use_head_tracking: bool = False,
        rng: random.Random | None = None,
    ) -> None:
        self._robot = robot
        self._tick_s = tick_s
        # Daemon built-ins, off by default — see the module docstring for
        # the live failure that parked them.
        self._use_wobbler = use_wobbler
        self._use_head_tracking = use_head_tracking
        # Injected for deterministic tests; jitters gesture parameters per
        # state entry so motion never feels copy-pasted between turns.
        self._rng = rng if rng is not None else random.Random()
        self._mood = "neutral"
        self._think_right = True
        self._think_center_rad = THINKING_ANTENNA_CENTER_RAD
        self._think_amplitude_rad = THINKING_ANTENNA_AMPLITUDE_RAD
        self._think_freq_hz = THINKING_ANTENNA_FREQ_HZ
        self._speak_freq_jitter = 1.0
        self._speak_phase = 0.0
        self.state: MotionState = "idle"
        self._pending_cue: MotionCue | None = None
        self._cue_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._sent_head: HeadOffsets | None = None
        self._sent_antennas: tuple[float, float] | None = None
        self._phase_started_at = 0.0
        self._last_error_logged_at = 0.0

    async def start(self) -> None:
        if self._use_wobbler:
            # Best-effort — cosmetic motion must never block startup.
            try:
                await self._robot.enable_wobbling()
            except Exception:
                logger.exception("enabling speech wobble failed; continuing without it")
        self._phase_started_at = asyncio.get_running_loop().time()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stops commanding motors (so shutdown's goto_sleep isn't fought
        by a motion tick) and turns the daemon toggles back off. The
        toggle-offs run unconditionally: they also clear state a previous
        (differently-configured) run may have left enabled in the daemon."""
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

    def set_mood(self, mood: str) -> None:
        """From the LLM's reply tag, via the tool loop: steers the
        speaking style from the next tick. Unknown tags mean neutral;
        never raises (the tag is model-generated free text)."""
        self._mood = mood if mood in SPEAKING_STYLES else "neutral"

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
            # Perk first, then (if enabled) hand the head to tracking —
            # the other way round, tracking owns the head and the perk
            # never shows.
            await self._robot.goto(ATTENTIVE_HEAD, ATTENTIVE_ANTENNAS, PERK_DURATION_S)
            self._sent_head, self._sent_antennas = ATTENTIVE_HEAD, ATTENTIVE_ANTENNAS
            if self._use_head_tracking:
                await self._robot.set_head_tracking(1.0)
            self._mood = "neutral"
            self.state = "attentive"
        elif cue == "listening":
            # Follow-up window reopening: no re-perk, just settle the
            # antennas out of the speaking wag (and resume gaze corrections
            # when tracking is on).
            await self._robot.goto(None, ATTENTIVE_ANTENNAS, REJOIN_DURATION_S)
            self._sent_antennas = ATTENTIVE_ANTENNAS
            if self._use_head_tracking:
                await self._robot.set_head_tracking(1.0)
            self.state = "attentive"
        elif cue == "user_speech_start":
            if self._use_head_tracking:
                # Freeze: hold the head where tracking aimed it (the
                # anchor), then pause tracking so its corrections stop
                # making servo noise into the open mic.
                await self._robot.hold_current_head_pose()
                self._sent_head = None
                await self._robot.set_head_tracking(0.0)
            self.state = "user_speech_hold"
        elif cue == "thinking":
            # A fresh "hmm" every turn: which antenna muses, how deep the
            # droop, how fast the sway — never the same twice in a row.
            self._think_right = self._rng.random() < 0.5
            self._think_center_rad = THINKING_ANTENNA_CENTER_RAD * self._rng.uniform(0.7, 1.2)
            self._think_amplitude_rad = THINKING_ANTENNA_AMPLITUDE_RAD * self._rng.uniform(0.7, 1.3)
            self._think_freq_hz = THINKING_ANTENNA_FREQ_HZ * self._rng.uniform(0.7, 1.3)
            self._phase_started_at = now
            self.state = "thinking"
        elif cue == "speaking":
            # The mood (set by the reply's tag just before first audio)
            # picks the style; jitter keeps identical moods from looking
            # identical.
            self._speak_freq_jitter = self._rng.uniform(0.85, 1.15)
            self._speak_phase = self._rng.uniform(0.0, 2.0 * math.pi)
            self._phase_started_at = now
            self.state = "speaking"
        elif cue == "conversation_end":
            if self._use_head_tracking:
                await self._robot.stop_head_tracking()
            await self._robot.goto(NEUTRAL_HEAD, NEUTRAL_ANTENNAS, NEUTRAL_RETURN_S)
            self._sent_head, self._sent_antennas = NEUTRAL_HEAD, NEUTRAL_ANTENNAS
            self._mood = "neutral"
            self._phase_started_at = now
            self.state = "idle"

    async def _tick(self) -> None:
        t = asyncio.get_running_loop().time() - self._phase_started_at
        if self.state == "thinking":
            sway = math.sin(2 * math.pi * self._think_freq_hz * t)
            # Signed in the right antenna's convention; mirrored for left.
            droop = self._think_center_rad + self._think_amplitude_rad * sway
            if self._think_right:
                antennas = (droop, ATTENTIVE_ANTENNAS[1])
            else:
                antennas = (ATTENTIVE_ANTENNAS[0], -droop)
            await self._send(None, antennas)
        elif self.state == "speaking":
            style = speaking_style(self._mood)
            phase = math.sin(
                2 * math.pi * style.wag_freq_hz * self._speak_freq_jitter * t + self._speak_phase
            )
            wag = style.wag_amplitude_rad * phase
            head: HeadOffsets | None = None
            if not self._use_head_tracking:
                # With tracking off the head is ours: a gentle nod around
                # the attentive pose, amplitude we control — the stand-in
                # for the SDK wobbler (whose gains are fixed and read as
                # wild on this robot, live 2026-07-23).
                head = HeadOffsets(
                    z_m=ATTENTIVE_HEAD.z_m,
                    pitch_rad=ATTENTIVE_HEAD.pitch_rad + style.nod_amplitude_rad * phase,
                )
            await self._send(
                head,
                (
                    # Lift is toward-vertical for both antennas (their signs
                    # mirror); the wag rides on top, same-signed = seesaw.
                    ATTENTIVE_ANTENNAS[0] + style.antenna_lift_rad + wag,
                    ATTENTIVE_ANTENNAS[1] - style.antenna_lift_rad + wag,
                ),
            )
        # "idle", "attentive" and "user_speech_hold" deliberately send
        # nothing: stillness is the behavior (and while attentive/held the
        # head belongs to the perk pose, tracking, or the held anchor).

    async def _send(self, head: HeadOffsets | None, antennas: tuple[float, float] | None) -> None:
        head_to_send: HeadOffsets | None = None
        if head is not None:
            limited = slew_limited_head(self._sent_head, head)
            head_to_send = head_if_changed(self._sent_head, limited)
        antennas_to_send: tuple[float, float] | None = None
        if antennas is not None:
            eased = slew_limited_antennas(self._sent_antennas, antennas)
            antennas_to_send = antennas_if_changed(self._sent_antennas, eased)
        if head_to_send is None and antennas_to_send is None:
            return
        await self._robot.set_motion_target(head_to_send, antennas_to_send)
        if head_to_send is not None:
            self._sent_head = head_to_send
        if antennas_to_send is not None:
            self._sent_antennas = antennas_to_send
