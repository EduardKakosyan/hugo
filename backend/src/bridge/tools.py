"""Tool callback endpoints – called by OpenClaw when Claude invokes tools."""

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from src.bridge.tool_registry import ToolDef, registry
from src.events import VISION_RESULT, Event, bus
from src.vision import get_active_provider_name, get_provider
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


# ---------------------------------------------------------------------------
# Tool handler functions (used by both FastAPI routes and the registry)
# ---------------------------------------------------------------------------


async def _analyze_vision(query: str = "Describe what you see in detail.") -> str:
    provider = get_provider()
    return await provider.analyze(query)


async def _speak_text(text: str) -> bool:
    await voice_pipeline.speak(text)
    return True


# ---------------------------------------------------------------------------
# Register tools in the registry
# ---------------------------------------------------------------------------

registry.register(
    ToolDef(
        name="look_around",
        description="Capture and analyze what the camera sees",
        handler=_analyze_vision,
        category="vision",
    )
)

registry.register(
    ToolDef(
        name="speak_to_user",
        description="Speak text aloud through the speaker",
        handler=_speak_text,
        category="voice",
    )
)


# ---------------------------------------------------------------------------
# FastAPI endpoints
# ---------------------------------------------------------------------------


@router.post("/vision/analyze", response_model=VisionResponse)
async def analyze_vision(req: VisionRequest) -> VisionResponse:
    try:
        description = await _analyze_vision(req.query)
        await bus.emit(Event(
            type=VISION_RESULT,
            data={"query": req.query, "description": description},
            source="vision",
        ))
        return VisionResponse(description=description)
    except Exception as e:
        logger.error("Vision analysis failed: %s", e)
        return VisionResponse(description=f"Vision unavailable: {e}")


@router.post("/voice/speak", response_model=SpeakResponse)
async def speak_text_endpoint(req: SpeakRequest) -> SpeakResponse:
    try:
        await _speak_text(req.text)
        return SpeakResponse(ok=True)
    except Exception as e:
        logger.error("TTS failed: %s", e)
        return SpeakResponse(ok=False)


@router.get("/status", response_model=StatusResponse)
async def tool_status() -> StatusResponse:
    services: dict[str, str] = {
        "voice_pipeline": "ok" if voice_pipeline._models_loaded else "not_loaded",
        "vision_provider": get_active_provider_name(),
    }
    return StatusResponse(status="ok", services=services)


@router.get("/registry")
async def list_registered_tools() -> dict[str, Any]:
    """List all registered tools and their status."""
    tools = registry.list_tools(enabled_only=False)
    return {
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "enabled": t.enabled,
            }
            for t in tools
        ]
    }
