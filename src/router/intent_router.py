"""Semantic intent router using nomic-embed-text V2 for sub-ms classification."""

from __future__ import annotations

import logging
from typing import Any

from semantic_router import Route  # type: ignore[import-untyped]
from semantic_router.encoders import HuggingFaceEncoder  # type: ignore[import-untyped]
from semantic_router.routers import SemanticRouter  # type: ignore[import-untyped]

from src.models.schemas import IntentCategory, IntentResult

logger = logging.getLogger(__name__)

# ── Route Definitions ──────────────────────────────────────────────────────────

EMAIL_UTTERANCES = [
    "check my email",
    "do I have any new emails",
    "read my inbox",
    "send an email to",
    "reply to that email",
    "any urgent emails",
    "email summary",
    "what did John send me",
    "compose a message",
    "forward this email",
]

CALENDAR_UTTERANCES = [
    "what's on my calendar",
    "schedule a meeting",
    "when is my next meeting",
    "create an event",
    "cancel the meeting",
    "what meetings do I have today",
    "am I free at 3pm",
    "book a room",
    "reschedule the standup",
    "add a reminder",
]

LINEAR_UTTERANCES = [
    "what are my Linear issues",
    "create a ticket",
    "update the issue status",
    "assign this to me",
    "what's in the sprint",
    "show my open tasks",
    "mark this as done",
    "create a bug report",
    "what's the project progress",
    "move this to in progress",
]

FIREFLIES_UTTERANCES = [
    "summarize the last meeting",
    "what were the action items",
    "search meeting transcripts",
    "what did we discuss yesterday",
    "find the meeting about budgets",
    "who attended the standup",
    "key decisions from last week",
    "meeting notes from Monday",
    "what was decided about the launch",
    "list recent meetings",
]

VISION_UTTERANCES = [
    "what do you see",
    "look at this",
    "describe what's in front of you",
    "can you read this",
    "what's on my screen",
    "take a photo",
    "analyze this image",
    "what color is this",
    "identify this object",
    "read the text on this",
]

GENERAL_UTTERANCES = [
    "hello",
    "how are you",
    "tell me a joke",
    "what's the weather",
    "explain this concept",
    "help me think about",
    "what do you think",
    "good morning",
    "thank you",
    "goodbye",
]

ROBOT_UTTERANCES = [
    "look at me",
    "turn around",
    "nod your head",
    "wiggle",
    "look left",
    "look right",
    "look up",
    "show me happy",
    "do a dance",
    "face forward",
]


def build_routes() -> list[Route]:
    """Build semantic routes for all intent categories."""
    return [
        Route(name=IntentCategory.EMAIL.value, utterances=EMAIL_UTTERANCES),
        Route(name=IntentCategory.CALENDAR.value, utterances=CALENDAR_UTTERANCES),
        Route(name=IntentCategory.LINEAR.value, utterances=LINEAR_UTTERANCES),
        Route(name=IntentCategory.FIREFLIES.value, utterances=FIREFLIES_UTTERANCES),
        Route(name=IntentCategory.VISION.value, utterances=VISION_UTTERANCES),
        Route(name=IntentCategory.GENERAL_CHAT.value, utterances=GENERAL_UTTERANCES),
        Route(name=IntentCategory.ROBOT_CONTROL.value, utterances=ROBOT_UTTERANCES),
    ]


class IntentRouter:
    """Routes user utterances to the correct agent via semantic similarity.

    Uses nomic-embed-text V2 loaded locally for sub-millisecond routing.
    Falls back to LLM classification for ambiguous queries.
    """

    def __init__(
        self,
        encoder_model: str = "nomic-ai/nomic-embed-text-v2-moe",
        confidence_threshold: float = 0.3,
    ) -> None:
        self._confidence_threshold = confidence_threshold
        self._encoder_model = encoder_model
        self._router: SemanticRouter | None = None

    async def initialize(self) -> None:
        """Load the encoder and build the semantic router."""
        logger.info("Initializing intent router with %s...", self._encoder_model)

        encoder = HuggingFaceEncoder(name=self._encoder_model)  # type: ignore[no-untyped-call]
        routes = build_routes()
        self._router = SemanticRouter(encoder=encoder, routes=routes)

        logger.info("Intent router ready with %d routes", len(routes))

    def route(self, text: str) -> IntentResult:
        """Route a user utterance to an intent category.

        Args:
            text: The user's spoken/typed input.

        Returns:
            IntentResult with category and confidence.
        """
        if self._router is None:
            msg = "Router not initialized. Call initialize() first."
            raise RuntimeError(msg)

        result: Any = self._router(text)

        if result.name is None or (
            hasattr(result, "similarity_score")
            and result.similarity_score < self._confidence_threshold
        ):
            # Low confidence — return general_chat as fallback
            return IntentResult(
                category=IntentCategory.GENERAL_CHAT,
                confidence=0.0,
                raw_text=text,
                fallback_used=True,
            )

        try:
            category = IntentCategory(result.name)
        except ValueError:
            category = IntentCategory.GENERAL_CHAT

        confidence = getattr(result, "similarity_score", 0.5)
        return IntentResult(
            category=category,
            confidence=float(confidence),
            raw_text=text,
        )
