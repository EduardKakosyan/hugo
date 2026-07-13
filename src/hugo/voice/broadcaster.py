"""Fans one async source of audio frames out to multiple independent
consumers — e.g. during SPEAKING, both the barge-in VAD check and a
buffer-ahead-for-the-next-STT-session need to see every mic frame."""

import asyncio
import contextlib
from collections.abc import AsyncIterator


class FrameBroadcaster:
    def __init__(self, source: AsyncIterator[bytes]) -> None:
        self._source = source
        self._queues: list[asyncio.Queue[bytes | None]] = []
        self._pump_task: asyncio.Task[None] | None = None

    def subscribe(self) -> AsyncIterator[bytes]:
        """Returns a fresh stream of frames from this point forward. Must be
        called before start() sees the frames you want — a subscriber only
        receives frames pumped after it subscribes."""
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._queues.append(queue)
        return self._consume(queue)

    async def _consume(self, queue: asyncio.Queue[bytes | None]) -> AsyncIterator[bytes]:
        try:
            while True:
                frame = await queue.get()
                if frame is None:
                    return
                yield frame
        finally:
            # Runs on normal exhaustion, on the queue's own None sentinel,
            # and on cancellation (e.g. a consumer task being cancelled
            # mid-iteration) — without this, every subscribe() call leaks a
            # queue the pump keeps feeding forever, since nothing else ever
            # removes it from self._queues.
            if queue in self._queues:
                self._queues.remove(queue)

    def start(self) -> None:
        self._pump_task = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        try:
            async for frame in self._source:
                for queue in self._queues:
                    queue.put_nowait(frame)
        finally:
            for queue in self._queues:
                queue.put_nowait(None)

    async def stop(self) -> None:
        if self._pump_task is not None:
            self._pump_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pump_task
