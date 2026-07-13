import asyncio

from hugo.voice.turn import Turn


async def test_cancel_all_cancels_running_tasks() -> None:
    turn = Turn()
    started = asyncio.Event()

    async def never_ends() -> None:
        started.set()
        await asyncio.sleep(999)

    task = turn.spawn(never_ends())
    await started.wait()

    await turn.cancel_all()

    assert task.cancelled()


async def test_cancel_all_is_safe_when_tasks_already_finished() -> None:
    turn = Turn()
    task = turn.spawn(asyncio.sleep(0))
    await task

    await turn.cancel_all()  # must not raise

    assert task.done()
    assert not task.cancelled()


async def test_cancel_all_clears_task_list() -> None:
    turn = Turn()
    turn.spawn(asyncio.sleep(0))
    turn.spawn(asyncio.sleep(999))

    await turn.cancel_all()

    assert turn._tasks == []
