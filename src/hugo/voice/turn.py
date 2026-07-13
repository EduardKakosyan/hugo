"""One exchange's cancellable task set — barge-in cancels everything
spawned during the current turn together, in one place."""

import asyncio
import contextlib
from collections.abc import Coroutine
from typing import Any


class Turn:
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task[Any]] = []

    def spawn(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro)
        self._tasks.append(task)
        return task

    async def cancel_all(self) -> None:
        for task in self._tasks:
            if not task.done():
                task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
