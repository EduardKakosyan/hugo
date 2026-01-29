"""WebSocket handlers for telemetry, video, audio, and chat streaming."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.vision.camera import CameraStream

logger = logging.getLogger(__name__)
router = APIRouter()


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
