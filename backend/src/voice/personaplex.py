"""NVIDIA PersonaPlex speech-to-speech engine integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class PersonaPlexEngine:
    """Full-duplex speech-to-speech via NVIDIA PersonaPlex-7B-v1 (Moshi server)."""

    def __init__(self, host: str = "localhost", port: int = 8998) -> None:
        self._host = host
        self._port = port
        self._ws: Any = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        """Connect to the PersonaPlex Moshi server WebSocket."""
        try:
            import websockets

            uri = f"ws://{self._host}:{self._port}/ws"
            self._ws = await websockets.connect(uri)
            self._connected = True
            logger.info("Connected to PersonaPlex at %s:%d", self._host, self._port)
            return True
        except Exception as e:
            logger.warning("Failed to connect to PersonaPlex: %s", e)
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from PersonaPlex."""
        if self._ws is not None:
            await self._ws.close()
            self._connected = False

    async def speech_to_text(self, audio_data: bytes) -> str:
        """Send audio to PersonaPlex and get transcription.

        Note: PersonaPlex is speech-to-speech, so this extracts the text
        representation from the model's response.
        """
        if not self._connected or self._ws is None:
            raise RuntimeError("PersonaPlex not connected")

        await self._ws.send(audio_data)
        response = await asyncio.wait_for(self._ws.recv(), timeout=10.0)

        if isinstance(response, str):
            return response
        # Binary response — extract text if available
        return response.decode("utf-8", errors="replace")

    async def text_to_speech(self, text: str) -> bytes:
        """Send text to PersonaPlex and get speech audio back.

        PersonaPlex can accept text conditioning for generating speech output.
        """
        if not self._connected or self._ws is None:
            raise RuntimeError("PersonaPlex not connected")

        await self._ws.send(text.encode("utf-8"))
        response = await asyncio.wait_for(self._ws.recv(), timeout=10.0)

        if isinstance(response, bytes):
            return response
        return response.encode("utf-8")

    async def stream_bidirectional(
        self,
        input_audio: asyncio.Queue[bytes],
        output_audio: asyncio.Queue[bytes],
    ) -> None:
        """Stream audio bidirectionally with PersonaPlex for full-duplex conversation."""
        if not self._connected or self._ws is None:
            raise RuntimeError("PersonaPlex not connected")

        async def send_loop() -> None:
            while True:
                chunk = await input_audio.get()
                if chunk == b"":
                    break
                await self._ws.send(chunk)

        async def recv_loop() -> None:
            async for message in self._ws:
                if isinstance(message, bytes):
                    await output_audio.put(message)

        await asyncio.gather(send_loop(), recv_loop())
