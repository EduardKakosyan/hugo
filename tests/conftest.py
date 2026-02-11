"""Shared test fixtures — mock robot, mock MCP, mock voice."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.robot.controller import ReachyController


@pytest.fixture
def mock_robot() -> ReachyController:
    """A ReachyController in simulation mode."""
    return ReachyController(sim=True)


@pytest.fixture
def connected_robot(mock_robot: ReachyController) -> ReachyController:
    """A connected ReachyController (sim mode)."""
    import asyncio

    asyncio.get_event_loop().run_until_complete(mock_robot.connect())
    return mock_robot


@pytest.fixture
def mock_graph_client() -> MagicMock:
    """Mock Microsoft Graph client."""
    client = MagicMock()
    client.me.messages.get = AsyncMock(return_value=MagicMock(value=[]))
    client.me.send_mail.post = AsyncMock()
    client.me.calendar_view.get = AsyncMock(return_value=MagicMock(value=[]))
    client.me.events.post = AsyncMock()
    return client


@pytest.fixture
def mock_linear_response() -> dict:
    """Sample Linear GraphQL response."""
    return {
        "viewer": {
            "assignedIssues": {
                "nodes": [
                    {
                        "identifier": "ENG-123",
                        "title": "Fix login bug",
                        "state": {"name": "In Progress"},
                        "priority": 2,
                        "assignee": {"name": "Test User"},
                        "description": "The login form crashes on submit.",
                        "url": "https://linear.app/test/issue/ENG-123",
                    }
                ]
            }
        }
    }


@pytest.fixture
def mock_fireflies_response() -> dict:
    """Sample Fireflies GraphQL response."""
    return {
        "transcripts": [
            {
                "id": "tx_123",
                "title": "Sprint Planning",
                "date": "2026-02-10T10:00:00Z",
                "duration": 30,
                "participants": ["Alice", "Bob"],
                "summary": {
                    "overview": "Discussed sprint goals.",
                    "action_items": ["Review PR #42", "Update docs"],
                    "keywords": ["sprint", "planning"],
                },
            }
        ]
    }


@pytest.fixture
def sample_utterances() -> dict[str, list[str]]:
    """Sample utterances for each intent category."""
    return {
        "email": [
            "check my email",
            "any new messages",
            "read my inbox",
        ],
        "calendar": [
            "what's on my calendar today",
            "when is my next meeting",
            "schedule a call",
        ],
        "linear": [
            "show my Linear issues",
            "create a ticket for this bug",
            "what's in the sprint",
        ],
        "fireflies": [
            "summarize the last meeting",
            "what were the action items from yesterday",
        ],
        "vision": [
            "what do you see",
            "describe what's in front of you",
        ],
        "general_chat": [
            "hello",
            "tell me a joke",
            "how are you",
        ],
        "robot_control": [
            "look at me",
            "wiggle",
            "turn around",
        ],
    }
