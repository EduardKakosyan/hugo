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
import wave
from pathlib import Path

import numpy as np
import typer

from hugo.agent.web_search import WebSearchTool
from hugo.config import load_config
from hugo.logging_setup import configure_logging
from hugo.robot.reachy_client import ReachyMiniClient, _downmix_to_mono, _float32_to_pcm16
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


@dev_app.command("dump-capture")
def dump_capture(seconds: float = 5.0, out_dir: str = ".") -> None:
    """Records N seconds via reachy_mini's own capture path and writes two
    WAV files for offline A/B comparison: the untouched multi-channel
    float32 samples exactly as the media backend returns them
    (capture_raw.wav), and HUGO's actual mono PCM16 conversion of that same
    audio (capture_hugo_mono.wav, via the real downmix in
    robot/reachy_client.py) — useful for re-verifying the capture path
    after any future change to that conversion."""
    configure_logging(load_config().log_level)
    asyncio.run(_dump_capture(seconds, Path(out_dir)))


async def _dump_capture(seconds: float, out_dir: Path) -> None:
    robot = ReachyMiniClient()
    typer.echo(
        f"connected: input {robot.input_sample_rate_hz}Hz, {robot.input_channels} channel(s)"
    )

    raw_chunks: list[np.ndarray] = []
    await robot.start_recording()
    typer.echo(f"recording {seconds}s from reachy_mini's raw capture path...")

    async def collect() -> None:
        async for sample in robot.read_mic_frames_raw():
            raw_chunks.append(sample)

    collect_task = asyncio.create_task(collect())
    await asyncio.sleep(seconds)
    collect_task.cancel()
    await robot.stop_recording()
    robot.close()

    if not raw_chunks:
        typer.echo("captured 0 samples — recording produced nothing.")
        raise typer.Exit(1)

    raw = np.concatenate(raw_chunks, axis=0)
    typer.echo(f"captured {raw.shape[0]} frames x {robot.input_channels} channel(s)")

    raw_path = out_dir / "capture_raw.wav"
    _write_pcm16_wav(
        raw_path,
        (np.clip(raw, -1.0, 1.0) * 32767).astype(np.int16).tobytes(),
        robot.input_sample_rate_hz,
        robot.input_channels,
    )
    typer.echo(f"wrote {raw_path} (untouched reachy_mini output, {robot.input_channels}ch)")

    mono_bytes = b"".join(_float32_to_pcm16(_downmix_to_mono(chunk)) for chunk in raw_chunks)
    mono_path = out_dir / "capture_hugo_mono.wav"
    _write_pcm16_wav(mono_path, mono_bytes, robot.input_sample_rate_hz, channels=1)
    typer.echo(f"wrote {mono_path} (HUGO's actual mono PCM16 conversion of the same audio)")


def _write_pcm16_wav(path: Path, pcm16_bytes: bytes, sample_rate_hz: int, channels: int) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate_hz)
        wav_file.writeframes(pcm16_bytes)


@dev_app.command("wake")
def wake(seconds: float = 15.0) -> None:
    """Wake word detection only -- prints every frame's size and live
    detection score as you speak. No VAD, no STT, no robot movement.
    Isolates the one stage that had never been verified against a real
    spoken wake phrase (see tests/unit/voice/test_wake_word.py's own
    docstring) from everything downstream."""
    configure_logging(load_config().log_level)
    asyncio.run(_wake(seconds))


async def _wake(seconds: float) -> None:
    config = load_config()
    robot = ReachyMiniClient()
    wake_word = WakeWordDetector(model_name=config.wake_word)

    await robot.start_recording()
    typer.echo(f"listening for '{config.wake_word}' for {seconds}s...")

    frame_count = 0
    detected_count = 0

    async def watch() -> None:
        nonlocal frame_count, detected_count
        async for frame in robot.read_mic_frames():
            frame_count += 1
            triggered = wake_word.feed(frame)
            if triggered:
                detected_count += 1
            typer.echo(
                f"  frame {frame_count}: {len(frame)} bytes, "
                f"score={wake_word.last_score:.3f}, detected={triggered}"
            )

    watch_task = asyncio.create_task(watch())
    await asyncio.sleep(seconds)
    watch_task.cancel()
    await robot.stop_recording()
    robot.close()
    typer.echo(f"done: {frame_count} frames, {detected_count} detection(s)")


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


@dev_app.command("search")
def search(query: str) -> None:
    """Runs the web search tool directly against Tavily -- no LLM, no voice
    loop. Verifies HUGO_TAVILY_API_KEY and the Tavily integration in
    isolation."""
    configure_logging(load_config().log_level)
    asyncio.run(_search(query))


async def _search(query: str) -> None:
    config = load_config()
    if not config.tavily_api_key:
        typer.echo("HUGO_TAVILY_API_KEY is not set.")
        raise typer.Exit(1)

    tool = WebSearchTool(config.tavily_api_key)
    result = await tool.search(query)
    typer.echo(result)


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
