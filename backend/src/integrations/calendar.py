"""Google Calendar integration via Google Calendar API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.integrations.base import Integration

logger = logging.getLogger(__name__)


class CalendarIntegration(Integration):
    name = "calendar"
    description = "List events, create events, and check availability on Google Calendar"

    def __init__(self) -> None:
        self._credentials_json = ""
        self._access_token = ""

    async def setup(self, config: dict[str, Any]) -> bool:
        self._credentials_json = config.get("credentials_json", "")
        if not self._credentials_json:
            return False

        # In production, use google-auth library for proper OAuth2 flow.
        # This is a simplified placeholder that expects a pre-obtained access token.
        try:
            import json

            creds = json.loads(self._credentials_json)
            self._access_token = creds.get("access_token", "")
            return bool(self._access_token)
        except Exception as e:
            logger.warning("Calendar setup failed: %s", e)
            return False

    async def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "calendar_list_events",
                    "description": "List upcoming events from Google Calendar",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of events to return",
                                "default": 10,
                            }
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calendar_create_event",
                    "description": "Create a new event on Google Calendar",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string", "description": "Event title"},
                            "start": {"type": "string", "description": "Start time (ISO 8601)"},
                            "end": {"type": "string", "description": "End time (ISO 8601)"},
                            "description": {"type": "string", "description": "Event description"},
                        },
                        "required": ["summary", "start", "end"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calendar_check_availability",
                    "description": "Check if a time slot is available",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start": {"type": "string", "description": "Start time (ISO 8601)"},
                            "end": {"type": "string", "description": "End time (ISO 8601)"},
                        },
                        "required": ["start", "end"],
                    },
                },
            },
        ]

    async def execute_tool(self, tool_name: str, args: dict[str, Any]) -> str:
        headers = {"Authorization": f"Bearer {self._access_token}"}
        base_url = "https://www.googleapis.com/calendar/v3"

        if tool_name == "calendar_list_events":
            max_results = args.get("max_results", 10)
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{base_url}/calendars/primary/events",
                    headers=headers,
                    params={
                        "maxResults": max_results,
                        "orderBy": "startTime",
                        "singleEvents": True,
                    },
                    timeout=15.0,
                )
                resp.raise_for_status()
                events = resp.json().get("items", [])
                if not events:
                    return "No upcoming events."
                lines = []
                for event in events:
                    start_obj = event.get("start", {})
                    start = start_obj.get("dateTime", start_obj.get("date", ""))
                    lines.append(f"- {event.get('summary', 'No title')} at {start}")
                return "\n".join(lines)

        if tool_name == "calendar_create_event":
            event_body = {
                "summary": args["summary"],
                "start": {"dateTime": args["start"]},
                "end": {"dateTime": args["end"]},
            }
            if "description" in args:
                event_body["description"] = args["description"]
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{base_url}/calendars/primary/events",
                    headers=headers,
                    json=event_body,
                    timeout=15.0,
                )
                resp.raise_for_status()
                return f"Event created: {args['summary']}"

        if tool_name == "calendar_check_availability":
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{base_url}/freeBusy",
                    headers=headers,
                    json={
                        "timeMin": args["start"],
                        "timeMax": args["end"],
                        "items": [{"id": "primary"}],
                    },
                    timeout=15.0,
                )
                resp.raise_for_status()
                busy = resp.json().get("calendars", {}).get("primary", {}).get("busy", [])
                if busy:
                    return f"Time slot is busy ({len(busy)} conflicting events)."
                return "Time slot is available."

        return f"Unknown tool: {tool_name}"

    async def teardown(self) -> None:
        self._access_token = ""
