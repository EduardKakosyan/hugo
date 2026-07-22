"""The highest-value test suite in the project: proves the voice loop's
state transitions and — most importantly — barge-in cancellation, entirely
against fakes. No hardware, no real model inference, fully deterministic."""

import asyncio
from collections.abc import Callable

from fakes import (
    SPEECH_END_MARKER,
    SPEECH_START_MARKER,
    WAKE_MARKER,
    FakeRobotAudioIO,
    FakeSpeechDetector,
    FakeSttSession,
    FakeThinker,
    FakeTtsSession,
    FakeWakeWordListener,
)

from hugo.voice.chime import wake_chime_pcm16
from hugo.voice.loop import VoiceLoop


def _build_loop(
    tts: FakeTtsSession | None = None,
) -> tuple[VoiceLoop, FakeRobotAudioIO, FakeTtsSession, FakeSttSession, FakeThinker]:
    robot = FakeRobotAudioIO()
    tts = tts or FakeTtsSession()
    stt = FakeSttSession()
    thinker = FakeThinker()
    loop = VoiceLoop(
        robot=robot,
        wake_word=FakeWakeWordListener(),
        vad=FakeSpeechDetector(),
        stt=stt,
        tts=tts,
        thinker=thinker,
    )
    return loop, robot, tts, stt, thinker


