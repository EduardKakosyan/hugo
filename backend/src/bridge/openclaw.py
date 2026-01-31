"""OpenClaw WebSocket client – sends transcripts, receives Claude responses."""

import asyncio
import json
import logging
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from src.config import settings

logger = logging.getLogger("hugo.bridge.openclaw")

# Callback type for streaming deltas to the frontend
DeltaCallback = Callable[[str, str], Coroutine[Any, Any, None]]  # (req_id, delta) -> None
DoneCallback = Callable[[str, str], Coroutine[Any, Any, None]]  # (req_id, full_text) -> None


class OpenClawClient:
    def __init__(self) -> None:
        self._ws: ClientConnection | None = None
        self._connected = False
        self._pending: dict[str, asyncio.Future[dict]] = {}
        self._response_chunks: dict[str, list[str]] = {}
        self._run_to_req: dict[str, str] = {}
        self._listener_task: asyncio.Task | None = None
        self.on_delta: DeltaCallback | None = None
        self.on_done: DoneCallback | None = None

    async def connect(self) -> None:
        """Connect to the OpenClaw gateway via WebSocket."""
        try:
            self._ws = await websockets.connect(settings.openclaw_url)

            # Wait for connect.challenge
            raw = await self._ws.recv()
            challenge = json.loads(raw)
            if challenge.get("event") != "connect.challenge":
                logger.warning("Expected connect.challenge, got: %s", challenge.get("event"))

            # Send connect request
            req_id = str(uuid.uuid4())
            connect_req = {
                "type": "req",
                "id": req_id,
                "method": "connect",
                "params": {
                    "minProtocol": 3,
                    "maxProtocol": 3,
                    "role": "operator",
                    "scopes": ["operator.read", "operator.write"],
                    "client": {
                        "id": "cli",
                        "version": "0.1.0",
                        "platform": "darwin",
                        "mode": "cli",
                    },
                    "auth": {"token": settings.openclaw_token},
                    "locale": "en-US",
                },
            }
            await self._ws.send(json.dumps(connect_req))

            # Wait for hello response
            raw = await self._ws.recv()
            hello = json.loads(raw)
            if hello.get("ok"):
                self._connected = True
                logger.info("Connected to OpenClaw gateway")
                self._listener_task = asyncio.create_task(self._listen())
            else:
                logger.error("OpenClaw handshake failed: %s", hello)
        except Exception as e:
            logger.error("OpenClaw WebSocket connection failed: %s", e)

    async def _listen(self) -> None:
        """Background listener for WebSocket messages."""
        assert self._ws is not None
        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                msg_type = msg.get("type")

                if msg_type == "res":
                    req_id = msg.get("id")
                    payload = msg.get("payload", {})

                    # Map runId back to request
                    run_id = payload.get("runId")
                    if run_id and req_id:
                        self._run_to_req[run_id] = req_id

                elif msg_type == "event":
                    event = msg.get("event")
                    payload = msg.get("payload", {})
                    run_id = payload.get("runId", "")
                    req_id = self._run_to_req.get(run_id)

                    if event == "agent" and payload.get("stream") == "assistant":
                        delta = payload.get("data", {}).get("delta", "")
                        if delta and req_id:
                            self._response_chunks.setdefault(req_id, []).append(delta)
                            if self.on_delta:
                                await self.on_delta(req_id, delta)

                    elif event == "chat":
                        state = payload.get("state")
                        if state == "final" and req_id:
                            chunks = self._response_chunks.pop(req_id, [])
                            text = "".join(chunks)
                            if self.on_done:
                                await self.on_done(req_id, text)
                            if req_id in self._pending:
                                fut = self._pending.pop(req_id)
                                if not fut.done():
                                    fut.set_result({"status": "ok", "text": text})

        except websockets.ConnectionClosed:
            logger.warning("OpenClaw WebSocket connection closed")
            self._connected = False
        except Exception as e:
            logger.error("OpenClaw listener error: %s", e)
            self._connected = False

    async def send_message(self, message: str) -> str | None:
        """Send a user message to OpenClaw and return the assistant response text."""
        if not self._connected or self._ws is None:
            await self.connect()
            if not self._connected:
                return None

        req_id = str(uuid.uuid4())
        request = {
            "type": "req",
            "id": req_id,
            "method": "chat.send",
            "params": {
                "sessionKey": "hugo",
                "message": message,
                "idempotencyKey": str(uuid.uuid4()),
            },
        }

        loop = asyncio.get_event_loop()
        fut: asyncio.Future[dict] = loop.create_future()
        self._pending[req_id] = fut

        try:
            await self._ws.send(json.dumps(request))
            result = await asyncio.wait_for(fut, timeout=60.0)
            return result.get("text") or None
        except asyncio.TimeoutError:
            logger.error("OpenClaw response timed out")
            self._pending.pop(req_id, None)
            self._response_chunks.pop(req_id, None)
            return None
        except Exception as e:
            logger.error("OpenClaw send_message failed: %s", e)
            self._pending.pop(req_id, None)
            self._response_chunks.pop(req_id, None)
            return None

    async def send_message_streaming(self, message: str) -> str:
        """Send a message and return the req_id for tracking. Deltas arrive via on_delta callback."""
        if not self._connected or self._ws is None:
            await self.connect()
            if not self._connected:
                raise ConnectionError("Not connected to OpenClaw")

        req_id = str(uuid.uuid4())
        request = {
            "type": "req",
            "id": req_id,
            "method": "chat.send",
            "params": {
                "sessionKey": "hugo",
                "message": message,
                "idempotencyKey": str(uuid.uuid4()),
            },
        }

        await self._ws.send(json.dumps(request))
        return req_id

    async def close(self) -> None:
        if self._listener_task is not None:
            self._listener_task.cancel()
            self._listener_task = None
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        self._connected = False


openclaw_client = OpenClawClient()
