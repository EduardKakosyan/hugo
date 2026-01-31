"""WebSocket endpoint – streams transcripts, responses, and status to the frontend."""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.bridge.openclaw import openclaw_client
from src.vision import set_active_provider
from src.voice.pipeline import voice_pipeline

logger = logging.getLogger("hugo.api.ws")

router = APIRouter(tags=["websocket"])

# Connected clients
_clients: set[WebSocket] = set()


async def broadcast(msg_type: str, data: dict | str) -> None:
    """Broadcast a message to all connected WebSocket clients."""
    payload = data if isinstance(data, str) else json.dumps(data)
    message = json.dumps({"type": msg_type, "data": payload})
    disconnected: list[WebSocket] = []
    for ws in _clients:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        _clients.discard(ws)


async def _broadcast_delta(req_id: str, delta: str) -> None:
    """Called by OpenClaw client when a streaming delta arrives."""
    await broadcast("chat:delta", {"reqId": req_id, "delta": delta})


async def _broadcast_done(req_id: str, full_text: str) -> None:
    """Called by OpenClaw client when the response is complete."""
    await broadcast("chat:done", {"reqId": req_id, "text": full_text})


def _register_callbacks() -> None:
    """Wire OpenClaw streaming callbacks to frontend broadcast."""
    openclaw_client.on_delta = _broadcast_delta
    openclaw_client.on_done = _broadcast_done


# Register callbacks on import
_register_callbacks()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    _clients.add(ws)
    logger.info("WebSocket client connected (%d total)", len(_clients))
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            msg_type = msg.get("type")

            if msg_type == "ping":
                await ws.send_text(json.dumps({"type": "pong", "data": ""}))

            elif msg_type == "chat":
                # Frontend sends a chat message — forward to OpenClaw with streaming
                text = msg.get("data", "")
                if not text:
                    continue
                try:
                    req_id = await openclaw_client.send_message_streaming(text)
                    await ws.send_text(
                        json.dumps({"type": "chat:start", "data": json.dumps({"reqId": req_id})})
                    )
                except Exception as e:
                    logger.error("Failed to send chat to OpenClaw: %s", e)
                    await ws.send_text(
                        json.dumps({"type": "chat:error", "data": json.dumps({"error": str(e)})})
                    )

            elif msg_type == "voice:start":
                try:
                    await voice_pipeline.start()
                    await broadcast("voice:status", {"active": True})
                except Exception as e:
                    logger.error("Failed to start voice pipeline: %s", e)
                    await ws.send_text(
                        json.dumps({
                            "type": "voice:error",
                            "data": json.dumps({"error": str(e)}),
                        })
                    )

            elif msg_type == "voice:stop":
                await voice_pipeline.stop()
                await broadcast("voice:status", {"active": False})

            elif msg_type == "session:reset":
                openclaw_client.reset_session()
                await broadcast("session:reset", {})

            elif msg_type == "vision:set-provider":
                provider_name = msg.get("data", "")
                try:
                    set_active_provider(provider_name)
                    await broadcast("vision:provider", {"provider": provider_name})
                except ValueError as e:
                    await ws.send_text(
                        json.dumps({
                            "type": "vision:error",
                            "data": json.dumps({"error": str(e)}),
                        })
                    )

    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        pass
    finally:
        _clients.discard(ws)
        logger.info("WebSocket client disconnected (%d remaining)", len(_clients))