async def _wait_until(predicate: Callable[[], bool], timeout_s: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("timed out waiting for condition")
        await asyncio.sleep(0.005)


async def test_starts_idle() -> None:
    loop, _robot, _tts, _stt, _thinker = _build_loop()
    assert loop.state == "IDLE"


async def test_full_happy_path_returns_to_idle() -> None:
    loop, robot, tts, stt, thinker = _build_loop()
    task = asyncio.create_task(loop.run())
    try:
        await asyncio.sleep(0.01)
        assert loop.state == "IDLE"

        robot.push_frame(WAKE_MARKER)
        await _wait_until(lambda: loop.state == "LISTENING")

        robot.push_frame(b"speech-audio-1")
        robot.push_frame(SPEECH_END_MARKER)
        await _wait_until(lambda: loop.state == "SPEAKING")

        # Fully-scripted, short TTS stream with no barge-in — let it finish.
        await _wait_until(lambda: loop.state == "IDLE")
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert stt.sent_audio == [b"speech-audio-1", SPEECH_END_MARKER]
    assert stt.ended
    assert thinker.asked == "hello hugo"
    assert tts.spoken_text == "hello there"
    chime = wake_chime_pcm16(robot.output_sample_rate_hz)
    assert robot.played_chunks == [chime, b"a", b"b", b"c", b"d", b"e"]
    assert not tts.cancelled
    # Pipeline discipline: start_playing exactly once at startup, and no
    # stop_playing while the loop runs — reachy_mini's shared pipeline
    # makes a mid-loop stop kill capture (see loop.py's run()).
    assert robot.start_playing_calls == 1
    assert robot.stop_playing_calls == 0
    assert robot.clear_playback_calls == 0


async def test_barge_in_cancels_tts_and_returns_to_listening() -> None:
    # A longer TTS stream so there's a real window to interrupt it in.
    slow_chunks = [b"a", b"b", b"c", b"d", b"e", b"f", b"g", b"h"]
    slow_tts = FakeTtsSession(chunks=slow_chunks, chunk_delay=0.05)
    loop, robot, tts, _stt, _thinker = _build_loop(tts=slow_tts)

    task = asyncio.create_task(loop.run())
    try:
        robot.push_frame(WAKE_MARKER)
        await _wait_until(lambda: loop.state == "LISTENING")

        robot.push_frame(SPEECH_END_MARKER)
        await _wait_until(lambda: loop.state == "SPEAKING")

        # Let a couple of chunks play, then barge in mid-utterance.
        await asyncio.sleep(0.08)
        assert 0 < len(robot.played_chunks) < len(slow_chunks)
        robot.push_frame(SPEECH_START_MARKER)

        await _wait_until(lambda: loop.state == "LISTENING")
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert tts.cancelled
    # Playback must have been cut short, not run to completion.
    assert len(robot.played_chunks) < len(slow_chunks)
    # Interruption flushes queued audio without touching pipeline state.
    assert robot.clear_playback_calls == 1
    assert robot.stop_playing_calls == 0


async def test_stuck_listening_state_does_not_crash_or_advance() -> None:
    # If VAD never reports speech_end, LISTENING should just keep listening
    # rather than crash or spuriously advance to THINKING.
    class NeverEndsSpeechDetector(FakeSpeechDetector):
        def feed(self, pcm16_chunk: bytes) -> None:  # type: ignore[override]
            return None

    robot = FakeRobotAudioIO()
    thinker = FakeThinker()
    loop = VoiceLoop(
        robot=robot,
        wake_word=FakeWakeWordListener(),
        vad=NeverEndsSpeechDetector(),
        stt=FakeSttSession(),
        tts=FakeTtsSession(),
        thinker=thinker,
    )

    task = asyncio.create_task(loop.run())
    try:
        robot.push_frame(WAKE_MARKER)
        await _wait_until(lambda: loop.state == "LISTENING")

        robot.push_frame(b"never-triggers-end")
        await asyncio.sleep(0.05)

        assert loop.state == "LISTENING"
        assert thinker.asked is None
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def test_thinker_failure_does_not_crash_the_loop() -> None:
    # A real 400 from vLLM (tool-calling not enabled server-side) once
    # propagated all the way up through here uncaught, silently killing
    # run()'s asyncio.Task -- the wake word listener never ran again for
    # the rest of the process. This proves that class of failure now
    # degrades to a spoken apology instead.
    class RaisingThinker:
        async def think(self, user_text: str) -> str:
            raise RuntimeError("boom")

    robot = FakeRobotAudioIO()
    tts = FakeTtsSession()
    loop = VoiceLoop(
        robot=robot,
        wake_word=FakeWakeWordListener(),
        vad=FakeSpeechDetector(),
        stt=FakeSttSession(),
        tts=tts,
        thinker=RaisingThinker(),  # type: ignore[arg-type]
    )

    task = asyncio.create_task(loop.run())
    try:
        robot.push_frame(WAKE_MARKER)
        await _wait_until(lambda: loop.state == "LISTENING")

        robot.push_frame(SPEECH_END_MARKER)
        await _wait_until(lambda: loop.state == "SPEAKING")
        await _wait_until(lambda: loop.state == "IDLE")

        assert not task.done()
        assert tts.spoken_text is not None
        assert "sorry" in tts.spoken_text.lower()
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def test_failure_in_a_non_thinking_state_also_recovers_instead_of_crashing() -> None:
    # A real dgx1 failure surfaced in IDLE (the new wake chime playback),
    # not THINKING -- proving the recovery is general (run()'s own
    # catch-all), not just something bolted onto _run_thinking specifically.
    class FlakyPlaybackRobot(FakeRobotAudioIO):
        def __init__(self) -> None:
            super().__init__()
            self.play_audio_calls = 0

        async def play_audio(self, pcm16_chunk: bytes) -> None:
            self.play_audio_calls += 1
            if self.play_audio_calls == 1:
                raise RuntimeError("boom")
            await super().play_audio(pcm16_chunk)

    robot = FlakyPlaybackRobot()
    loop = VoiceLoop(
        robot=robot,
        wake_word=FakeWakeWordListener(),
        vad=FakeSpeechDetector(),
        stt=FakeSttSession(),
        tts=FakeTtsSession(),
        thinker=FakeThinker(),
    )

    task = asyncio.create_task(loop.run())
    try:
        robot.push_frame(WAKE_MARKER)
        await _wait_until(lambda: robot.play_audio_calls == 1)
        await _wait_until(lambda: loop.state == "IDLE")
        assert not task.done()

        # A second wake word must still work -- proves real recovery, not
        # just "survived one crash while already broken forever after".
        robot.push_frame(WAKE_MARKER)
        await _wait_until(lambda: loop.state == "LISTENING")
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
