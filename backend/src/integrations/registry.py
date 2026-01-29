"""Plugin registry — discovers, loads, and manages integration lifecycle."""

from __future__ import annotations

import logging
from typing import Any

from src.config import Settings
from src.integrations.base import Integration

logger = logging.getLogger(__name__)


class IntegrationRegistry:
    """Manages the lifecycle of integration plugins."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._integrations: dict[str, Integration] = {}
        self._active: set[str] = set()

    async def discover_and_load(self) -> None:
        """Discover and load available integrations based on config."""
        from src.integrations.calendar import CalendarIntegration
        from src.integrations.obsidian import ObsidianIntegration
        from src.integrations.outlook import OutlookIntegration

        available: list[tuple[str, type[Integration], dict[str, Any]]] = [
            (
                "outlook",
                OutlookIntegration,
                {
                    "client_id": self._settings.microsoft_client_id,
                    "client_secret": self._settings.microsoft_client_secret,
                    "tenant_id": self._settings.microsoft_tenant_id,
                },
            ),
            (
                "calendar",
                CalendarIntegration,
                {"credentials_json": self._settings.google_calendar_credentials_json},
            ),
            (
                "obsidian",
                ObsidianIntegration,
                {
                    "api_key": self._settings.obsidian_api_key,
                    "host": self._settings.obsidian_host,
                },
            ),
        ]

        for name, cls, config in available:
            try:
                integration = cls()
                self._integrations[name] = integration
                success = await integration.setup(config)
                if success:
                    self._active.add(name)
                    # Cache tools for sync access
                    integration._cached_tools = await integration.get_tools()  # type: ignore[attr-defined]
                    logger.info("Integration loaded: %s", name)
                else:
                    logger.info("Integration not configured: %s", name)
            except Exception as e:
                logger.warning("Failed to load integration %s: %s", name, e)

    def active_integrations(self) -> list[Integration]:
        """Return list of active (successfully configured) integrations."""
        return [self._integrations[name] for name in self._active]

    def list_all(self) -> list[dict[str, Any]]:
        """Return info about all known integrations."""
        result = []
        for name, integration in self._integrations.items():
            result.append({
                "name": name,
                "description": integration.description,
                "active": name in self._active,
            })
        return result

    async def configure(self, name: str, config: dict[str, Any]) -> bool:
        """(Re)configure an integration at runtime."""
        if name not in self._integrations:
            return False
        integration = self._integrations[name]
        await integration.teardown()
        success = await integration.setup(config)
        if success:
            self._active.add(name)
            integration._cached_tools = await integration.get_tools()  # type: ignore[attr-defined]
        else:
            self._active.discard(name)
        return success

    async def execute_tool(self, tool_name: str, args: dict[str, Any]) -> str | None:
        """Try to execute a tool across all active integrations."""
        for integration in self.active_integrations():
            tools = getattr(integration, "_cached_tools", [])
            tool_names = [t["function"]["name"] for t in tools]
            if tool_name in tool_names:
                return await integration.execute_tool(tool_name, args)
        return None

    async def teardown_all(self) -> None:
        """Teardown all integrations."""
        for name, integration in self._integrations.items():
            try:
                await integration.teardown()
            except Exception as e:
                logger.warning(
                    "Error tearing down integration '%s': %s", name, e
                )
        self._active.clear()
