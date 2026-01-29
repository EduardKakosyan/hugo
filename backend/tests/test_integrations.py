"""Tests for the integration plugin system."""

from __future__ import annotations

import pytest

from src.integrations.base import Integration
from src.integrations.outlook import OutlookIntegration
from src.integrations.calendar import CalendarIntegration
from src.integrations.obsidian import ObsidianIntegration


class TestIntegrationBase:
    def test_outlook_has_required_attrs(self) -> None:
        integration = OutlookIntegration()
        assert integration.name == "outlook"
        assert integration.description

    def test_calendar_has_required_attrs(self) -> None:
        integration = CalendarIntegration()
        assert integration.name == "calendar"
        assert integration.description

    def test_obsidian_has_required_attrs(self) -> None:
        integration = ObsidianIntegration()
        assert integration.name == "obsidian"
        assert integration.description

    @pytest.mark.asyncio
    async def test_outlook_setup_fails_without_config(self) -> None:
        integration = OutlookIntegration()
        result = await integration.setup({})
        assert result is False

    @pytest.mark.asyncio
    async def test_calendar_setup_fails_without_config(self) -> None:
        integration = CalendarIntegration()
        result = await integration.setup({})
        assert result is False

    @pytest.mark.asyncio
    async def test_obsidian_setup_fails_without_config(self) -> None:
        integration = ObsidianIntegration()
        result = await integration.setup({})
        assert result is False

    @pytest.mark.asyncio
    async def test_outlook_tools_schema(self) -> None:
        integration = OutlookIntegration()
        tools = await integration.get_tools()
        assert len(tools) == 3
        names = {t["function"]["name"] for t in tools}
        assert "outlook_read_inbox" in names
        assert "outlook_send_email" in names
        assert "outlook_search_inbox" in names

    @pytest.mark.asyncio
    async def test_calendar_tools_schema(self) -> None:
        integration = CalendarIntegration()
        tools = await integration.get_tools()
        assert len(tools) == 3
        names = {t["function"]["name"] for t in tools}
        assert "calendar_list_events" in names
        assert "calendar_create_event" in names

    @pytest.mark.asyncio
    async def test_obsidian_tools_schema(self) -> None:
        integration = ObsidianIntegration()
        tools = await integration.get_tools()
        assert len(tools) == 3
        names = {t["function"]["name"] for t in tools}
        assert "obsidian_search_notes" in names
        assert "obsidian_read_note" in names
        assert "obsidian_create_note" in names
