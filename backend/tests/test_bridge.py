"""Tests for bridge modules (OpenClaw client, tool endpoints)."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


class TestOpenClawClient:
    @patch("src.bridge.openclaw.httpx.AsyncClient")
    async def test_send_message_success(self, mock_client_cls):
        from src.bridge.openclaw import OpenClawClient

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "Hello!"}
        mock_response.raise_for_status = AsyncMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = OpenClawClient()
        client._client = mock_client

        result = await client.send_message("hi")
        assert result == "Hello!"

    @patch("src.bridge.openclaw.httpx.AsyncClient")
    async def test_send_message_failure(self, mock_client_cls):
        from src.bridge.openclaw import OpenClawClient

        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("connection refused")
        mock_client_cls.return_value = mock_client

        client = OpenClawClient()
        client._client = mock_client

        result = await client.send_message("hi")
        assert result is None


class TestToolEndpoints:
    @patch("src.bridge.tools.voice_pipeline")
    @patch("src.bridge.tools.gemini_vision")
    def test_status_endpoint(self, mock_vision, mock_voice):
        from src.main import app

        mock_voice._models_loaded = False
        mock_vision._client = None

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/tools/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    @patch("src.bridge.tools.voice_pipeline")
    def test_speak_endpoint(self, mock_voice):
        from src.main import app

        mock_voice.speak = AsyncMock()

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/tools/voice/speak", json={"text": "hello"})
        assert resp.status_code == 200

    @patch("src.bridge.tools.gemini_vision")
    def test_vision_endpoint(self, mock_vision):
        from src.main import app

        mock_vision.analyze = AsyncMock(return_value="I see things")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/tools/vision/analyze", json={"query": "describe"})
        assert resp.status_code == 200
        assert "I see things" in resp.json()["description"]
