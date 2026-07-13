"""Async WebSocket client for the TTS subprocess (see servers/tts_server.py)."""

import json
from collections.abc import AsyncIterator

import websockets
from websockets.asyncio.client import ClientConnection


class TtsClient:
    def __init__(self, url: str) -> None:
        self._url = url
        self._ws: ClientConnection | None = None

    async def connect(self) -> None:
        self._ws = await websockets.connect(self._url)

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def speak(self, text: str) -> AsyncIterator[bytes]:
        """Sends a speak request and yields audio chunks until the server
        reports the utterance done or cancelled. To interrupt playback
        mid-stream (barge-in), call cancel() from a concurrent task while
        iterating this — see docs/adr/0003."""
        await self._connection().send(json.dumps({"type": "speak", "text": text}))
        async for message in self._connection():
            if isinstance(message, bytes):
                yield message
                continue
            payload = json.loads(message)
            if payload.get("type") in ("done", "cancelled"):
                return

    async def cancel(self) -> None:
        await self._connection().send(json.dumps({"type": "cancel"}))

    def _connection(self) -> ClientConnection:
        if self._ws is None:
            raise RuntimeError("TtsClient.connect() must be awaited before use")
        return self._ws

    async def __aenter__(self) -> "TtsClient":
        await self.connect()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()
