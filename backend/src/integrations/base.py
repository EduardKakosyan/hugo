"""Base integration protocol/ABC for the plugin system."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Integration(ABC):
    """Abstract base class for all integration plugins.

    Each integration exposes tools that the LLM can call via function calling.
    """

    name: str
    description: str

    @abstractmethod
    async def setup(self, config: dict[str, Any]) -> bool:
        """Initialize the integration with configuration. Returns True on success."""
        ...

    @abstractmethod
    async def get_tools(self) -> list[dict[str, Any]]:
        """Return OpenAI-format tool schemas for this integration."""
        ...

    def get_tools_sync(self) -> list[dict[str, Any]]:
        """Synchronous version for building tool lists. Override if async setup needed."""
        import asyncio

        try:
            asyncio.get_running_loop()
            # Already in async context — use cached tools
            return getattr(self, "_cached_tools", [])
        except RuntimeError:
            return asyncio.run(self.get_tools())

    @abstractmethod
    async def execute_tool(self, tool_name: str, args: dict[str, Any]) -> str:
        """Execute a tool call and return the result as a string."""
        ...

    @abstractmethod
    async def teardown(self) -> None:
        """Clean up resources."""
        ...
