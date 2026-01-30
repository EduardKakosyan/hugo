"""FastAPI application entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.agent.core import AgentOrchestrator
from src.api.routes import router as api_router
from src.api.websocket import router as ws_router
from src.config import settings
from src.integrations.registry import IntegrationRegistry
from src.robot.controller import RobotController
from src.robot.simulator import SimulatorManager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle — connect robot, start agent, load integrations."""
    # Startup — optionally spawn the simulator daemon if no external one is running
    simulator: SimulatorManager | None = None
    if settings.robot.simulation:
        # Try connecting first; if it fails, spawn the daemon ourselves
        probe = RobotController(settings.robot)
        await probe.connect()
        if not probe.connected:
            logger.info("No running simulator found — spawning reachy-mini-daemon --sim")
            simulator = SimulatorManager()
            await simulator.start()
            app.state.simulator = simulator
        else:
            await probe.disconnect()

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
    if simulator is not None:
        await simulator.stop()


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
