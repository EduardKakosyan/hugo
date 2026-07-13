"""End-to-end wire-protocol test: real serve() + real SttClient over a real
localhost WebSocket, with a fake (non-GPU) transcriber standing in for
Parakeet TDT. No network/hardware dependency, safe for CI."""

import asyncio

import pytest

from hugo.servers.stt_server import Transcriber, serve
from hugo.voice.stt import SttClient


class FakeTranscriber:
    def __init__(self, partials: list[str], final: str) -> None:
        self._partials = list(partials)
        self._final = final
        self.fed_chunks: list[bytes] = []
        self.reset_count = 0

    async def feed(self, pcm_chunk: bytes) -> str | None:
        self.fed_chunks.append(pcm_chunk)
        return self._partials.pop(0) if self._partials else None

    async def finalize(self) -> str:
        return self._final

    def reset(self) -> None:
        self.reset_count += 1


@pytest.fixture
async def running_server() -> tuple[FakeTranscriber, str]:
    transcriber = FakeTranscriber(partials=["hel", "hello"], final="hello world")
    port_holder: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    server_task = asyncio.create_task(
        serve(transcriber, host="127.0.0.1", port=0, on_ready=lambda p: port_holder.set_result(p))
    )
    port = await asyncio.wait_for(port_holder, timeout=5)

    try:
        yield transcriber, f"ws://127.0.0.1:{port}"
    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass


async def test_full_utterance_round_trip(running_server: tuple[FakeTranscriber, str]) -> None:
    transcriber, url = running_server

    async with SttClient(url) as client:
        await client.send_audio(b"\x00\x01" * 100)
        await client.send_audio(b"\x00\x01" * 100)
        await client.end_utterance()

        received = [t async for t in client.transcripts()]

    assert received[0].kind == "partial"
    assert received[0].text == "hel"
    assert received[1].kind == "partial"
    assert received[1].text == "hello"
    assert received[2].kind == "final"
    assert received[2].text == "hello world"
    assert len(transcriber.fed_chunks) == 2
    # reset() once on connect, once after finalize.
    assert transcriber.reset_count == 2


async def test_second_utterance_on_same_connection_gets_fresh_state(
    running_server: tuple[FakeTranscriber, str],
) -> None:
    transcriber, url = running_server

    async with SttClient(url) as client:
        await client.send_audio(b"\x00\x01")
        await client.end_utterance()
        first = [t async for t in client.transcripts()]

        transcriber._partials = ["still"]
        transcriber._final = "still working"
        await client.send_audio(b"\x00\x01")
        await client.end_utterance()
        second = [t async for t in client.transcripts()]

    assert first[-1].text == "hello world"
    assert second[-1].text == "still working"


def test_transcriber_protocol_is_satisfied_by_fake() -> None:
    # Static-typing sanity check: FakeTranscriber must structurally satisfy
    # the Transcriber protocol used by the real server.
    transcriber: Transcriber = FakeTranscriber(partials=[], final="")
    assert transcriber is not None
