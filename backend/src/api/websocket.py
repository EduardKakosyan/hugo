"""WebSocket handlers for telemetry, video, audio, and chat streaming."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.vision.camera import CameraStream

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Simulator video relay ────────────────────────────────────────────────────
# The daemon connects as a WS client to /video_stream and pushes JPEG frames.
# Frontend clients connect to /ws/sim_video to receive those frames.

_sim_frame: bytes | None = None
_sim_subscribers: set[WebSocket] = set()


@router.websocket("/video_stream")
async def sim_video_ingest(websocket: WebSocket) -> None:
    """Receive JPEG frames from the reachy-mini daemon."""
    global _sim_frame  # noqa: PLW0603
    await websocket.accept()
    logger.info("Simulator video ingest connected")

    try:
        while True:
            data = await websocket.receive_bytes()
            _sim_frame = data
            # Broadcast to all subscribed frontend clients
            dead: list[WebSocket] = []
            for sub in _sim_subscribers:
                try:
                    await sub.send_bytes(data)
                except Exception:
                    dead.append(sub)
            for d in dead:
                _sim_subscribers.discard(d)
    except WebSocketDisconnect:
        logger.info("Simulator video ingest disconnected")
    except Exception as e:
        logger.error("Simulator video ingest error: %s", e)


@router.websocket("/audio_stream")
async def sim_audio_ingest(websocket: WebSocket) -> None:
    """Accept audio stream from the reachy-mini daemon (currently unused)."""
    await websocket.accept()
    logger.info("Simulator audio ingest connected")
    try:
        while True:
            await websocket.receive_bytes()
    except WebSocketDisconnect:
        logger.info("Simulator audio ingest disconnected")
    except Exception as e:
        logger.error("Simulator audio ingest error: %s", e)


@router.websocket("/robot")
async def sim_robot_control(websocket: WebSocket) -> None:
    """Accept robot control channel from the reachy-mini daemon (currently unused)."""
    await websocket.accept()
    logger.info("Simulator robot control channel connected")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("Simulator robot control channel disconnected")
    except Exception as e:
        logger.error("Simulator robot control channel error: %s", e)


@router.websocket("/ws/sim_video")
async def sim_video_feed(websocket: WebSocket) -> None:
    """Stream simulator video frames to frontend clients."""
    await websocket.accept()
    _sim_subscribers.add(websocket)
    logger.info("Simulator video subscriber connected (%d total)", len(_sim_subscribers))

    try:
        # Keep the connection alive; frames are pushed via broadcast above
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("Simulator video subscriber error: %s", e)
    finally:
        _sim_subscribers.discard(websocket)
        logger.info("Simulator video subscriber disconnected (%d remaining)", len(_sim_subscribers))


@router.websocket("/ws/telemetry")
async def telemetry_ws(websocket: WebSocket) -> None:
    """Stream robot state at 20Hz."""
    await websocket.accept()
    robot = websocket.app.state.robot
    interval = 1.0 / robot._config.state_frequency_hz

    try:
        while True:
            state = await robot.get_state()
            await websocket.send_json(state)
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        logger.info("Telemetry WebSocket disconnected")
    except Exception as e:
        logger.error("Telemetry WebSocket error: %s", e)


@router.websocket("/ws/video")
async def video_ws(websocket: WebSocket) -> None:
    """Stream camera frames as JPEG bytes."""
    await websocket.accept()
    robot = websocket.app.state.robot

    if not robot.media_available:
        logger.info("Video WebSocket: media not available (simulation mode), closing")
        await websocket.close(code=1000, reason="Media not available in simulation mode")
        return

    camera = CameraStream(robot)

    try:
        async for frame_data in camera.stream_frames():
            await websocket.send_bytes(frame_data)
    except WebSocketDisconnect:
        camera.stop()
        logger.info("Video WebSocket disconnected")
    except Exception as e:
        camera.stop()
        logger.error("Video WebSocket error: %s", e)


@router.websocket("/ws/audio")
async def audio_ws(websocket: WebSocket) -> None:
    """Bidirectional audio streaming."""
    await websocket.accept()
    robot = websocket.app.state.robot

    try:
        while True:
            # Receive audio from client
            data = await websocket.receive_bytes()

            # Push audio to robot speaker
            await robot.push_audio(data)

            # Get audio from robot mic and send back
            mic_audio = await robot.get_audio()
            if mic_audio:
                await websocket.send_bytes(mic_audio)
    except WebSocketDisconnect:
        logger.info("Audio WebSocket disconnected")
    except Exception as e:
        logger.error("Audio WebSocket error: %s", e)


@router.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket) -> None:
    """Streaming chat responses via WebSocket."""
    await websocket.accept()
    agent = websocket.app.state.agent

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            user_text = message.get("message", "")

            if not user_text:
                continue

            # Stream response tokens
            async for token in agent.stream_chat(user_text):
                await websocket.send_json({"type": "token", "content": token})

            await websocket.send_json({"type": "done"})
    except WebSocketDisconnect:
        logger.info("Chat WebSocket disconnected")
    except Exception as e:
        logger.error("Chat WebSocket error: %s", e, exc_info=True)
        try:
            await websocket.send_json({"type": "error", "content": str(e)})
        except Exception as send_err:
            logger.debug(
                "Failed to send error to chat WebSocket client: %s", send_err
            )
