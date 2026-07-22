"""End-to-end wire-protocol test: real serve() + real TtsClient over a real
localhost WebSocket, with a fake (non-GPU) synthesizer standing in for
Qwen3-TTS. Covers the barge-in cancellation contract from ADR 0003."""

import asyncio
import contextlib
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


async def test_second_utterance_on_same_client_works_after_a_full_one(
    running_server: tuple[FakeSynthesizer, str],
) -> None:
    _synthesizer, url = running_server

    async with TtsClient(url) as client:
        first = [chunk async for chunk in client.speak("first")]
        second = [chunk async for chunk in client.speak("second")]

    assert first == second == [f"chunk{i}".encode() for i in range(5)]


async def test_second_utterance_streams_fully_when_first_consumer_was_task_cancelled(
    running_server: tuple[FakeSynthesizer, str],
) -> None:
    """Regression for the dgx1 2026-07-22 silent-robot bug: the voice loop's
    barge-in path task-cancels the coroutine iterating speak() (never reading
    the server's terminal message), then starts a fresh utterance. The stale
    terminator must not leak into — and instantly end — the next utterance,
    and the abandoned socket must not poison the client."""
    synthesizer, url = running_server

    async with TtsClient(url) as client:
        got_first_chunk = asyncio.Event()

        async def consume_until_parked() -> None:
            async for _ in client.speak("first"):
                got_first_chunk.set()
                await asyncio.sleep(3600)  # playback task parked; cancelled below

        playback_task = asyncio.create_task(consume_until_parked())
        await asyncio.wait_for(got_first_chunk.wait(), timeout=5)
        await client.cancel()
        playback_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await playback_task

        # In the real loop, LISTENING + THINKING sit between barge-in and the
        # next utterance — long enough for the server to acknowledge the
        # cancel with its terminal message. Without this gap the bug hides:
        # the next "speak" reaches the server first and task-cancels the old
        # utterance before any stale terminator is ever sent.
        await asyncio.sleep(0.1)

        second = [chunk async for chunk in client.speak("second")]

    assert second == [f"chunk{i}".encode() for i in range(5)]


async def test_abandoning_speak_mid_stream_stops_synthesis(
    running_server: tuple[FakeSynthesizer, str],
) -> None:
    """Task-cancelling the speak() consumer (barge-in) must reach the server
    and stop the synthesizer — not leave it generating for a dead socket."""
    synthesizer, url = running_server
    # Lengthen the utterance so abandonment happens well before completion.
    synthesizer._num_chunks = 100

    async with TtsClient(url) as client:
        got_first_chunk = asyncio.Event()

        async def consume_until_parked() -> None:
            async for _ in client.speak("a very long reply"):
                got_first_chunk.set()
                await asyncio.sleep(3600)

        playback_task = asyncio.create_task(consume_until_parked())
        await asyncio.wait_for(got_first_chunk.wait(), timeout=5)
        playback_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await playback_task

        for _ in range(100):
            if synthesizer.closed:
                break
            await asyncio.sleep(0.02)

    assert synthesizer.closed
    assert synthesizer.chunks_yielded < 100


def test_split_sentences_splits_on_terminal_punctuation() -> None:
    from hugo.servers.tts_server import split_sentences

    assert split_sentences("Hello there. How are you? Fine!") == [
        "Hello there.",
        "How are you?",
        "Fine!",
    ]


def test_split_sentences_passes_unpunctuated_text_through_whole() -> None:
    from hugo.servers.tts_server import split_sentences

    assert split_sentences("no punctuation at all here") == [
        "no punctuation at all here"
    ]


def test_split_sentences_drops_empty_segments() -> None:
    from hugo.servers.tts_server import split_sentences

    assert split_sentences("  One.   Two.  ") == ["One.", "Two."]
    assert split_sentences("") == []
