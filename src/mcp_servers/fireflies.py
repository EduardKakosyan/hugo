"""MCP server for Fireflies.ai — meeting transcripts and summaries."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

mcp = FastMCP("fireflies", instructions="Fireflies.ai meeting transcripts and summaries.")

FIREFLIES_API_URL = "https://api.fireflies.ai/graphql"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ['FIREFLIES_API_KEY']}",
        "Content-Type": "application/json",
    }


async def _query(graphql: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a GraphQL query against the Fireflies API."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            FIREFLIES_API_URL,
            headers=_headers(),
            json={"query": graphql, "variables": variables or {}},
            timeout=30.0,
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        if "errors" in data:
            msg = f"Fireflies API error: {data['errors']}"
            raise RuntimeError(msg)
        return data.get("data", {})


@mcp.tool()
async def list_recent_meetings(limit: int = 10) -> list[dict[str, Any]]:
    """List recent meeting transcripts.

    Args:
        limit: Number of recent meetings to return (max 50).
    """
    query = f"""
    query {{
        transcripts(limit: {min(limit, 50)}) {{
            id
            title
            date
            duration
            participants
            summary {{
                overview
                action_items
                keywords
            }}
        }}
    }}
    """
    data = await _query(query)
    transcripts = data.get("transcripts", [])
    return [
        {
            "id": t["id"],
            "title": t.get("title", "Untitled"),
            "date": t.get("date"),
            "duration_minutes": t.get("duration", 0),
            "participants": t.get("participants", []),
            "summary": t.get("summary", {}).get("overview", ""),
            "action_items": t.get("summary", {}).get("action_items", []),
        }
        for t in transcripts
    ]


@mcp.tool()
async def get_meeting_summary(transcript_id: str) -> dict[str, Any]:
    """Get detailed summary of a specific meeting.

    Args:
        transcript_id: The Fireflies transcript ID.
    """
    query = """
    query($id: String!) {
        transcript(id: $id) {
            id
            title
            date
            duration
            participants
            summary {
                overview
                action_items
                shorthand_bullet
                keywords
            }
            sentences {
                speaker_name
                text
            }
        }
    }
    """
    data = await _query(query, {"id": transcript_id})
    t = data.get("transcript", {})
    summary = t.get("summary", {})

    return {
        "id": t.get("id"),
        "title": t.get("title", "Untitled"),
        "date": t.get("date"),
        "duration_minutes": t.get("duration", 0),
        "participants": t.get("participants", []),
        "overview": summary.get("overview", ""),
        "action_items": summary.get("action_items", []),
        "bullet_points": summary.get("shorthand_bullet", []),
        "keywords": summary.get("keywords", []),
    }


@mcp.tool()
async def search_transcripts(query_text: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search meeting transcripts by keyword.

    Args:
        query_text: Search keyword or phrase.
        limit: Max results to return.
    """
    query = """
    query($q: String!, $limit: Int!) {
        transcripts(limit: $limit, search: $q) {
            id
            title
            date
            participants
            summary {
                overview
            }
        }
    }
    """
    data = await _query(query, {"q": query_text, "limit": min(limit, 20)})
    transcripts = data.get("transcripts", [])
    return [
        {
            "id": t["id"],
            "title": t.get("title", "Untitled"),
            "date": t.get("date"),
            "participants": t.get("participants", []),
            "summary": t.get("summary", {}).get("overview", ""),
        }
        for t in transcripts
    ]


# ── Server Entry Point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
