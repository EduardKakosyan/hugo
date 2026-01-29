"""Tests for the voice engine."""

from __future__ import annotations

from src.config import VoiceSettings
from src.voice.engine import VoiceEngine


class TestVoiceEngine:
    def test_default_engine(self) -> None:
        config = VoiceSettings()
        engine = VoiceEngine(config)
        assert engine.engine_name == "fallback"

    def test_switch_engine(self) -> None:
        config = VoiceSettings()
        engine = VoiceEngine(config)
        engine.switch_engine("personaplex")
        assert engine.engine_name == "personaplex"
