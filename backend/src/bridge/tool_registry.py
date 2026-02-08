"""Tool registry — discover and manage available tools."""

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("hugo.bridge.tool_registry")

ToolHandler = Callable[..., Coroutine[Any, Any, Any]]


@dataclass
class ToolDef:
    """Definition of a tool that Claude can invoke."""

    name: str
    description: str
    handler: ToolHandler
    category: str  # "vision", "voice", "general"
    enabled: bool = True


class ToolRegistry:
    """Registry for dynamically managing available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool: ToolDef) -> None:
        """Register a tool definition."""
        self._tools[tool.name] = tool
        logger.info("Registered tool: %s [%s]", tool.name, tool.category)

    def unregister(self, name: str) -> None:
        """Remove a tool by name."""
        self._tools.pop(name, None)
        logger.info("Unregistered tool: %s", name)

    def get(self, name: str) -> ToolDef | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(
        self, category: str | None = None, enabled_only: bool = True
    ) -> list[ToolDef]:
        """List tools, optionally filtering by category and enabled status."""
        tools = list(self._tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        if enabled_only:
            tools = [t for t in tools if t.enabled]
        return tools

    def enable(self, name: str) -> None:
        """Enable a tool."""
        if tool := self._tools.get(name):
            tool.enabled = True
            logger.info("Enabled tool: %s", name)

    def disable(self, name: str) -> None:
        """Disable a tool."""
        if tool := self._tools.get(name):
            tool.enabled = False
            logger.info("Disabled tool: %s", name)


# Global registry singleton
registry = ToolRegistry()
