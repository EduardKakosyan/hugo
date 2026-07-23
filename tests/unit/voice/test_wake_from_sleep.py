"""The sleeping ear (wake_listener) and the startup announcement — the
wake-from-sleep UX arc: chime when heard, speak when actually ready."""

import asyncio

from fakes import (
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
from hugo.wake_listener import listen_until_wake


async def test_listener_ignores_noise_until_the_wake_word_then_chimes() -> None:
    robot = FakeRobotAudioIO()
    wake_word = FakeWakeWordListener()
    robot.push_frame(b"just-noise")
    robot.push_frame(b"more-noise")
    robot.push_frame(WAKE_MARKER)

    await asyncio.wait_for(listen_until_wake(robot, wake_word), timeout=2.0)

    assert robot.played_chunks == [wake_chime_pcm16(robot.output_sample_rate_hz)]
    assert wake_word.reset_count == 1


async def test_listener_stands_the_robot_up_when_the_wake_word_fires() -> None:
    robot = FakeRobotAudioIO()
    wake_word = FakeWakeWordListener()
    stand_ups = 0

    async def on_wake() -> None:
        nonlocal stand_ups
        stand_ups += 1

    robot.push_frame(b"just-noise")
    robot.push_frame(WAKE_MARKER)

    await asyncio.wait_for(listen_until_wake(robot, wake_word, on_wake=on_wake), timeout=2.0)

    # The physical ack lands with the chime — both must have completed by
    # the time the listener returns (the caller releases media right after).
    assert stand_ups == 1
    assert robot.played_chunks == [wake_chime_pcm16(robot.output_sample_rate_hz)]


async def test_startup_announcement_is_spoken_before_listening_begins() -> None:
    robot = FakeRobotAudioIO()
    tts = FakeTtsSession()
    loop = VoiceLoop(
        robot=robot,
        wake_word=FakeWakeWordListener(),
        vad=FakeSpeechDetector(),
        stt=FakeSttSession(),
        tts=tts,
        thinker=FakeThinker(),
        startup_announcement="I'm awake.",
    )

    task = asyncio.create_task(loop.run())
    try:
        deadline = asyncio.get_running_loop().time() + 2.0
        while not tts.spoken_texts:
            assert asyncio.get_running_loop().time() < deadline
            await asyncio.sleep(0.005)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert tts.spoken_texts == ["I'm awake."]
