"""Pydantic models for REST and WebSocket APIs."""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str | None
    error: str | None = None


class StatusResponse(BaseModel):
    status: str
    voice: str
    vision: str
    openclaw: str


class WSMessage(BaseModel):
    type: str  # "transcript" | "response" | "status" | "error"
    data: str
