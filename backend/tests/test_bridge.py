"""Tests for bridge modules (OpenClaw client, tool endpoints)."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


class TestOpenClawClient:
    async def test_send_message_success(self):
        from src.bridge.openclaw import OpenClawClient

        client = OpenClawClient()

        # Simulate an already-connected state with a mock websocket
        mock_ws = AsyncMock()
        client._ws = mock_ws
        client._connected = True

        # Set up the listener to resolve the pending future when send is called
        req_id_holder: list[str] = []

        async def fake_send(data):
            msg = json.loads(data)
            req_id_holder.append(msg["id"])

        mock_ws.send = fake_send

        # Run send_message in a task so we can resolve the future
        async def do_send():
            return await client.send_message("hi")

        task = asyncio.create_task(do_send())
        # Let the send happen
        await asyncio.sleep(0.05)

        # Resolve the pending future as if the listener got the response
        req_id = req_id_holder[0]
        fut = client._pending[req_id]
        fut.set_result({"status": "ok", "text": "Hello!"})

        result = await task
        assert result == "Hello!"

    async def test_send_message_failure(self):
        from src.bridge.openclaw import OpenClawClient

        client = OpenClawClient()

        # Simulate connected state but send raises
        mock_ws = AsyncMock()
        mock_ws.send.side_effect = Exception("connection refused")
        client._ws = mock_ws
        client._connected = True

        result = await client.send_message("hi")
        assert result is None

    async def test_reset_session(self):
        from src.bridge.openclaw import OpenClawClient

        client = OpenClawClient()
        old_key = client._session_key
        client.reset_session()
        assert client._session_key != old_key
        assert client._session_key.startswith("hugo-")

    async def test_session_key_used_in_send(self):
        from src.bridge.openclaw import OpenClawClient

        client = OpenClawClient()
        mock_ws = AsyncMock()
        client._ws = mock_ws
        client._connected = True

        sent_messages: list[dict] = []

        async def capture_send(data):
            sent_messages.append(json.loads(data))

        mock_ws.send = capture_send

        # Start streaming send (non-blocking)
        req_id = await client.send_message_streaming("hi")

        assert len(sent_messages) == 1
        assert sent_messages[0]["params"]["sessionKey"] == client._session_key


class TestToolEndpoints:
    @patch("src.bridge.tools.voice_pipeline")
    @patch("src.bridge.tools.get_active_provider_name", return_value="gemini")
    def test_status_endpoint(self, mock_provider_name, mock_voice):
        from src.main import app

        mock_voice._models_loaded = False

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

    @patch("src.bridge.tools.get_provider")
    def test_vision_endpoint(self, mock_get_provider):
        from src.main import app

        mock_provider = AsyncMock()
        mock_provider.analyze = AsyncMock(return_value="I see things")
        mock_get_provider.return_value = mock_provider

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/tools/vision/analyze", json={"query": "describe"})
        assert resp.status_code == 200
        assert "I see things" in resp.json()["description"]
