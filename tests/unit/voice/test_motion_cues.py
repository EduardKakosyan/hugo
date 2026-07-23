"""The voice loop -> motion layer seam (VEN-57): asserts the sequence of
motion cues emitted across conversation lifecycles, against the same
scripted fakes as test_loop.py. The cues ARE the external contract the
MotionManager consumes, so order is everything."""

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

from hugo.robot.motion_io import MotionCue
from hugo.voice.loop import VoiceLoop


def _build_loop(
    cues: list[MotionCue],
    stt: FakeSttSession | None = None,
    thinker: FakeThinker | None = None,
    follow_up_window_s: float = 0.2,
) -> tuple[VoiceLoop, FakeRobotAudioIO]:
    robot = FakeRobotAudioIO()
    loop = VoiceLoop(
        robot=robot,
        wake_word=FakeWakeWordListener(),
        vad=FakeSpeechDetector(),
        stt=stt or FakeSttSession(),
        tts=FakeTtsSession(),
        thinker=thinker or FakeThinker(),
        no_speech_timeout_s=1.0,
        follow_up_window_s=follow_up_window_s,
        max_utterance_s=1.0,
        on_motion_cue=cues.append,
    )
    return loop, robot


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


async def test_full_conversation_emits_the_cue_arc_in_order() -> None:
    cues: list[MotionCue] = []
    loop, robot = _build_loop(cues)
    task = asyncio.create_task(loop.run())
    try:
        robot.push_frame(WAKE_MARKER)
        await _wait_until(lambda: loop.state == "LISTENING")
        robot.push_frame(SPEECH_START_MARKER)
        robot.push_frame(SPEECH_END_MARKER)
        await _wait_until(lambda: loop.state == "RESPONDING")
        # Reply plays out; the follow-up window then expires -> conversation
        # ends. The full arc: perk, freeze, think, talk, re-listen, settle.
        await _wait_until(lambda: "conversation_end" in cues)
    finally:
        await _run_cancelled(task)

    assert cues == [
        "wake",
        "user_speech_start",
        "thinking",
        "speaking",
        "listening",
        "conversation_end",
    ]


async def test_stop_phrase_skips_the_speaking_cue() -> None:
    cues: list[MotionCue] = []
    loop, robot = _build_loop(cues, stt=FakeSttSession(final_text="stop"))
    task = asyncio.create_task(loop.run())
    try:
        robot.push_frame(WAKE_MARKER)
        await _wait_until(lambda: loop.state == "LISTENING")
        robot.push_frame(SPEECH_START_MARKER)
        robot.push_frame(SPEECH_END_MARKER)
        await _wait_until(lambda: "conversation_end" in cues)
    finally:
        await _run_cancelled(task)

    # "stop" never reaches the thinker, so HUGO never speaks: the thinking
    # cue resolves straight into the conversation-end settle.
    assert cues == ["wake", "user_speech_start", "thinking", "conversation_end"]


async def test_barge_in_emits_a_fresh_wake_cue() -> None:
    cues: list[MotionCue] = []
    # A many-utterance slow thinker keeps HUGO talking long enough to
    # interrupt deterministically after its first audio.
    loop, robot = _build_loop(
        cues, thinker=FakeThinker(utterances=["one", "two", "three"], delay_before_each=0.05)
    )
    task = asyncio.create_task(loop.run())
    try:
        robot.push_frame(WAKE_MARKER)
        await _wait_until(lambda: loop.state == "LISTENING")
        robot.push_frame(SPEECH_START_MARKER)
        robot.push_frame(SPEECH_END_MARKER)
        await _wait_until(lambda: "speaking" in cues)

        robot.push_frame(WAKE_MARKER)
        await _wait_until(lambda: cues.count("wake") == 2)
    finally:
        await _run_cancelled(task)

    # The barge-in is a fresh wake (perk), not a follow-up "listening".
    assert cues == ["wake", "user_speech_start", "thinking", "speaking", "wake"]


async def test_no_cue_callback_is_fine() -> None:
    # The seam is optional: a loop without a motion layer runs unchanged.
    robot = FakeRobotAudioIO()
    loop = VoiceLoop(
        robot=robot,
        wake_word=FakeWakeWordListener(),
        vad=FakeSpeechDetector(),
        stt=FakeSttSession(),
        tts=FakeTtsSession(),
        thinker=FakeThinker(),
        no_speech_timeout_s=1.0,
        follow_up_window_s=0.2,
    )
    task = asyncio.create_task(loop.run())
    try:
        robot.push_frame(WAKE_MARKER)
        await _wait_until(lambda: loop.state == "LISTENING")
        robot.push_frame(SPEECH_START_MARKER)
        robot.push_frame(SPEECH_END_MARKER)
        await _wait_until(lambda: loop.state == "RESPONDING")
        await _wait_until(lambda: loop.state == "IDLE")
    finally:
        await _run_cancelled(task)
