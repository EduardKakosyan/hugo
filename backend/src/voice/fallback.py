"""Cloud TTS/STT fallback when PersonaPlex is unavailable."""

from __future__ import annotations

import logging

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class CloudVoiceEngine:
    """Fallback voice engine using OpenAI Whisper (STT) and OpenAI TTS."""

    def __init__(self) -> None:
        self._api_key = settings.openai_api_key

    async def speech_to_text(self, audio_data: bytes) -> str:
        """Transcribe audio using OpenAI Whisper API."""
        if not self._api_key:
            logger.error("OpenAI API key not set — cannot use cloud STT")
            return ""

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                files={"file": ("audio.wav", audio_data, "audio/wav")},
                data={"model": "whisper-1"},
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json().get("text", "")

    async def text_to_speech(self, text: str) -> bytes:
        """Generate speech using OpenAI TTS API."""
        if not self._api_key:
            logger.error("OpenAI API key not set — cannot use cloud TTS")
            return b""

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "tts-1",
                    "input": text,
                    "voice": "onyx",
                    "response_format": "wav",
                },
                timeout=30.0,
            )
            response.raise_for_status()
            return response.content
