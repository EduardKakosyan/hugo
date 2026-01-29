"""REST API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from src.api.schemas import (
    ChatRequest,
    ChatResponse,
    IntegrationConfigRequest,
    IntegrationInfo,
    ProviderSwitchRequest,
    StatusResponse,
    VoiceSwitchRequest,
)

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    """Send a text message and get the agent's response."""
    agent = request.app.state.agent
    response = await agent.chat(body.message)
    return ChatResponse(response=response)


@router.get("/status", response_model=StatusResponse)
async def status(request: Request) -> StatusResponse:
    """Get robot + agent status."""
    robot = request.app.state.robot
    agent = request.app.state.agent
    integrations = request.app.state.integrations

    active = [i.name for i in integrations.active_integrations()]
    return StatusResponse(
        robot_connected=robot.connected,
        agent_model=agent.llm.model,
        voice_engine="fallback",  # TODO: expose from voice engine
        active_integrations=active,
    )


@router.get("/integrations", response_model=list[IntegrationInfo])
async def list_integrations(request: Request) -> list[IntegrationInfo]:
    """List available integrations."""
    registry = request.app.state.integrations
    return [IntegrationInfo(**info) for info in registry.list_all()]


@router.post("/integrations/{name}/configure")
async def configure_integration(
    request: Request, name: str, body: IntegrationConfigRequest
) -> dict[str, bool]:
    """Configure an integration."""
    registry = request.app.state.integrations
    success = await registry.configure(name, body.config)
    return {"success": success}


@router.post("/settings/provider")
async def switch_provider(request: Request, body: ProviderSwitchRequest) -> dict[str, str]:
    """Switch the LLM provider."""
    agent = request.app.state.agent
    model = body.model or body.provider
    agent.llm.set_model(model)
    return {"model": agent.llm.model}


@router.post("/settings/voice")
async def switch_voice(request: Request, body: VoiceSwitchRequest) -> dict[str, str]:
    """Switch the voice engine."""
    # Voice engine switch is handled via config reload
    return {"engine": body.engine}
