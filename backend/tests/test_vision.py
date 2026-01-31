"""Tests for vision modules (camera, Gemini, MLX, provider factory)."""

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
        mock_camera.capture_jpeg.return_value = b"\xff\xd8fake"
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


class TestMLXVision:
    @patch("src.vision.mlx_vision.camera")
    async def test_analyze_success(self, mock_camera):
        from src.vision.mlx_vision import MLXVision

        mock_camera.capture_jpeg.return_value = b"\xff\xd8fake"

        vision = MLXVision()
        vision._run_inference = MagicMock(return_value="I see a desk")

        result = await vision.analyze("What do you see?")

        assert result == "I see a desk"
        vision._run_inference.assert_called_once()
        args = vision._run_inference.call_args[0]
        assert args[0] == "What do you see?"

    @patch("src.vision.mlx_vision.camera")
    async def test_analyze_model_load_failure(self, mock_camera):
        from src.vision.mlx_vision import MLXVision

        mock_camera.capture_jpeg.return_value = b"\xff\xd8fake"

        vision = MLXVision()
        vision._run_inference = MagicMock(side_effect=RuntimeError("Model not found"))

        with pytest.raises(RuntimeError, match="Model not found"):
            await vision.analyze("test")


class TestProviderFactory:
    def test_set_and_get_provider_gemini(self):
        from src.vision import get_active_provider_name, set_active_provider

        set_active_provider("gemini")
        assert get_active_provider_name() == "gemini"

    def test_set_and_get_provider_mlx(self):
        from src.vision import get_active_provider_name, set_active_provider

        set_active_provider("mlx")
        assert get_active_provider_name() == "mlx"

    def test_set_invalid_provider(self):
        from src.vision import set_active_provider

        with pytest.raises(ValueError, match="Unknown vision provider"):
            set_active_provider("invalid")

    def test_get_provider_returns_gemini(self):
        from src.vision import get_provider, set_active_provider
        from src.vision.gemini import GeminiVision

        set_active_provider("gemini")
        provider = get_provider()
        assert isinstance(provider, GeminiVision)

    def test_get_provider_returns_mlx(self):
        from src.vision import get_provider, set_active_provider
        from src.vision.mlx_vision import MLXVision

        set_active_provider("mlx")
        provider = get_provider()
        assert isinstance(provider, MLXVision)
