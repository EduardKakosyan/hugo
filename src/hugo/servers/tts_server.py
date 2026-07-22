"""WebSocket streaming TTS server.

Runs as its own subprocess (see ADR 0002), same pattern as stt_server.py.

Wire protocol (one connection = one utterance — the client dials per
utterance and hangs up when done or barged-in; connection close is the
server's signal to stop synthesizing. See voice/tts.py for why a shared
long-lived connection is unsound):
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
import re
from collections.abc import AsyncGenerator, Callable
from typing import Protocol

import websockets
from websockets.asyncio.server import ServerConnection

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8002


_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?;:])\s+")


def split_sentences(text: str) -> list[str]:
    """Splits text at sentence-ish boundaries for incremental synthesis.

    Qwen3-TTS can only synthesize a full utterance in one blocking call
    (see qwen_tts_synthesizer.py), so first-audio latency scales with the
    length of the text handed to it. Synthesizing sentence-by-sentence
    caps that latency at one sentence — measured live on dgx1 2026-07-22,
    a full multi-sentence answer took minutes before its first sample,
    which reads as HUGO simply not responding. Unpunctuated text passes
    through whole; no worse than before.
    """
    return [s for s in (p.strip() for p in _SENTENCE_BOUNDARY.split(text)) if s]


class Synthesizer(Protocol):
    def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        """Yields raw PCM16 audio chunks for `text`. Implementations should
        treat generator close (aclose(), triggered on cancellation) as a
        signal to stop generating further chunks promptly."""
        ...


async def handle_connection(ws: ServerConnection, synthesizer: Synthesizer) -> None:
    cancel_event = asyncio.Event()
    speak_task: asyncio.Task[None] | None = None

    try:
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
                speak_task = asyncio.create_task(
                    _speak(ws, synthesizer, request["text"], cancel_event)
                )
            elif kind == "cancel":
                cancel_event.set()
            else:
                logger.warning("tts_server: unrecognized message: %r", request)
    finally:
        # Must run on abnormal connection death too, not just clean close:
        # the client hangs up mid-stream as its normal barge-in path (see
        # voice/tts.py), which lands here via ConnectionClosed rather than
        # loop exit. Stop synthesis, and retrieve the task's exception so a
        # send() that lost the race to the closed socket doesn't surface as
        # "Task exception was never retrieved".
        if speak_task is not None:
            speak_task.cancel()
            with contextlib.suppress(
                asyncio.CancelledError, websockets.exceptions.ConnectionClosed
            ):
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
    asyncio.run(_warmup_then_serve(synthesizer, args.host, args.port))


async def _warmup_then_serve(synthesizer: Synthesizer, host: str, port: int) -> None:
    # One throwaway synthesis before binding the socket: the first real
    # generate pays CUDA/JIT warmup costs (observed live on dgx1 as extra
    # seconds of silence on HUGO's first-ever reply). The orchestrator's
    # health check only passes once we're bound, so warmup time is covered
    # by the tts health_check_timeout — keep those in sync.
    logger.info("tts_server: warming up synthesizer...")
    async for _ in synthesizer.synthesize("Ready."):
        pass
    logger.info("tts_server: warmup complete")
    await serve(synthesizer, host, port)


if __name__ == "__main__":
    main()
