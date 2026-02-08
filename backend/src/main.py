import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.events import TRANSCRIPT_READY, VOICE_SPEAK, Event, bus

logger = logging.getLogger("hugo")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


async def _handle_transcript(event: Event) -> None:
    """Handle voice transcript: broadcast to frontend + send to Claude via OpenClaw."""
    from src.api.websocket import _voice_requests, broadcast
    from src.bridge.openclaw import openclaw_client

    text = event.data["text"]
    logger.info("Transcript: %s", text)
    await broadcast("voice:transcript", {"text": text})
    try:
        req_id = await openclaw_client.send_message_streaming(text)
        _voice_requests.add(req_id)
        await broadcast("chat:start", json.dumps({"reqId": req_id}))
    except Exception as e:
        logger.error("Failed to send voice transcript to OpenClaw: %s", e)
        error_msg = f"Sorry, I couldn't process that: {e}"
        await broadcast("voice:response", {"text": error_msg})


async def _handle_voice_speak(event: Event) -> None:
    """Handle TTS request: speak text aloud."""
    from src.voice.pipeline import voice_pipeline

    text = event.data["text"]
    await voice_pipeline.speak(text)


# Register event handlers
bus.on(TRANSCRIPT_READY, _handle_transcript)
bus.on(VOICE_SPEAK, _handle_voice_speak)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    logger.info("HUGO backend starting on %s:%d", settings.host, settings.port)
    from src.bridge.openclaw import openclaw_client
    from src.voice.pipeline import voice_pipeline

    try:
        await asyncio.wait_for(openclaw_client.connect(), timeout=5.0)
    except Exception:
        logger.warning("OpenClaw not available – continuing without AI bridge", exc_info=True)

    # Auto-start voice pipeline in background so server isn't blocked
    async def _boot_voice() -> None:
        try:
            await voice_pipeline.start()
            logger.info("Voice pipeline auto-started on boot")
            # Notify any connected clients
            from src.api.websocket import broadcast
            await broadcast("voice:status", {"active": True})
        except Exception:
            logger.warning("Voice pipeline failed to auto-start", exc_info=True)

    asyncio.create_task(_boot_voice())

    yield

    await voice_pipeline.stop()
    await openclaw_client.close()

    from src.vision.camera import camera
    camera.close()

    logger.info("HUGO backend stopped")


app = FastAPI(title="HUGO", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
from src.api.routes import router as api_router  # noqa: E402
from src.api.websocket import router as ws_router  # noqa: E402
from src.bridge.tools import router as tools_router  # noqa: E402

app.include_router(tools_router)
app.include_router(api_router)
app.include_router(ws_router)
