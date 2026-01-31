"""Tests for voice modules (VAD, STT, TTS)."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest


class TestVAD:
    def test_process_chunk_not_loaded(self):
        from src.voice.vad import VoiceActivityDetector

        detector = VoiceActivityDetector()
        with pytest.raises(RuntimeError, match="not loaded"):
            detector.process_chunk(np.zeros(512, dtype=np.float32))

    @patch("src.voice.vad.torch")
    def test_process_chunk_speech_detected(self, mock_torch):
        from src.voice.vad import VoiceActivityDetector

        mock_model = MagicMock()
        mock_model.return_value.item.return_value = 0.9

        detector = VoiceActivityDetector(threshold=0.5)
        detector._model = mock_model

        result = detector.process_chunk(np.zeros(512, dtype=np.float32))
        assert result["is_speaking"] is True
        assert result["speech_start"] is True

    @patch("src.voice.vad.torch")
    def test_speech_end_transition(self, mock_torch):
        from src.voice.vad import VoiceActivityDetector

        mock_model = MagicMock()
        detector = VoiceActivityDetector(threshold=0.5)
        detector._model = mock_model
        detector._is_speaking = True

        mock_model.return_value.item.return_value = 0.1
        result = detector.process_chunk(np.zeros(512, dtype=np.float32))
        assert result["speech_end"] is True
        assert result["is_speaking"] is False

    def test_reset(self):
        from src.voice.vad import VoiceActivityDetector

        detector = VoiceActivityDetector()
        detector._is_speaking = True
        detector._model = MagicMock()
        detector.reset()
        assert detector._is_speaking is False


class TestSTT:
    def test_transcribe_not_loaded(self):
        from src.voice.stt import SpeechToText

        engine = SpeechToText()
        with pytest.raises(RuntimeError, match="not loaded"):
            engine.transcribe(np.zeros(16000, dtype=np.float32))

    def test_transcribe_with_mock_model(self):
        from src.voice.stt import SpeechToText

        engine = SpeechToText()
        mock_model = MagicMock()
        mock_model.generate.return_value = {"text": "  hello world  "}
        engine._model = mock_model

        result = engine.transcribe(np.zeros(16000, dtype=np.float32))
        assert result == "hello world"
        mock_model.generate.assert_called_once()


class TestTTS:
    def test_synthesize_not_loaded(self):
        from src.voice.tts import TextToSpeech

        engine = TextToSpeech()
        with pytest.raises(RuntimeError, match="not loaded"):
            engine.synthesize("hello")

    def test_synthesize_with_mock_pipeline(self):
        from src.voice.tts import TextToSpeech

        engine = TextToSpeech()
        mock_pipeline = MagicMock()
        mock_audio = np.zeros(24000, dtype=np.float32)
        mock_pipeline.return_value = (mock_audio, 24000)
        engine._pipeline = mock_pipeline

        audio, sr = engine.synthesize("hello")
        assert sr == 24000
        assert len(audio) == 24000
