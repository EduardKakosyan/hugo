"""REST API routes – text chat fallback and status."""

import logging

from fastapi import APIRouter

from src.api.schemas import ChatRequest, ChatResponse, StatusResponse
from src.bridge.openclaw import openclaw_client
from src.vision.gemini import gemini_vision
from src.voice.pipeline import voice_pipeline

logger = logging.getLogger("hugo.api")

router = APIRouter(prefix="/api", tags=["api"])


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    response = await openclaw_client.send_message(req.message)
    if response is None:
        return ChatResponse(response=None, error="Failed to get response from OpenClaw")
    return ChatResponse(response=response)


@router.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    return StatusResponse(
        status="ok",
        voice="ok" if voice_pipeline._models_loaded else "not_loaded",
        vision="configured" if gemini_vision._client is not None else "not_configured",
        openclaw="unknown",
    )
