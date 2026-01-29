"""Obsidian integration via the Local REST API plugin."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.integrations.base import Integration

logger = logging.getLogger(__name__)


class ObsidianIntegration(Integration):
    name = "obsidian"
    description = "Search, read, and create notes in Obsidian"

    def __init__(self) -> None:
        self._api_key = ""
        self._host = "http://localhost:27124"

    async def setup(self, config: dict[str, Any]) -> bool:
        self._api_key = config.get("api_key", "")
        self._host = config.get("host", "http://localhost:27124")

        if not self._api_key:
            return False

        # Verify connectivity
        try:
            async with httpx.AsyncClient(verify=False) as client:
                resp = await client.get(
                    f"{self._host}/",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    timeout=5.0,
                )
                return resp.status_code == 200
        except Exception as e:
            logger.warning("Obsidian connection failed: %s", e)
            return False

    async def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "obsidian_search_notes",
                    "description": "Search for notes in the Obsidian vault",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "obsidian_read_note",
                    "description": "Read the content of a specific note",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Note path (e.g. 'folder/note.md')"},
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "obsidian_create_note",
                    "description": "Create a new note in Obsidian",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Note path (e.g. 'folder/note.md')"},
                            "content": {"type": "string", "description": "Note content in Markdown"},
                        },
                        "required": ["path", "content"],
                    },
                },
            },
        ]

    async def execute_tool(self, tool_name: str, args: dict[str, Any]) -> str:
        headers = {"Authorization": f"Bearer {self._api_key}"}

        if tool_name == "obsidian_search_notes":
            async with httpx.AsyncClient(verify=False) as client:
                resp = await client.post(
                    f"{self._host}/search/simple/",
                    headers=headers,
                    json={"query": args["query"]},
                    timeout=10.0,
                )
                resp.raise_for_status()
                results = resp.json()
                if not results:
                    return "No notes found."
                lines = [f"- {r.get('filename', 'unknown')}" for r in results[:10]]
                return "\n".join(lines)

        if tool_name == "obsidian_read_note":
            path = args["path"]
            async with httpx.AsyncClient(verify=False) as client:
                resp = await client.get(
                    f"{self._host}/vault/{path}",
                    headers={**headers, "Accept": "text/markdown"},
                    timeout=10.0,
                )
                resp.raise_for_status()
                return resp.text

        if tool_name == "obsidian_create_note":
            path = args["path"]
            content = args["content"]
            async with httpx.AsyncClient(verify=False) as client:
                resp = await client.put(
                    f"{self._host}/vault/{path}",
                    headers={**headers, "Content-Type": "text/markdown"},
                    content=content,
                    timeout=10.0,
                )
                resp.raise_for_status()
                return f"Note created: {path}"

        return f"Unknown tool: {tool_name}"

    async def teardown(self) -> None:
        pass
