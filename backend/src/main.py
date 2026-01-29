"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router as api_router
from src.api.websocket import router as ws_router
from src.config import settings
from src.robot.controller import RobotController
from src.agent.core import AgentOrchestrator
from src.integrations.registry import IntegrationRegistry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle — connect robot, start agent, load integrations."""
    # Startup
    controller = RobotController(settings.robot)
    await controller.connect()
    app.state.robot = controller

    registry = IntegrationRegistry(settings)
    await registry.discover_and_load()
    app.state.integrations = registry

    orchestrator = AgentOrchestrator(settings.agent, controller, registry)
    app.state.agent = orchestrator

    yield

    # Shutdown
    await registry.teardown_all()
    await controller.disconnect()


app = FastAPI(
    title="HUGO",
    description="Personal Assistant Agent for Reachy Mini",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
app.include_router(ws_router)
