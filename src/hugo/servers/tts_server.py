"""WebSocket streaming TTS server.

Runs as its own subprocess (see ADR 0002), same pattern as stt_server.py.

Wire protocol (one connection = one orchestrator, one utterance at a time):
  client -> server: {"type": "speak", "text": ...} starts synthesis.
  client -> server: {"type": "cancel"} aborts the utterance currently
                     streaming — required for true barge-in (ADR 0003): the
                     orchestrator must be able to cut HUGO off mid-sentence.
  server -> client: binary frames are raw mono PCM16 audio chunks, sample
                     rate determined by the Synthesizer implementation
                     (Qwen3-TTS outputs 24kHz — see qwen_tts_synthesizer.py).
  server -> client: {"type": "done"} once an utterance finishes normally, or
  server -> client: {"type": "cancelled"} if it was cut short.

The Synthesizer protocol keeps the real Qwen3-TTS model out of this module,
so the server loop, streaming, and cancellation logic are unit-testable
without GPU hardware.
"""

import argparse
import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncGenerator, Callable
from typing import Protocol

import websockets
from websockets.asyncio.server import ServerConnection

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8002


class Synthesizer(Protocol):
    def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        """Yields raw PCM16 audio chunks for `text`. Implementations should
        treat generator close (aclose(), triggered on cancellation) as a
        signal to stop generating further chunks promptly."""
        ...


async def handle_connection(ws: ServerConnection, synthesizer: Synthesizer) -> None:
    cancel_event = asyncio.Event()
    speak_task: asyncio.Task[None] | None = None

    async for message in ws:
        if not isinstance(message, str):
            continue  # audio only flows server -> client
        request = json.loads(message)
        kind = request.get("type")

        if kind == "speak":
            if speak_task is not None and not speak_task.done():
                speak_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await speak_task
            cancel_event = asyncio.Event()
            speak_task = asyncio.create_task(_speak(ws, synthesizer, request["text"], cancel_event))
        elif kind == "cancel":
            cancel_event.set()
        else:
            logger.warning("tts_server: unrecognized message: %r", request)

    if speak_task is not None and not speak_task.done():
        speak_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await speak_task


async def _speak(
    ws: ServerConnection, synthesizer: Synthesizer, text: str, cancel_event: asyncio.Event
) -> None:
    gen = synthesizer.synthesize(text)
    try:
        async for chunk in gen:
            if cancel_event.is_set():
                break
            await ws.send(chunk)
        else:
            await ws.send(json.dumps({"type": "done"}))
            return
        await ws.send(json.dumps({"type": "cancelled"}))
    finally:
        await gen.aclose()


async def serve(
    synthesizer: Synthesizer,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    on_ready: Callable[[int], None] | None = None,
) -> None:
    async def handler(ws: ServerConnection) -> None:
        await handle_connection(ws, synthesizer)

    async with websockets.serve(handler, host, port) as server:
        if on_ready is not None:
            bound_port = next(iter(server.sockets)).getsockname()[1]
            on_ready(bound_port)
        await asyncio.Future()  # run until cancelled


def _create_default_synthesizer() -> Synthesizer:
    from hugo.servers.qwen_tts_synthesizer import QwenTtsSynthesizer

    return QwenTtsSynthesizer()


def main(make_synthesizer: Callable[[], Synthesizer] = _create_default_synthesizer) -> None:
    parser = argparse.ArgumentParser(description="HUGO TTS server")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    synthesizer = make_synthesizer()
    asyncio.run(serve(synthesizer, args.host, args.port))


if __name__ == "__main__":
    main()
