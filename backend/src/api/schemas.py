"""Pydantic request/response models for the API."""

from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str


class StatusResponse(BaseModel):
    robot_connected: bool
    agent_model: str
    voice_engine: str
    active_integrations: list[str]


class IntegrationInfo(BaseModel):
    name: str
    description: str
    active: bool


class IntegrationConfigRequest(BaseModel):
    config: dict[str, str]


class ProviderSwitchRequest(BaseModel):
    provider: str
    model: str | None = None


class VoiceSwitchRequest(BaseModel):
    engine: str  # "personaplex" or "fallback"
