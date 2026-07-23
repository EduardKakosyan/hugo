"""The highest-value test suite in the project: proves the voice loop's
state transitions, conversation lifecycle (VEN-56), and interruption
cancellation entirely against fakes. No hardware, no real model inference,
fully deterministic (timing windows are shrunk to tens of milliseconds)."""

import asyncio
from collections.abc import AsyncIterator, Callable

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

from hugo.voice.chime import conversation_end_chime_pcm16, wake_chime_pcm16
from hugo.voice.loop import PROGRESS_NUDGE, SLEEP_CONFIRMATION, VoiceLoop, normalize_command


def _build_loop(
    tts: FakeTtsSession | None = None,
    stt: FakeSttSession | None = None,
    thinker: FakeThinker | None = None,
    on_sleep: Callable[[], None] | None = None,
    no_speech_timeout_s: float = 1.0,
    follow_up_window_s: float = 0.3,
    max_utterance_s: float = 1.0,
    progress_update_after_s: float = 5.0,
) -> tuple[VoiceLoop, FakeRobotAudioIO, FakeTtsSession, FakeSttSession, FakeThinker]:
    robot = FakeRobotAudioIO()
    tts = tts or FakeTtsSession()
    stt = stt or FakeSttSession()
    thinker = thinker or FakeThinker()
    loop = VoiceLoop(
        robot=robot,
        wake_word=FakeWakeWordListener(),
        vad=FakeSpeechDetector(),
        stt=stt,
        tts=tts,
        thinker=thinker,
        no_speech_timeout_s=no_speech_timeout_s,
        follow_up_window_s=follow_up_window_s,
        max_utterance_s=max_utterance_s,
        progress_update_after_s=progress_update_after_s,
        on_sleep=on_sleep,
    )
    return loop, robot, tts, stt, thinker


