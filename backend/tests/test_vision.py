"""Tests for vision modules (camera, Gemini)."""

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


class TestCamera:
    @patch("src.vision.camera.cv2")
    def test_capture_frame(self, mock_cv2):
        from src.vision.camera import Camera

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
        mock_cv2.VideoCapture.return_value = mock_cap

        cam = Camera(index=0)
        cam.open()
        frame = cam.capture_frame()
        assert frame.shape == (480, 640, 3)

    @patch("src.vision.camera.cv2")
    def test_capture_jpeg(self, mock_cv2):
        from src.vision.camera import Camera

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cv2.imencode.return_value = (True, np.array([0xFF, 0xD8], dtype=np.uint8))

        cam = Camera(index=0)
        cam.open()
        jpeg = cam.capture_jpeg()
        assert isinstance(jpeg, bytes)

    @patch("src.vision.camera.cv2")
    def test_camera_open_failure(self, mock_cv2):
        from src.vision.camera import Camera

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_cv2.VideoCapture.return_value = mock_cap

        cam = Camera(index=99)
        with pytest.raises(RuntimeError, match="Cannot open camera"):
            cam.open()


class TestGeminiVision:
    @patch("src.vision.gemini.camera")
    @patch("src.vision.gemini.settings")
    async def test_analyze_no_api_key(self, mock_settings, mock_camera):
        from src.vision.gemini import GeminiVision

        mock_settings.gemini_api_key = ""
        vision = GeminiVision()

        with pytest.raises(RuntimeError, match="HUGO_GEMINI_API_KEY"):
            await vision.analyze("test")

    @patch("src.vision.gemini.camera")
    @patch("src.vision.gemini.genai")
    @patch("src.vision.gemini.settings")
    async def test_analyze_success(self, mock_settings, mock_genai, mock_camera):
        from src.vision.gemini import GeminiVision

        mock_settings.gemini_api_key = "test-key"
        mock_settings.gemini_model = "gemini-2.0-flash"
        mock_camera.capture_jpeg.return_value = b"\xff\xd8fake"

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "I see a room"
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
        mock_genai.Client.return_value = mock_client

        vision = GeminiVision()
        result = await vision.analyze("What do you see?")
        assert result == "I see a room"
