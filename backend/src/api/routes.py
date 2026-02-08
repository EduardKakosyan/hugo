"""REST API routes – text chat fallback and status."""

import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.api.schemas import ChatRequest, ChatResponse, StatusResponse
from src.bridge.openclaw import openclaw_client
from src.vision.camera import camera
from src.vision.gemini import gemini_vision
from src.voice.pipeline import voice_pipeline

logger = logging.getLogger("hugo.api")

router = APIRouter(prefix="/api", tags=["api"])

_camera_active = True


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    response = await openclaw_client.send_message(req.message)
    if response is None:
        return ChatResponse(response=None, error="Failed to get response from OpenClaw")
    return ChatResponse(response=response)


@router.get("/camera/stream")
async def camera_stream() -> StreamingResponse:
    """MJPEG stream from the camera at ~10 fps."""

    async def _generate():
        try:
            while _camera_active:
                frame = camera.capture_jpeg()
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            return

    return StreamingResponse(
        _generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.post("/camera/pause")
async def camera_pause():
    """Pause the camera stream and release hardware."""
    global _camera_active
    _camera_active = False
    camera.close()
    logger.info("Camera paused and released")
    return {"status": "paused"}


@router.post("/camera/resume")
async def camera_resume():
    """Resume the camera stream (camera will lazy-open on next capture)."""
    global _camera_active
    _camera_active = True
    logger.info("Camera resumed")
    return {"status": "resumed"}


@router.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    return StatusResponse(
        status="ok",
        voice="ok" if voice_pipeline._running else "not_loaded",
        vision="configured" if gemini_vision._client is not None else "not_configured",
        openclaw="unknown",
    )


@router.get("/debug/voice")
async def debug_voice():
    """Debug endpoint for voice pipeline state."""
    return {
        "running": voice_pipeline._running,
        "stream_active": voice_pipeline._stream is not None and voice_pipeline._stream.active,
        "models_loaded": voice_pipeline._models_loaded,
        "gemini_client": voice_pipeline._gemini_client is not None,
    }
