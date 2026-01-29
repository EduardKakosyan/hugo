"""Application configuration loaded from environment variables and YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


def _load_yaml_config() -> dict[str, Any]:
    config_path = Path(__file__).parent.parent / "configs" / "default.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


_yaml = _load_yaml_config()


class RobotSettings(BaseSettings):
    host: str = Field(default=_yaml.get("robot", {}).get("host", "localhost"))
    port: int = Field(default=_yaml.get("robot", {}).get("port", 8000))
    simulation: bool = Field(default=_yaml.get("robot", {}).get("simulation", True))
    state_frequency_hz: int = Field(
        default=_yaml.get("robot", {}).get("state_frequency_hz", 20)
    )

    model_config = {"env_prefix": "REACHY_"}


class AgentSettings(BaseSettings):
    default_provider: str = Field(
        default=_yaml.get("agent", {}).get("default_provider", "gemini/gemini-2.5-flash")
    )
    system_prompt: str = Field(
        default=_yaml.get("agent", {}).get(
            "system_prompt",
            "You are HUGO, a personal assistant embodied in a Reachy Mini robot.",
        )
    )
    providers: dict[str, Any] = Field(
        default_factory=lambda: _yaml.get("agent", {}).get("providers", {})
    )

    model_config = {"env_prefix": "AGENT_"}


class VoiceSettings(BaseSettings):
    engine: str = Field(default=_yaml.get("voice", {}).get("engine", "fallback"))
    personaplex_host: str = Field(default="localhost")
    personaplex_port: int = Field(default=8998)

    model_config = {"env_prefix": "VOICE_"}


class VisionSettings(BaseSettings):
    enabled: bool = Field(default=_yaml.get("vision", {}).get("enabled", True))
    stream_quality: int = Field(default=_yaml.get("vision", {}).get("stream_quality", 80))
    analysis_provider: str = Field(
        default=_yaml.get("vision", {}).get("analysis_provider", "gemini/gemini-2.5-flash")
    )


class Settings(BaseSettings):
    robot: RobotSettings = Field(default_factory=RobotSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    vision: VisionSettings = Field(default_factory=VisionSettings)

    # API keys (loaded from env)
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    huggingface_api_key: str = ""
    ollama_host: str = "http://localhost:11434"

    # Integration keys
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_tenant_id: str = ""
    google_calendar_credentials_json: str = ""
    obsidian_api_key: str = ""
    obsidian_host: str = "http://localhost:27124"


settings = Settings()
