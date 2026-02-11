"""Tests for MCP server tool definitions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


class TestMSGraphServer:
    """Test MS Graph MCP server tool definitions."""

    def test_server_defined(self) -> None:
        """MCP server is properly defined."""
        from src.mcp_servers.ms_graph import mcp

        assert mcp.name == "ms-graph"

    @patch("src.mcp_servers.ms_graph._get_graph_client")
    async def test_read_emails(self, mock_client_fn: MagicMock) -> None:
        """read_emails tool returns expected structure."""
        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.subject = "Test Subject"
        mock_msg.from_.email_address.address = "test@example.com"
        mock_msg.received_date_time = "2026-02-11T10:00:00Z"
        mock_msg.body_preview = "Hello world"
        mock_msg.is_read = False
        mock_msg.importance = "normal"
        mock_msg.id = "msg-123"

        mock_response = MagicMock()
        mock_response.value = [mock_msg]
        mock_client.me.mail_folders.by_mail_folder_id.return_value.messages.get = AsyncMock(
            return_value=mock_response
        )
        mock_client_fn.return_value = mock_client

        from src.mcp_servers.ms_graph import read_emails

        result = await read_emails(folder="inbox", count=5)
        assert len(result) == 1
        assert result[0]["subject"] == "Test Subject"


class TestLinearServer:
    """Test Linear MCP server tool definitions."""

    def test_server_defined(self) -> None:
        from src.mcp_servers.linear_server import mcp

        assert mcp.name == "linear"

    @patch("src.mcp_servers.linear_server._query")
    async def test_list_my_issues(self, mock_query: AsyncMock, mock_linear_response: dict) -> None:
        """list_my_issues returns expected structure."""
        mock_query.return_value = mock_linear_response

        from src.mcp_servers.linear_server import list_my_issues

        result = await list_my_issues(limit=10)
        assert len(result) == 1
        assert result[0]["identifier"] == "ENG-123"
        assert result[0]["title"] == "Fix login bug"

    @patch("src.mcp_servers.linear_server._query")
    async def test_search_issues(self, mock_query: AsyncMock) -> None:
        mock_query.return_value = {
            "issueSearch": {
                "nodes": [
                    {
                        "identifier": "ENG-456",
                        "title": "Add dark mode",
                        "state": {"name": "Todo"},
                        "priority": 3,
                        "url": "https://linear.app/test/issue/ENG-456",
                    }
                ]
            }
        }

        from src.mcp_servers.linear_server import search_issues

        result = await search_issues("dark mode")
        assert len(result) == 1
        assert result[0]["identifier"] == "ENG-456"


class TestFirefliesServer:
    """Test Fireflies MCP server tool definitions."""

    def test_server_defined(self) -> None:
        from src.mcp_servers.fireflies import mcp

        assert mcp.name == "fireflies"

    @patch("src.mcp_servers.fireflies._query")
    async def test_list_recent_meetings(
        self, mock_query: AsyncMock, mock_fireflies_response: dict
    ) -> None:
        mock_query.return_value = mock_fireflies_response

        from src.mcp_servers.fireflies import list_recent_meetings

        result = await list_recent_meetings(limit=5)
        assert len(result) == 1
        assert result[0]["title"] == "Sprint Planning"
        assert len(result[0]["action_items"]) == 2
