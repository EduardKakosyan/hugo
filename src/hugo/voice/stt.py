"""Async WebSocket client for the STT subprocess (see servers/stt_server.py)."""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

import websockets
from websockets.asyncio.client import ClientConnection


@dataclass(frozen=True)
class Transcript:
    kind: Literal["partial", "final"]
    text: str


class SttClient:
    def __init__(self, url: str) -> None:
        self._url = url
        self._ws: ClientConnection | None = None

    async def connect(self) -> None:
        self._ws = await websockets.connect(self._url)

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def send_audio(self, pcm_chunk: bytes) -> None:
        await self._connection().send(pcm_chunk)

    async def end_utterance(self) -> None:
        await self._connection().send(json.dumps({"type": "end"}))

    async def transcripts(self) -> AsyncIterator[Transcript]:
        """Yields partial transcripts as they arrive, then a final transcript,
        one per call to end_utterance()."""
        async for message in self._connection():
            if not isinstance(message, str):
                continue
            payload = json.loads(message)
            kind = payload.get("type")
            if kind in ("partial", "final"):
                yield Transcript(kind=kind, text=payload["text"])
                if kind == "final":
                    return

    def _connection(self) -> ClientConnection:
        if self._ws is None:
            raise RuntimeError("SttClient.connect() must be awaited before use")
        return self._ws

    async def __aenter__(self) -> "SttClient":
        await self.connect()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()
