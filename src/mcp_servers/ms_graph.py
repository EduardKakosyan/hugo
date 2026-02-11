"""MCP server for Microsoft Graph API — email, calendar, Teams, OneDrive."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

mcp = FastMCP("ms-graph", instructions="Microsoft Graph API for email, calendar, and files.")

# ── Graph Client Setup ─────────────────────────────────────────────────────────


def _get_graph_client() -> Any:
    """Get an authenticated Microsoft Graph client."""
    from azure.identity import ClientSecretCredential  # type: ignore[import-untyped]
    from msgraph import GraphServiceClient  # type: ignore[import-untyped]

    credential = ClientSecretCredential(
        tenant_id=os.environ["AZURE_TENANT_ID"],
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_secret=os.environ["AZURE_CLIENT_SECRET"],
    )
    scopes = ["https://graph.microsoft.com/.default"]
    return GraphServiceClient(credentials=credential, scopes=scopes)


# ── Email Tools ────────────────────────────────────────────────────────────────


@mcp.tool()
async def read_emails(
    folder: str = "inbox",
    count: int = 10,
    unread_only: bool = False,
) -> list[dict[str, Any]]:
    """Read recent emails from a mailbox folder.

    Args:
        folder: Mail folder (inbox, sentitems, drafts).
        count: Number of emails to fetch (max 50).
        unread_only: Only return unread emails.
    """
    client = _get_graph_client()
    count = min(count, 50)

    query_params: dict[str, Any] = {
        "$top": count,
        "$orderby": "receivedDateTime desc",
        "$select": "subject,from,receivedDateTime,bodyPreview,isRead,importance",
    }
    if unread_only:
        query_params["$filter"] = "isRead eq false"

    messages = await client.me.mail_folders.by_mail_folder_id(folder).messages.get(
        query_params=query_params
    )

    results: list[dict[str, Any]] = []
    if messages and messages.value:
        for msg in messages.value:
            results.append(
                {
                    "subject": msg.subject,
                    "from": msg.from_.email_address.address if msg.from_ else "unknown",
                    "received": str(msg.received_date_time),
                    "preview": msg.body_preview[:200] if msg.body_preview else "",
                    "is_read": msg.is_read,
                    "importance": msg.importance,
                    "id": msg.id,
                }
            )

    return results


@mcp.tool()
async def send_email(
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
) -> str:
    """Send an email. REQUIRES USER APPROVAL before execution.

    Args:
        to: List of recipient email addresses.
        subject: Email subject line.
        body: Email body (HTML supported).
        cc: Optional CC recipients.
    """
    client = _get_graph_client()
    from msgraph.generated.models import (  # type: ignore[import-untyped]
        BodyType,
        EmailAddress,
        ItemBody,
        Message,
        Recipient,
        SendMailPostRequestBody,
    )

    recipients = [Recipient(email_address=EmailAddress(address=addr)) for addr in to]
    cc_recipients = [Recipient(email_address=EmailAddress(address=addr)) for addr in (cc or [])]

    message = Message(
        subject=subject,
        body=ItemBody(content_type=BodyType.Html, content=body),
        to_recipients=recipients,
        cc_recipients=cc_recipients,
    )

    request_body = SendMailPostRequestBody(message=message, save_to_sent_items=True)
    await client.me.send_mail.post(body=request_body)

    return f"Email sent to {', '.join(to)}: {subject}"


@mcp.tool()
async def search_emails(query: str, count: int = 10) -> list[dict[str, Any]]:
    """Search emails by keyword.

    Args:
        query: Search query (searches subject, body, sender).
        count: Number of results to return.
    """
    client = _get_graph_client()
    count = min(count, 50)

    query_params: dict[str, Any] = {
        "$search": f'"{query}"',
        "$top": count,
        "$select": "subject,from,receivedDateTime,bodyPreview",
    }

    messages = await client.me.messages.get(query_params=query_params)

    results: list[dict[str, Any]] = []
    if messages and messages.value:
        for msg in messages.value:
            results.append(
                {
                    "subject": msg.subject,
                    "from": msg.from_.email_address.address if msg.from_ else "unknown",
                    "received": str(msg.received_date_time),
                    "preview": msg.body_preview[:200] if msg.body_preview else "",
                }
            )
    return results


# ── Calendar Tools ─────────────────────────────────────────────────────────────


@mcp.tool()
async def list_calendar_events(
    days_ahead: int = 1,
    count: int = 20,
) -> list[dict[str, Any]]:
    """List upcoming calendar events.

    Args:
        days_ahead: Number of days to look ahead (1-30).
        count: Maximum events to return.
    """
    client = _get_graph_client()
    now = datetime.utcnow()
    end = now + timedelta(days=min(days_ahead, 30))

    query_params: dict[str, Any] = {
        "startDateTime": now.isoformat() + "Z",
        "endDateTime": end.isoformat() + "Z",
        "$top": min(count, 50),
        "$orderby": "start/dateTime",
        "$select": "subject,start,end,location,attendees,isOnlineMeeting,onlineMeetingUrl",
    }

    events = await client.me.calendar_view.get(query_params=query_params)

    results: list[dict[str, Any]] = []
    if events and events.value:
        for evt in events.value:
            attendee_list = []
            if evt.attendees:
                attendee_list = [a.email_address.address for a in evt.attendees if a.email_address]

            results.append(
                {
                    "title": evt.subject,
                    "start": str(evt.start.date_time) if evt.start else "",
                    "end": str(evt.end.date_time) if evt.end else "",
                    "location": evt.location.display_name if evt.location else None,
                    "attendees": attendee_list,
                    "is_online": evt.is_online_meeting,
                    "meeting_url": evt.online_meeting_url,
                }
            )
    return results


@mcp.tool()
async def create_calendar_event(
    title: str,
    start: str,
    end: str,
    attendees: list[str] | None = None,
    location: str | None = None,
    body: str | None = None,
) -> str:
    """Create a calendar event. REQUIRES USER APPROVAL before execution.

    Args:
        title: Event title.
        start: Start time (ISO 8601 format).
        end: End time (ISO 8601 format).
        attendees: List of attendee email addresses.
        location: Event location.
        body: Event description.
    """
    client = _get_graph_client()
    from msgraph.generated.models import (  # type: ignore[import-untyped]
        Attendee,
        BodyType,
        DateTimeTimeZone,
        EmailAddress,
        Event,
        ItemBody,
        Location,
    )

    event = Event(
        subject=title,
        start=DateTimeTimeZone(date_time=start, time_zone="UTC"),
        end=DateTimeTimeZone(date_time=end, time_zone="UTC"),
    )

    if location:
        event.location = Location(display_name=location)
    if body:
        event.body = ItemBody(content_type=BodyType.Text, content=body)
    if attendees:
        event.attendees = [
            Attendee(email_address=EmailAddress(address=addr)) for addr in attendees
        ]

    created = await client.me.events.post(body=event)
    return f"Event created: {title} (ID: {created.id if created else 'unknown'})"


@mcp.tool()
async def search_files(query: str, count: int = 10) -> list[dict[str, Any]]:
    """Search OneDrive/SharePoint files.

    Args:
        query: Search query.
        count: Number of results.
    """
    client = _get_graph_client()

    query_params: dict[str, Any] = {
        "$top": min(count, 25),
    }

    results_resp = await client.me.drive.search_with_q(q=query).get(query_params=query_params)

    results: list[dict[str, Any]] = []
    if results_resp and results_resp.value:
        for item in results_resp.value:
            results.append(
                {
                    "name": item.name,
                    "web_url": item.web_url,
                    "size": item.size,
                    "last_modified": str(item.last_modified_date_time),
                }
            )
    return results


# ── Server Entry Point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
