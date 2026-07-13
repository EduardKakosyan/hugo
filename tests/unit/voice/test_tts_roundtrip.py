"""End-to-end wire-protocol test: real serve() + real TtsClient over a real
localhost WebSocket, with a fake (non-GPU) synthesizer standing in for
Qwen3-TTS. Covers the barge-in cancellation contract from ADR 0003."""

import asyncio
from collections.abc import AsyncGenerator

import pytest

from hugo.servers.tts_server import Synthesizer, serve
from hugo.voice.tts import TtsClient


class FakeSynthesizer:
    def __init__(self, num_chunks: int = 5, chunk_delay: float = 0.01) -> None:
        self.closed = False
        self.chunks_yielded = 0
        self._num_chunks = num_chunks
        self._chunk_delay = chunk_delay

    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        try:
            for i in range(self._num_chunks):
                await asyncio.sleep(self._chunk_delay)
                self.chunks_yielded += 1
                yield f"chunk{i}".encode()
        finally:
            self.closed = True


@pytest.fixture
async def running_server() -> tuple[FakeSynthesizer, str]:
    synthesizer = FakeSynthesizer()
    port_holder: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    server_task = asyncio.create_task(
        serve(synthesizer, host="127.0.0.1", port=0, on_ready=lambda p: port_holder.set_result(p))
    )
    port = await asyncio.wait_for(port_holder, timeout=5)

    try:
        yield synthesizer, f"ws://127.0.0.1:{port}"
    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass


def test_synthesizer_protocol_is_satisfied_by_fake() -> None:
    synthesizer: Synthesizer = FakeSynthesizer()
    assert synthesizer is not None


async def test_full_utterance_streams_all_chunks(
    running_server: tuple[FakeSynthesizer, str],
) -> None:
    synthesizer, url = running_server

    async with TtsClient(url) as client:
        received = [chunk async for chunk in client.speak("hello")]

    assert received == [f"chunk{i}".encode() for i in range(5)]
    assert synthesizer.closed


async def test_cancel_mid_stream_stops_playback_and_closes_generator(
    running_server: tuple[FakeSynthesizer, str],
) -> None:
    synthesizer, url = running_server

    async with TtsClient(url) as client:
        received = []
        async for chunk in client.speak("a long sentence HUGO is speaking"):
            received.append(chunk)
            if len(received) == 1:
                await client.cancel()

    # Barge-in must cut playback well before the full utterance streams.
    assert len(received) < 5
    assert received[0] == b"chunk0"
    # The generator must be told to stop, not left running in the background
    # burning GPU cycles for audio nobody will hear.
    assert synthesizer.closed
    assert synthesizer.chunks_yielded < 5


async def test_second_utterance_on_same_connection_works_after_a_full_one(
    running_server: tuple[FakeSynthesizer, str],
) -> None:
    _synthesizer, url = running_server

    async with TtsClient(url) as client:
        first = [chunk async for chunk in client.speak("first")]
        second = [chunk async for chunk in client.speak("second")]

    assert first == second == [f"chunk{i}".encode() for i in range(5)]
