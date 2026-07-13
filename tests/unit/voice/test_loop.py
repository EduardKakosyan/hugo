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
    assert robot.played_chunks == [b"a", b"b", b"c", b"d", b"e"]
    assert not tts.cancelled


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
