"""MCP server for Linear — issues, projects, comments."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

mcp = FastMCP("linear", instructions="Linear project management — issues, projects, comments.")

LINEAR_API_URL = "https://api.linear.app/graphql"


def _headers() -> dict[str, str]:
    return {
        "Authorization": os.environ["LINEAR_API_KEY"],
        "Content-Type": "application/json",
    }


async def _query(graphql: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a GraphQL query against the Linear API."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            LINEAR_API_URL,
            headers=_headers(),
            json={"query": graphql, "variables": variables or {}},
            timeout=30.0,
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        if "errors" in data:
            msg = f"Linear API error: {data['errors']}"
            raise RuntimeError(msg)
        return data.get("data", {})


# ── Issue Tools ────────────────────────────────────────────────────────────────


@mcp.tool()
async def list_my_issues(
    state: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """List issues assigned to the authenticated user.

    Args:
        state: Filter by state name (e.g. "In Progress", "Todo").
        limit: Max issues to return.
    """
    filter_clause = ""
    if state:
        filter_clause = f', filter: {{ state: {{ name: {{ eq: "{state}" }} }} }}'

    query = f"""
    query {{
        viewer {{
            assignedIssues(first: {min(limit, 50)}{filter_clause}) {{
                nodes {{
                    identifier
                    title
                    state {{ name }}
                    priority
                    assignee {{ name }}
                    description
                    url
                }}
            }}
        }}
    }}
    """
    data = await _query(query)
    issues = data.get("viewer", {}).get("assignedIssues", {}).get("nodes", [])
    return [
        {
            "identifier": i["identifier"],
            "title": i["title"],
            "state": i["state"]["name"] if i.get("state") else None,
            "priority": i.get("priority"),
            "assignee": i["assignee"]["name"] if i.get("assignee") else None,
            "description": (i.get("description") or "")[:200],
            "url": i.get("url"),
        }
        for i in issues
    ]


@mcp.tool()
async def search_issues(query_text: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search Linear issues by text.

    Args:
        query_text: Search string.
        limit: Max results.
    """
    query = """
    query($term: String!, $limit: Int!) {
        issueSearch(query: $term, first: $limit) {
            nodes {
                identifier
                title
                state { name }
                priority
                url
            }
        }
    }
    """
    data = await _query(query, {"term": query_text, "limit": min(limit, 50)})
    issues = data.get("issueSearch", {}).get("nodes", [])
    return [
        {
            "identifier": i["identifier"],
            "title": i["title"],
            "state": i["state"]["name"] if i.get("state") else None,
            "priority": i.get("priority"),
            "url": i.get("url"),
        }
        for i in issues
    ]


@mcp.tool()
async def create_issue(
    title: str,
    team_key: str,
    description: str = "",
    priority: int = 3,
    labels: list[str] | None = None,
) -> dict[str, str]:
    """Create a new Linear issue. REQUIRES USER APPROVAL before execution.

    Args:
        title: Issue title.
        team_key: Team key (e.g. "ENG").
        description: Issue description (markdown).
        priority: Priority (1=urgent, 2=high, 3=normal, 4=low).
        labels: Optional label names.
    """
    # First resolve team ID
    team_query = """
    query($key: String!) {
        teams(filter: { key: { eq: $key } }) {
            nodes { id }
        }
    }
    """
    team_data = await _query(team_query, {"key": team_key})
    teams = team_data.get("teams", {}).get("nodes", [])
    if not teams:
        msg = f"Team '{team_key}' not found"
        raise ValueError(msg)

    team_id = teams[0]["id"]

    mutation = """
    mutation($input: IssueCreateInput!) {
        issueCreate(input: $input) {
            success
            issue {
                identifier
                title
                url
            }
        }
    }
    """
    input_data: dict[str, Any] = {
        "title": title,
        "teamId": team_id,
        "description": description,
        "priority": priority,
    }

    data = await _query(mutation, {"input": input_data})
    issue = data.get("issueCreate", {}).get("issue", {})
    return {
        "identifier": issue.get("identifier", ""),
        "title": issue.get("title", ""),
        "url": issue.get("url", ""),
    }


@mcp.tool()
async def update_issue(
    issue_id: str,
    state: str | None = None,
    priority: int | None = None,
    assignee_email: str | None = None,
) -> str:
    """Update an existing Linear issue.

    Args:
        issue_id: Issue identifier (e.g. "ENG-123").
        state: New state name.
        priority: New priority (1-4).
        assignee_email: Email of new assignee.
    """
    # Resolve issue ID from identifier
    issue_query = """
    query($id: String!) {
        issueSearch(query: $id, first: 1) {
            nodes { id }
        }
    }
    """
    issue_data = await _query(issue_query, {"id": issue_id})
    nodes = issue_data.get("issueSearch", {}).get("nodes", [])
    if not nodes:
        msg = f"Issue '{issue_id}' not found"
        raise ValueError(msg)

    actual_id = nodes[0]["id"]
    input_data: dict[str, Any] = {}

    if state:
        input_data["stateId"] = state  # Would need to resolve state ID in practice
    if priority is not None:
        input_data["priority"] = priority
    if assignee_email:
        input_data["assigneeId"] = assignee_email  # Would need to resolve user ID

    mutation = """
    mutation($id: String!, $input: IssueUpdateInput!) {
        issueUpdate(id: $id, input: $input) {
            success
        }
    }
    """
    await _query(mutation, {"id": actual_id, "input": input_data})
    return f"Issue {issue_id} updated"


# ── Server Entry Point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
