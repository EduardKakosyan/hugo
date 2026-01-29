"""Microsoft Outlook integration via Microsoft Graph API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.integrations.base import Integration

logger = logging.getLogger(__name__)


class OutlookIntegration(Integration):
    name = "outlook"
    description = "Send and read emails, search inbox via Microsoft Outlook"

    def __init__(self) -> None:
        self._client_id = ""
        self._client_secret = ""
        self._tenant_id = ""
        self._access_token = ""

    async def setup(self, config: dict[str, Any]) -> bool:
        self._client_id = config.get("client_id", "")
        self._client_secret = config.get("client_secret", "")
        self._tenant_id = config.get("tenant_id", "")

        if not all([self._client_id, self._client_secret, self._tenant_id]):
            return False

        # Acquire access token via client credentials flow
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/token",
                    data={
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                        "scope": "https://graph.microsoft.com/.default",
                        "grant_type": "client_credentials",
                    },
                    timeout=15.0,
                )
                response.raise_for_status()
                self._access_token = response.json()["access_token"]
                return True
        except Exception as e:
            logger.warning("Outlook auth failed: %s", e)
            return False

    async def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "outlook_read_inbox",
                    "description": "Read recent emails from the user's Outlook inbox",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "count": {
                                "type": "integer",
                                "description": "Number of emails to fetch (max 10)",
                                "default": 5,
                            }
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "outlook_send_email",
                    "description": "Send an email via Outlook",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "to": {"type": "string", "description": "Recipient email address"},
                            "subject": {"type": "string", "description": "Email subject"},
                            "body": {"type": "string", "description": "Email body (plain text)"},
                        },
                        "required": ["to", "subject", "body"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "outlook_search_inbox",
                    "description": "Search emails in the user's Outlook inbox",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                        },
                        "required": ["query"],
                    },
                },
            },
        ]

    async def execute_tool(self, tool_name: str, args: dict[str, Any]) -> str:
        headers = {"Authorization": f"Bearer {self._access_token}"}

        if tool_name == "outlook_read_inbox":
            count = min(args.get("count", 5), 10)
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://graph.microsoft.com/v1.0/me/messages?$top={count}",
                    headers=headers,
                    timeout=15.0,
                )
                resp.raise_for_status()
                messages = resp.json().get("value", [])
                summaries = []
                for msg in messages:
                    from_addr = msg.get("from", {}).get("emailAddress", {})
                    addr = from_addr.get("address", "unknown")
                    summaries.append(
                        f"From: {addr}\n"
                        f"Subject: {msg.get('subject', '')}\n"
                        f"Preview: {msg.get('bodyPreview', '')[:100]}"
                    )
                return "\n---\n".join(summaries) if summaries else "No messages found."

        if tool_name == "outlook_send_email":
            payload = {
                "message": {
                    "subject": args["subject"],
                    "body": {"contentType": "Text", "content": args["body"]},
                    "toRecipients": [{"emailAddress": {"address": args["to"]}}],
                }
            }
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://graph.microsoft.com/v1.0/me/sendMail",
                    headers=headers,
                    json=payload,
                    timeout=15.0,
                )
                resp.raise_for_status()
                return f"Email sent to {args['to']}."

        if tool_name == "outlook_search_inbox":
            query = args["query"]
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://graph.microsoft.com/v1.0/me/messages?$search=\"{query}\"&$top=5",
                    headers=headers,
                    timeout=15.0,
                )
                resp.raise_for_status()
                messages = resp.json().get("value", [])
                summaries = []
                for msg in messages:
                    summaries.append(
                        f"Subject: {msg.get('subject', '')}\n"
                        f"Preview: {msg.get('bodyPreview', '')[:100]}"
                    )
                return "\n---\n".join(summaries) if summaries else "No results found."

        return f"Unknown tool: {tool_name}"

    async def teardown(self) -> None:
        self._access_token = ""
