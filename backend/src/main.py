import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings

logger = logging.getLogger("hugo")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    logger.info("HUGO backend starting on %s:%d", settings.host, settings.port)
    # Import here to avoid circular imports and allow graceful degradation
    from src.api.websocket import broadcast
    from src.bridge.openclaw import openclaw_client
    from src.voice.pipeline import voice_pipeline

    await openclaw_client.connect()

    async def on_transcript(text: str) -> None:
        logger.info("Transcript: %s", text)
        await broadcast("voice:transcript", {"text": text})
        response = await openclaw_client.send_message(text)
        if response:
            await broadcast("voice:response", {"text": response})
            await voice_pipeline.speak(response)

    voice_pipeline.on_transcript = on_transcript

    yield

    await voice_pipeline.stop()
    await openclaw_client.close()
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
