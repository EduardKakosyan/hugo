"""`hugo dev <mode>` — isolated hardware verification commands, each
de-risking one stage of the voice pipeline before the full loop needs to
work together. `echo`/`bargein` need the robot physically connected;
`listen`/`speak` additionally need the relevant model server already
running (e.g. `.venv-stt/bin/python -m hugo.servers.stt_server`) — these
commands are deliberately narrow, not another orchestrator.

NOT YET run against real hardware — no Reachy Mini was connected to dgx1
while this was written. See robot/reachy_client.py's own caveat.
"""

import asyncio
import time

import typer

from hugo.config import load_config
from hugo.logging_setup import configure_logging
from hugo.robot.reachy_client import ReachyMiniClient
from hugo.voice.stt import SttClient
from hugo.voice.tts import TtsClient
from hugo.voice.vad import SpeechActivityDetector
from hugo.voice.wake_word import WakeWordDetector

dev_app = typer.Typer(add_completion=False, help="Isolated hardware verification commands.")


@dev_app.command("echo")
def echo(seconds: float = 5.0) -> None:
    """Record N seconds from the mic, then play it back — the cheapest
    possible mic/speaker sanity check."""
    configure_logging(load_config().log_level)
    asyncio.run(_echo(seconds))


async def _echo(seconds: float) -> None:
    robot = ReachyMiniClient()
    typer.echo(
        f"connected: input {robot.input_sample_rate_hz}Hz, output {robot.output_sample_rate_hz}Hz"
    )

    frames: list[bytes] = []
    await robot.start_recording()
    typer.echo(f"recording {seconds}s...")

    async def collect() -> None:
        async for frame in robot.read_mic_frames():
            frames.append(frame)

    collect_task = asyncio.create_task(collect())
    await asyncio.sleep(seconds)
    collect_task.cancel()
    await robot.stop_recording()

    typer.echo(f"captured {len(frames)} frames, {sum(len(f) for f in frames)} bytes")
    typer.echo("playing back...")
    await robot.start_playing()
    for frame in frames:
        await robot.play_audio(frame)
    await robot.stop_playing()
    robot.close()
    typer.echo("done")


@dev_app.command("listen")
def listen() -> None:
    """Wake-word + VAD + STT only — prints transcripts. No LLM, no TTS, no
    robot movement. Assumes the STT server is already running."""
    configure_logging(load_config().log_level)
    asyncio.run(_listen())


async def _listen() -> None:
    config = load_config()
    robot = ReachyMiniClient()
    wake_word = WakeWordDetector(model_name=config.wake_word)
    vad = SpeechActivityDetector()
    stt = SttClient(config.stt_ws_url)
    await stt.connect()

    await robot.start_recording()
    typer.echo(f"listening for wake word '{config.wake_word}'...")
    async for frame in robot.read_mic_frames():
        if wake_word.feed(frame):
            break
    typer.echo("wake word detected — say something, then pause.")

    async def feed_until_speech_ends() -> None:
        async for frame in robot.read_mic_frames():
            await stt.send_audio(frame)
            if vad.feed(frame) == "speech_end":
                await stt.end_utterance()
                return

    feed_task = asyncio.create_task(feed_until_speech_ends())
    async for t in stt.transcripts():
        typer.echo(f"  {t.kind}: {t.text}")
    await feed_task

    await robot.stop_recording()
    await stt.close()
    robot.close()


@dev_app.command("speak")
def speak(text: str) -> None:
    """TTS + playback only. Assumes the TTS server is already running."""
    configure_logging(load_config().log_level)
    asyncio.run(_speak(text))


async def _speak(text: str) -> None:
    config = load_config()
    robot = ReachyMiniClient()
    tts = TtsClient(config.tts_ws_url)
    await tts.connect()

    await robot.start_playing()
    async for chunk in tts.speak(text):
        await robot.play_audio(chunk)
    await robot.stop_playing()

    await tts.close()
    robot.close()


@dev_app.command("bargein")
def bargein(
    text: str = (
        "This is a long test utterance, spoken slowly, to leave you plenty of "
        "time to interrupt it by speaking before it finishes on its own."
    ),
) -> None:
    """Speaks a long utterance while watching the mic for real barge-in,
    printing detection latency. Assumes the TTS server is already running."""
    configure_logging(load_config().log_level)
    asyncio.run(_bargein(text))


async def _bargein(text: str) -> None:
    config = load_config()
    robot = ReachyMiniClient()
    tts = TtsClient(config.tts_ws_url)
    await tts.connect()
    vad = SpeechActivityDetector()

    start_time: float | None = None
    detected_at: float | None = None

    async def play() -> None:
        nonlocal start_time
        await robot.start_playing()
        start_time = time.monotonic()
        try:
            async for chunk in tts.speak(text):
                await robot.play_audio(chunk)
        finally:
            await robot.stop_playing()

    async def watch() -> None:
        nonlocal detected_at
        await robot.start_recording()
        try:
            async for frame in robot.read_mic_frames():
                if vad.feed(frame) == "speech_start":
                    detected_at = time.monotonic()
                    return
        finally:
            await robot.stop_recording()

    typer.echo("speaking — interrupt by talking whenever you like...")
    play_task = asyncio.create_task(play())
    watch_task = asyncio.create_task(watch())
    done, _pending = await asyncio.wait(
        {play_task, watch_task}, return_when=asyncio.FIRST_COMPLETED
    )

    if watch_task in done and detected_at is not None and start_time is not None:
        await tts.cancel()
        typer.echo(f"barge-in detected after {detected_at - start_time:.3f}s")
    else:
        typer.echo("utterance finished with no barge-in detected")

    for task in (play_task, watch_task):
        if not task.done():
            task.cancel()
    await tts.close()
    robot.close()
