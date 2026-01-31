"""Tool callback endpoints – called by OpenClaw when Claude invokes tools."""

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from src.vision.gemini import gemini_vision
from src.voice.pipeline import voice_pipeline

logger = logging.getLogger("hugo.bridge.tools")

router = APIRouter(prefix="/tools", tags=["tools"])


class VisionRequest(BaseModel):
    query: str = "Describe what you see in detail."


class VisionResponse(BaseModel):
    description: str


class SpeakRequest(BaseModel):
    text: str


class SpeakResponse(BaseModel):
    ok: bool


class StatusResponse(BaseModel):
    status: str
    services: dict[str, str]


@router.post("/vision/analyze", response_model=VisionResponse)
async def analyze_vision(req: VisionRequest) -> VisionResponse:
    try:
        description = await gemini_vision.analyze(req.query)
        return VisionResponse(description=description)
    except Exception as e:
        logger.error("Vision analysis failed: %s", e)
        return VisionResponse(description=f"Vision unavailable: {e}")


@router.post("/voice/speak", response_model=SpeakResponse)
async def speak_text(req: SpeakRequest) -> SpeakResponse:
    try:
        await voice_pipeline.speak(req.text)
        return SpeakResponse(ok=True)
    except Exception as e:
        logger.error("TTS failed: %s", e)
        return SpeakResponse(ok=False)


@router.get("/status", response_model=StatusResponse)
async def tool_status() -> StatusResponse:
    services: dict[str, str] = {
        "voice_pipeline": "ok" if voice_pipeline._models_loaded else "not_loaded",
        "gemini": "configured" if gemini_vision._client is not None else "not_configured",
    }
    return StatusResponse(status="ok", services=services)