async def _wait_until(predicate: Callable[[], bool], timeout_s: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("timed out waiting for condition")
        await asyncio.sleep(0.005)


async def _run_cancelled(task: asyncio.Task[None]) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def test_normalize_command_strips_stt_punctuation() -> None:
    assert normalize_command("Stop.") == "stop"
    assert normalize_command("  That's  ALL! ") == "that's all"
    assert normalize_command("Go to sleep?") == "go to sleep"


async def test_starts_idle() -> None:
    loop, _robot, _tts, _stt, _thinker = _build_loop()
    assert loop.state == "IDLE"


async def test_full_happy_path_returns_to_idle_after_follow_up_expires() -> None:
    loop, robot, tts, stt, thinker = _build_loop()
    task = asyncio.create_task(loop.run())
    try:
        await asyncio.sleep(0.01)
        assert loop.state == "IDLE"

        robot.push_frame(WAKE_MARKER)
        await _wait_until(lambda: loop.state == "LISTENING")

        robot.push_frame(SPEECH_START_MARKER)
        robot.push_frame(b"speech-audio-1")
        robot.push_frame(SPEECH_END_MARKER)
        await _wait_until(lambda: loop.state == "RESPONDING")

        # Reply plays out, then the follow-up window expires with no
        # speech — the conversation ends with the end chime, back to IDLE.
        await _wait_until(lambda: loop.state == "IDLE")
    finally:
        await _run_cancelled(task)

    # Pre-roll: mic audio is buffered until VAD confirms speech, then
    # flushed — so STT saw the onset frame, the speech, and the end frame,
    # and nothing before speech started.
    assert stt.sent_audio == [SPEECH_START_MARKER, b"speech-audio-1", SPEECH_END_MARKER]
    assert stt.ended
    assert thinker.asked == ["hello hugo"]
    assert tts.spoken_texts == ["hello there"]
    wake_chime = wake_chime_pcm16(robot.output_sample_rate_hz)
    end_chime = conversation_end_chime_pcm16(robot.output_sample_rate_hz)
    assert robot.played_chunks == [wake_chime, b"a", b"b", b"c", b"d", b"e", end_chime]
    assert not tts.cancelled
    # Pipeline discipline: start_playing exactly once at startup, and no
    # stop_playing while the loop runs — reachy_mini's shared pipeline
    # makes a mid-loop stop kill capture (see loop.py's run()).
    assert robot.start_playing_calls == 1
    assert robot.stop_playing_calls == 0
    assert robot.clear_playback_calls == 0


async def test_follow_up_turn_needs_no_wake_word() -> None:
    loop, robot, _tts, _stt, thinker = _build_loop(follow_up_window_s=1.0)
    task = asyncio.create_task(loop.run())
    try:
        robot.push_frame(WAKE_MARKER)
        await _wait_until(lambda: loop.state == "LISTENING")
        robot.push_frame(SPEECH_START_MARKER)
        robot.push_frame(SPEECH_END_MARKER)
        await _wait_until(lambda: loop.state == "RESPONDING")
        await _wait_until(lambda: loop.state == "LISTENING")

        # Second turn: no wake word, just speech inside the follow-up window.
        robot.push_frame(SPEECH_START_MARKER)
        robot.push_frame(SPEECH_END_MARKER)
        await _wait_until(lambda: len(thinker.asked) == 2)
    finally:
        await _run_cancelled(task)

    assert thinker.asked == ["hello hugo", "hello hugo"]


async def test_no_speech_after_wake_times_out_to_idle() -> None:
    loop, robot, _tts, stt, thinker = _build_loop(no_speech_timeout_s=0.2)
    task = asyncio.create_task(loop.run())
    try:
        robot.push_frame(WAKE_MARKER)
        await _wait_until(lambda: loop.state == "LISTENING")
        # Say nothing. The window must expire back to IDLE — an accidental
        # wake can't leave the mic open indefinitely (VEN-56).
        await _wait_until(lambda: loop.state == "IDLE")
    finally:
        await _run_cancelled(task)

    assert thinker.asked == []
    assert stt.sent_audio == []  # nothing ever reached STT — no reset needed
    end_chime = conversation_end_chime_pcm16(robot.output_sample_rate_hz)
    assert robot.played_chunks[-1] == end_chime


async def test_utterance_cap_forces_end_of_utterance() -> None:
    # VAD reports speech starting but never ending (e.g. steady background
    # noise) — the cap must force the turn through rather than trap the
    # loop in LISTENING forever.
    loop, robot, _tts, stt, thinker = _build_loop(max_utterance_s=0.2)
    task = asyncio.create_task(loop.run())
    try:
        robot.push_frame(WAKE_MARKER)
        await _wait_until(lambda: loop.state == "LISTENING")
        robot.push_frame(SPEECH_START_MARKER)
        robot.push_frame(b"endless-noise")
        await _wait_until(lambda: loop.state == "RESPONDING")
    finally:
        await _run_cancelled(task)

    assert stt.ended
    assert thinker.asked == ["hello hugo"]


async def test_stop_phrase_ends_conversation_without_thinking() -> None:
    loop, robot, tts, _stt, thinker = _build_loop(stt=FakeSttSession(final_text="Stop."))
    task = asyncio.create_task(loop.run())
    try:
        robot.push_frame(WAKE_MARKER)
        await _wait_until(lambda: loop.state == "LISTENING")
        robot.push_frame(SPEECH_START_MARKER)
        robot.push_frame(SPEECH_END_MARKER)
        await _wait_until(lambda: loop.state == "IDLE")
    finally:
        await _run_cancelled(task)

    assert thinker.asked == []  # deterministic match, never LLM-interpreted
    assert tts.spoken_texts == []
    end_chime = conversation_end_chime_pcm16(robot.output_sample_rate_hz)
    assert robot.played_chunks[-1] == end_chime


async def test_empty_transcript_ends_conversation_without_thinking() -> None:
    loop, robot, _tts, _stt, thinker = _build_loop(stt=FakeSttSession(final_text="  "))
    task = asyncio.create_task(loop.run())
    try:
        robot.push_frame(WAKE_MARKER)
        await _wait_until(lambda: loop.state == "LISTENING")
        robot.push_frame(SPEECH_START_MARKER)
        robot.push_frame(SPEECH_END_MARKER)
        await _wait_until(lambda: loop.state == "IDLE")
    finally:
        await _run_cancelled(task)

    assert thinker.asked == []


async def test_sleep_phrase_confirms_then_shuts_the_loop_down() -> None:
    sleep_calls: list[bool] = []
    loop, robot, tts, _stt, thinker = _build_loop(
        stt=FakeSttSession(final_text="go to sleep"),
        on_sleep=lambda: sleep_calls.append(True),
    )
    task = asyncio.create_task(loop.run())
    try:
        robot.push_frame(WAKE_MARKER)
        await _wait_until(lambda: loop.state == "LISTENING")
        robot.push_frame(SPEECH_START_MARKER)
        robot.push_frame(SPEECH_END_MARKER)
        # run() exits on its own — sleep is a loop-terminating event, not a
        # state transition.
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        if not task.done():
            await _run_cancelled(task)

    assert sleep_calls == [True]
    assert tts.spoken_texts == [SLEEP_CONFIRMATION]
    assert thinker.asked == []
    assert robot.recording is False  # run()'s finally still cleaned up


async def test_wake_word_interrupts_playback_and_reopens_listening() -> None:
    # A longer TTS stream so there's a real window to interrupt it in.
    slow_chunks = [b"a", b"b", b"c", b"d", b"e", b"f", b"g", b"h"]
    slow_tts = FakeTtsSession(chunks=slow_chunks, chunk_delay=0.05)
    loop, robot, tts, _stt, _thinker = _build_loop(tts=slow_tts)

    task = asyncio.create_task(loop.run())
    try:
        robot.push_frame(WAKE_MARKER)
        await _wait_until(lambda: loop.state == "LISTENING")
        robot.push_frame(SPEECH_START_MARKER)
        robot.push_frame(SPEECH_END_MARKER)
        await _wait_until(lambda: loop.state == "RESPONDING")

        # Let a couple of chunks play, then interrupt with the wake word
        # (ADR 0003 as amended: arbitrary speech must NOT interrupt).
        await asyncio.sleep(0.08)
        tts_chunks_so_far = len(robot.played_chunks) - 1  # minus wake chime
        assert 0 < tts_chunks_so_far < len(slow_chunks)
        robot.push_frame(WAKE_MARKER)

        await _wait_until(lambda: loop.state == "LISTENING")
    finally:
        await _run_cancelled(task)

    assert tts.cancelled
    # Playback must have been cut short, not run to completion.
    assert len(robot.played_chunks) < len(slow_chunks) + 1
    # Interruption flushes queued audio without touching pipeline state.
    assert robot.clear_playback_calls == 1
    assert robot.stop_playing_calls == 0


async def test_arbitrary_speech_does_not_interrupt_playback() -> None:
    slow_tts = FakeTtsSession(chunks=[b"a", b"b", b"c", b"d"], chunk_delay=0.03)
    loop, robot, tts, _stt, _thinker = _build_loop(tts=slow_tts)

    task = asyncio.create_task(loop.run())
    try:
        robot.push_frame(WAKE_MARKER)
        await _wait_until(lambda: loop.state == "LISTENING")
        robot.push_frame(SPEECH_START_MARKER)
        robot.push_frame(SPEECH_END_MARKER)
        await _wait_until(lambda: loop.state == "RESPONDING")

        # VAD-visible speech mid-playback (e.g. HUGO's own voice — no AEC)
        # must not cut the reply.
        robot.push_frame(SPEECH_START_MARKER)
        await _wait_until(lambda: loop.state == "LISTENING")
    finally:
        await _run_cancelled(task)

    assert not tts.cancelled
    assert robot.clear_playback_calls == 0
    assert b"d" in robot.played_chunks  # reply played to completion


async def test_progress_nudge_speaks_while_the_thinker_is_slow() -> None:
    loop, robot, tts, _stt, _thinker = _build_loop(
        thinker=FakeThinker(utterances=["done now"], delay_before_each=0.5),
        progress_update_after_s=0.15,
    )
    task = asyncio.create_task(loop.run())
    try:
        robot.push_frame(WAKE_MARKER)
        await _wait_until(lambda: loop.state == "LISTENING")
        robot.push_frame(SPEECH_START_MARKER)
        robot.push_frame(SPEECH_END_MARKER)
        await _wait_until(lambda: "done now" in tts.spoken_texts)
    finally:
        await _run_cancelled(task)

    assert tts.spoken_texts[0] == PROGRESS_NUDGE  # silence never means "working"
    assert tts.spoken_texts[-1] == "done now"


async def test_thinker_failure_degrades_to_a_spoken_apology() -> None:
    # A real 400 from vLLM once propagated all the way up uncaught,
    # silently killing run()'s asyncio.Task. This proves a raising thinker
    # now degrades to a spoken apology and the loop keeps running.
    class RaisingThinker:
        async def think(self, user_text: str) -> AsyncIterator[str]:
            raise RuntimeError("boom")
            yield ""  # unreachable; makes this an async generator

    robot = FakeRobotAudioIO()
    tts = FakeTtsSession()
    loop = VoiceLoop(
        robot=robot,
        wake_word=FakeWakeWordListener(),
        vad=FakeSpeechDetector(),
        stt=FakeSttSession(),
        tts=tts,
        thinker=RaisingThinker(),
        follow_up_window_s=0.2,
    )

    task = asyncio.create_task(loop.run())
    try:
        robot.push_frame(WAKE_MARKER)
        await _wait_until(lambda: loop.state == "LISTENING")
        robot.push_frame(SPEECH_START_MARKER)
        robot.push_frame(SPEECH_END_MARKER)
        await _wait_until(lambda: loop.state == "IDLE")
        assert not task.done()
    finally:
        await _run_cancelled(task)

    assert any("sorry" in text.lower() for text in tts.spoken_texts)


async def test_failure_in_a_non_responding_state_also_recovers_instead_of_crashing() -> None:
    # A real dgx1 failure surfaced in IDLE (the wake chime playback), not
    # while thinking -- proving the recovery is general (run()'s own
    # catch-all), not just something bolted onto one state.
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
        await _run_cancelled(task)
