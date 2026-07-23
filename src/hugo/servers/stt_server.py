"""WebSocket streaming STT server.

Runs as its own subprocess (see ADR 0002) so the STT model's memory is
released by killing the process rather than relying on in-process cleanup.

Wire protocol (one connection = one orchestrator, one utterance at a time):
  client -> server: binary frames are raw 16kHz mono PCM16 audio chunks.
  client -> server: {"type": "end"} text frame signals end of utterance.
  server -> client: {"type": "partial", "text": ...} as transcription progresses.
  server -> client: {"type": "final", "text": ...} once finalized, after which
                     the server resets and is ready for the next utterance.

The Transcriber protocol keeps the real NeMo/Parakeet model out of this
module entirely, so the server loop and wire protocol are unit-testable
without GPU hardware or the (Linux/CUDA-only) `nemo_toolkit` dependency.
"""

import argparse
import asyncio
import json
import logging
from collections.abc import Callable
from typing import Protocol

import websockets
from websockets.asyncio.server import ServerConnection

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8001


class Transcriber(Protocol):
    async def feed(self, pcm_chunk: bytes) -> str | None:
        """Feed a raw PCM16 chunk. Returns an updated partial transcript, or
        None if there's nothing new to report yet."""
        ...

    async def finalize(self) -> str:
        """End the current utterance and return its final transcript."""
        ...

    def reset(self) -> None:
        """Clear any per-utterance state, ready for the next utterance."""
        ...


async def handle_connection(ws: ServerConnection, transcriber: Transcriber) -> None:
    transcriber.reset()
    async for message in ws:
        if isinstance(message, bytes):
            partial = await transcriber.feed(message)
            if partial is not None:
                await ws.send(json.dumps({"type": "partial", "text": partial}))
        else:
            _handle_control_message(message)
            final_text = await transcriber.finalize()
            await ws.send(json.dumps({"type": "final", "text": final_text}))
            transcriber.reset()


def _handle_control_message(raw: str) -> None:
    control = json.loads(raw)
    if control.get("type") != "end":
        logger.warning("stt_server: unrecognized control message: %r", control)


async def serve(
    transcriber: Transcriber,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    on_ready: Callable[[int], None] | None = None,
) -> None:
    """Serve forever. `on_ready` (if given) is called with the actual bound
    port once listening — pass port=0 plus on_ready in tests to avoid
    hardcoded-port collisions."""

    async def handler(ws: ServerConnection) -> None:
        await handle_connection(ws, transcriber)

    async with websockets.serve(handler, host, port) as server:
        if on_ready is not None:
            bound_port = next(iter(server.sockets)).getsockname()[1]
            on_ready(bound_port)
        await asyncio.Future()  # run until cancelled


def _create_default_transcriber() -> Transcriber:
    from hugo.servers.parakeet_transcriber import ParakeetTranscriber

    return ParakeetTranscriber()


def main(make_transcriber: Callable[[], Transcriber] = _create_default_transcriber) -> None:
    parser = argparse.ArgumentParser(description="HUGO STT server")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    transcriber = make_transcriber()
    asyncio.run(_warmup_then_serve(transcriber, args.host, args.port))


async def _warmup_then_serve(transcriber: Transcriber, host: str, port: int) -> None:
    # One throwaway transcription before binding the socket, mirroring the
    # TTS server: the first real inference pays cold CUDA costs that landed
    # on the first live turn (2.59s to transcribe vs 0.09s warm — measured
    # on dgx1, 2026-07-23). The orchestrator's health check only passes
    # once bound, so warmup time is covered by the stt health_check_timeout.
    logger.info("stt_server: warming up transcriber...")
    await transcriber.feed(b"\x00" * 32_000)  # 1s of silence at 16kHz
    await transcriber.finalize()
    transcriber.reset()
    logger.info("stt_server: warmup complete")
    await serve(transcriber, host, port)


if __name__ == "__main__":
    main()
