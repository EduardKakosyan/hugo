"""Always-on minimal wake listener — HUGO's ear while it sleeps (VEN-56
follow-up: "hey jarvis" must wake it from a full sleep).

Runs permanently as its own systemd user service (deploy/hugo-wake.service)
and SELF-GATES on hugo.service's state rather than using unit Conflicts=:
an earlier Conflicts+ExecStopPost design made `systemctl restart hugo`
cancel its own start job (observed live, 2026-07-23). While hugo is
active or activating, this just polls; while hugo is down, it holds the
robot mic and listens. Footprint is deliberately tiny — the wake-word
model on CPU, no GPU, no model servers — so the 121GB pool stays free
while HUGO sleeps (ADR 0002's spirit holds).

On detection it plays the wake chime (the audible "heard you — waking
up"), releases the robot's single-owner media pipeline, and asks systemd
to start hugo. If hugo starts by other means (CLI, another terminal),
the poll notices and the mic is released just the same.

Deliberately chime-only, no motor stand-up: an immediate stand-up on
detection was tried (2026-07-23) and rejected live — the robot then
stands motionless through the minutes-long model load, which reads as
senseless. The body stays in rest posture until the voice loop is
actually ready; the orchestrator's wake_up right before "I'm awake." IS
the physical "load done" cue (VEN-57 as revised).
"""

import asyncio
import contextlib
import logging
import subprocess

from hugo.config import Config, load_config
from hugo.logging_setup import configure_logging
from hugo.robot.audio_io import RobotAudioIO
from hugo.voice.chime import wake_chime_pcm16
from hugo.voice.loop import WakeWordListener

logger = logging.getLogger(__name__)

# Lets the chime drain through the robot's playback queue before the
# media pipeline is released.
_CHIME_DRAIN_S = 0.6
_POLL_INTERVAL_S = 5.0


async def listen_until_wake(robot: RobotAudioIO, wake_word: WakeWordListener) -> None:
    """Consumes mic frames until the wake word fires, then chimes."""
    wake_word.reset()
    frame_count = 0
    peak_score = 0.0
    async for frame in robot.read_mic_frames():
        fired = wake_word.feed(frame)
        peak_score = max(peak_score, wake_word.last_score)
        frame_count += 1
        # Same telemetry the voice loop's IDLE state has: without it, "said
        # the wake word, nothing happened" is undiagnosable — no way to
        # tell a dead mic (frames stop) from a low score (live user
        # report, 2026-07-23).
        if frame_count % 500 == 0:
            logger.info(
                "asleep: %d frames seen, peak wake score %.3f over last ~5s",
                frame_count,
                peak_score,
            )
            peak_score = 0.0
        if fired:
            logger.info("wake word heard while asleep")
            await robot.play_audio(wake_chime_pcm16(robot.output_sample_rate_hz))
            await asyncio.sleep(_CHIME_DRAIN_S)
            return


async def _hugo_service_state() -> str:
    proc = await asyncio.create_subprocess_exec(
        "systemctl",
        "--user",
        "is-active",
        "hugo.service",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()
    return stdout.decode().strip()


def _is_up(state: str) -> bool:
    # "activating" counts as up: hugo's robot connect starts early in its
    # minutes-long startup, and the media pipeline is single-owner.
    return state in ("active", "activating", "reloading")


async def _wait_until_hugo_up() -> None:
    # Genuine polling of external state (systemd) — there is no event to
    # await, hence the ASYNC110 suppression.
    while not _is_up(await _hugo_service_state()):  # noqa: ASYNC110
        await asyncio.sleep(_POLL_INTERVAL_S)


async def _listen_while_hugo_down(config: Config) -> bool:
    """Holds the mic until the wake word fires (True) or hugo comes up by
    other means (False). Releases the media pipeline either way."""
    from hugo.robot.reachy_client import ReachyMiniClient
    from hugo.voice.wake_word import WakeWordDetector

    robot = ReachyMiniClient(playback_gain=config.playback_gain)
    wake_word = WakeWordDetector(model_name=config.wake_word)
    await robot.start_recording()
    await robot.start_playing()
    listen_task = asyncio.ensure_future(listen_until_wake(robot, wake_word))
    hugo_up_task = asyncio.ensure_future(_wait_until_hugo_up())
    try:
        logger.info("asleep and listening — say '%s' to wake hugo", config.wake_word)
        done, pending = await asyncio.wait(
            {listen_task, hugo_up_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        return listen_task in done
    finally:
        await robot.stop_recording()
        robot.close()


async def run() -> None:
    config = load_config()
    while True:
        if _is_up(await _hugo_service_state()):
            await asyncio.sleep(_POLL_INTERVAL_S)
            continue
        try:
            woke = await _listen_while_hugo_down(config)
        except Exception:
            logger.exception("listener cycle failed; retrying shortly")
            await asyncio.sleep(_POLL_INTERVAL_S * 2)
            continue
        if woke:
            logger.info("starting hugo")
            await asyncio.to_thread(
                subprocess.run,
                ["systemctl", "--user", "start", "--no-block", "hugo.service"],
                check=True,
            )
            # Give systemd time to flip the unit into "activating" so the
            # next poll gates correctly.
            await asyncio.sleep(_POLL_INTERVAL_S)


def main() -> None:
    configure_logging(load_config().log_level)
    asyncio.run(run())


if __name__ == "__main__":
    main()
