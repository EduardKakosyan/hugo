"""Always-on minimal wake listener — HUGO's ear while it sleeps (VEN-56
follow-up: "hey jarvis" must wake it from a full sleep).

Runs as its own systemd user service (deploy/hugo-wake.service) whenever
the full stack is down. Footprint is deliberately tiny — the wake-word
model on CPU and the robot mic, no GPU, no model servers — so it doesn't
meaningfully dent the shared box's memory (ADR 0002's spirit holds: the
121GB pool stays free while HUGO sleeps).

On detection it plays the wake chime (the audible "heard you — waking
up"; the full model load takes minutes), releases the robot's media
pipeline so the starting orchestrator can claim it, and asks systemd to
start hugo. The units are mutually exclusive via Conflicts=, and
hugo.service's ExecStopPost restores this listener after every sleep or
crash — the ear is never left off.
"""

import asyncio
import logging
import subprocess

from hugo.config import load_config
from hugo.logging_setup import configure_logging
from hugo.robot.audio_io import RobotAudioIO
from hugo.voice.chime import wake_chime_pcm16
from hugo.voice.loop import WakeWordListener

logger = logging.getLogger(__name__)

# Lets the chime drain through the robot's playback queue before the
# media pipeline is released.
_CHIME_DRAIN_S = 0.6


async def listen_until_wake(robot: RobotAudioIO, wake_word: WakeWordListener) -> None:
    """Consumes mic frames until the wake word fires, then chimes."""
    wake_word.reset()
    async for frame in robot.read_mic_frames():
        if wake_word.feed(frame):
            logger.info("wake word heard while asleep")
            await robot.play_audio(wake_chime_pcm16(robot.output_sample_rate_hz))
            await asyncio.sleep(_CHIME_DRAIN_S)
            return


async def run() -> None:
    from hugo.robot.reachy_client import ReachyMiniClient
    from hugo.voice.wake_word import WakeWordDetector

    config = load_config()
    robot = ReachyMiniClient(playback_gain=config.playback_gain)
    wake_word = WakeWordDetector(model_name=config.wake_word)
    await robot.start_recording()
    await robot.start_playing()
    try:
        logger.info("asleep and listening — say '%s' to wake hugo", config.wake_word)
        await listen_until_wake(robot, wake_word)
    finally:
        # Release the mic/speaker BEFORE hugo starts: the orchestrator's
        # robot connect races this exit, and the media pipeline is
        # single-owner.
        await robot.stop_recording()
        robot.close()
    logger.info("starting hugo")
    await asyncio.to_thread(
        subprocess.run,
        ["systemctl", "--user", "start", "--no-block", "hugo.service"],
        check=True,
    )


def main() -> None:
    configure_logging(load_config().log_level)
    asyncio.run(run())


if __name__ == "__main__":
    main()
