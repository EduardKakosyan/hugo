"""Direct tests for FrameBroadcaster, including the leak/poisoning bug
found while building VoiceLoop: cancelling one subscriber must not affect
the pump or any other subscriber, and must remove its own queue rather
than leaking it forever."""

import asyncio
from collections.abc import AsyncIterator

from hugo.voice.broadcaster import FrameBroadcaster


async def _source(frames: list[bytes], hold_open: asyncio.Event) -> AsyncIterator[bytes]:
    for frame in frames:
        yield frame
    await hold_open.wait()  # keep the source "open" so we can test late-subscribe behavior


async def test_single_subscriber_receives_all_frames() -> None:
    hold_open = asyncio.Event()
    broadcaster = FrameBroadcaster(_source([b"a", b"b", b"c"], hold_open))
    broadcaster.start()

    received = []
    sub = broadcaster.subscribe()
    for _ in range(3):
        received.append(await anext(sub))

    assert received == [b"a", b"b", b"c"]

    hold_open.set()
    await broadcaster.stop()


async def test_multiple_subscribers_each_receive_every_frame() -> None:
    hold_open = asyncio.Event()
    broadcaster = FrameBroadcaster(_source([b"x", b"y"], hold_open))
    sub_a = broadcaster.subscribe()
    sub_b = broadcaster.subscribe()
    broadcaster.start()

    a_frames = [await anext(sub_a), await anext(sub_a)]
    b_frames = [await anext(sub_b), await anext(sub_b)]

    assert a_frames == [b"x", b"y"]
    assert b_frames == [b"x", b"y"]

    hold_open.set()
    await broadcaster.stop()


async def test_cancelling_one_subscriber_does_not_affect_another() -> None:
    hold_open = asyncio.Event()
    broadcaster = FrameBroadcaster(_source([b"x", b"y", b"z"], hold_open))
    sub_a = broadcaster.subscribe()
    sub_b = broadcaster.subscribe()
    broadcaster.start()

    assert await anext(sub_a) == b"x"
    assert await anext(sub_b) == b"x"

    task_a = asyncio.create_task(anext(sub_a))
    await asyncio.sleep(0.01)
    task_a.cancel()
    try:
        await task_a
    except asyncio.CancelledError:
        pass

    # sub_b must be completely unaffected by sub_a's cancellation.
    assert await anext(sub_b) == b"y"
    assert await anext(sub_b) == b"z"

    hold_open.set()
    await broadcaster.stop()


async def test_cancelled_subscriber_is_removed_not_leaked() -> None:
    # No frames ever arrive, so anext(sub) is genuinely suspended awaiting
    # an empty queue when cancelled — not racing a frame that's already
    # been delivered (queue.get() on non-empty data returns immediately,
    # which would complete the task before cancel() has any effect).
    hold_open = asyncio.Event()
    broadcaster = FrameBroadcaster(_source([], hold_open))
    sub = broadcaster.subscribe()
    broadcaster.start()

    assert len(broadcaster._queues) == 1
    task = asyncio.create_task(anext(sub))
    await asyncio.sleep(0.01)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert broadcaster._queues == []

    hold_open.set()
    await broadcaster.stop()


async def test_stop_cancels_the_pump() -> None:
    never_ends = asyncio.Event()
    broadcaster = FrameBroadcaster(_source([], never_ends))
    broadcaster.start()

    await broadcaster.stop()  # must return promptly, not hang

    assert broadcaster._pump_task is not None
    assert broadcaster._pump_task.cancelled()
