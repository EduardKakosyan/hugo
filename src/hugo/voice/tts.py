"""Async WebSocket client for the TTS subprocess (see servers/tts_server.py).

One connection per utterance: speak() dials, streams, and hangs up. A single
long-lived connection was tried first and is unsound with barge-in: the loop
cancels the playback task mid-`async for`, so the server's terminal
{"done"/"cancelled"} message is left unread in the shared connection's queue,
and the NEXT utterance's speak() consumes it as its own terminator — the
robot goes silent after one chunk. The server then kills the connection
(keepalive timeout, nobody reading), and with no reconnect every later
utterance died on the dead socket until full restart. Observed live on dgx1
2026-07-22, twice (11:39 and 14:06 sessions). A fresh connection per
utterance makes stale frames impossible and recovery automatic.
"""

import contextlib
import json
from collections.abc import AsyncIterator

import websockets
from websockets.asyncio.client import ClientConnection


class TtsClient:
    def __init__(self, url: str) -> None:
        self._url = url
        self._active_ws: ClientConnection | None = None

    async def connect(self) -> None:
        """Fail-fast reachability probe at startup; speak() dials its own
        connection per utterance."""
        ws = await websockets.connect(self._url)
        await ws.close()

    async def close(self) -> None:
        ws = self._active_ws
        self._active_ws = None
        if ws is not None:
            await ws.close()

    async def speak(self, text: str) -> AsyncIterator[bytes]:
        """Sends a speak request and yields audio chunks until the server
        reports the utterance done or cancelled. To interrupt playback
        mid-stream (barge-in), call cancel() from a concurrent task while
        iterating this — see docs/adr/0003. Closing the connection on exit
        (including generator close, the barge-in path) tells the server to
        stop synthesizing."""
        ws = await websockets.connect(self._url)
        self._active_ws = ws
        try:
            await ws.send(json.dumps({"type": "speak", "text": text}))
            async for message in ws:
                if isinstance(message, bytes):
                    yield message
                    continue
                payload = json.loads(message)
                if payload.get("type") in ("done", "cancelled"):
                    return
        finally:
            self._active_ws = None
            await ws.close()

    async def cancel(self) -> None:
        ws = self._active_ws
        if ws is None:
            return
        # The utterance may have finished (or died) since the caller decided
        # to barge in — a cancel that lost that race is a no-op, not an error.
        with contextlib.suppress(websockets.exceptions.ConnectionClosed):
            await ws.send(json.dumps({"type": "cancel"}))

    async def __aenter__(self) -> "TtsClient":
        await self.connect()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()
