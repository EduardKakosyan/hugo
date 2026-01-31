"""Vision providers – pluggable image analysis backends."""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger("hugo.vision")

_active_provider: str = ""


class VisionProvider(Protocol):
    async def analyze(self, query: str = "Describe what you see in detail.") -> str: ...


def get_active_provider_name() -> str:
    global _active_provider
    if not _active_provider:
        from src.config import settings

        _active_provider = settings.vision_provider
    return _active_provider


def set_active_provider(name: str) -> None:
    global _active_provider
    if name not in ("gemini", "mlx"):
        raise ValueError(f"Unknown vision provider: {name}")
    _active_provider = name
    logger.info("Vision provider set to: %s", name)


def get_provider() -> VisionProvider:
    name = get_active_provider_name()
    if name == "mlx":
        from src.vision.mlx_vision import mlx_vision

        return mlx_vision
    else:
        from src.vision.gemini import gemini_vision

        return gemini_vision
