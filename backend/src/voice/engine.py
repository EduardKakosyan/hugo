"""Voice engine manager — switches between PersonaPlex and cloud fallback."""

from __future__ import annotations

import logging
from typing import Any

from src.config import VoiceSettings

logger = logging.getLogger(__name__)


class VoiceEngine:
    """Manages voice I/O by delegating to the configured engine."""

    def __init__(self, config: VoiceSettings) -> None:
        self._config = config
        self._engine: Any = None

    @property
    def engine_name(self) -> str:
        return self._config.engine

    async def initialize(self) -> None:
        """Initialize the configured voice engine."""
        if self._config.engine == "personaplex":
            from src.voice.personaplex import PersonaPlexEngine

            self._engine = PersonaPlexEngine(
                host=self._config.personaplex_host,
                port=self._config.personaplex_port,
            )
            connected = await self._engine.connect()
            if not connected:
                logger.warning("PersonaPlex unavailable, falling back to cloud TTS/STT")
                from src.voice.fallback import CloudVoiceEngine

                self._engine = CloudVoiceEngine()
        else:
            from src.voice.fallback import CloudVoiceEngine

            self._engine = CloudVoiceEngine()

        logger.info("Voice engine initialized: %s", type(self._engine).__name__)

    async def speech_to_text(self, audio_data: bytes) -> str:
        """Convert speech audio to text."""
        if self._engine is None:
            await self.initialize()
        return await self._engine.speech_to_text(audio_data)

    async def text_to_speech(self, text: str) -> bytes:
        """Convert text to speech audio."""
        if self._engine is None:
            await self.initialize()
        return await self._engine.text_to_speech(text)

    def switch_engine(self, engine_name: str) -> None:
        """Switch to a different voice engine. Requires re-initialization."""
        self._config.engine = engine_name
        self._engine = None
        logger.info("Voice engine will switch to: %s", engine_name)
