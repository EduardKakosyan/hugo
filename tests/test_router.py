"""Tests for the semantic intent router."""

from __future__ import annotations

import pytest

from src.models.schemas import IntentCategory
from src.router.intent_router import IntentRouter, build_routes


class TestBuildRoutes:
    """Test route definitions."""

    def test_all_categories_have_routes(self) -> None:
        routes = build_routes()
        route_names = {r.name for r in routes}

        for category in IntentCategory:
            assert category.value in route_names, f"Missing route for {category.value}"

    def test_routes_have_utterances(self) -> None:
        routes = build_routes()
        for route in routes:
            assert len(route.utterances) >= 5, (
                f"Route '{route.name}' has too few utterances ({len(route.utterances)})"
            )


class TestIntentRouter:
    """Test intent routing (requires model loading — integration test)."""

    @pytest.fixture
    def router(self) -> IntentRouter:
        """Create a router instance (not initialized — for unit tests)."""
        return IntentRouter()

    def test_route_without_init_raises(self, router: IntentRouter) -> None:
        with pytest.raises(RuntimeError, match="not initialized"):
            router.route("hello")

    def test_intent_result_structure(self) -> None:
        """Test that IntentResult model works correctly."""
        from src.models.schemas import IntentResult

        result = IntentResult(
            category=IntentCategory.EMAIL,
            confidence=0.95,
            raw_text="check my email",
        )
        assert result.category == IntentCategory.EMAIL
        assert result.confidence == 0.95
        assert result.fallback_used is False

    def test_intent_result_fallback(self) -> None:
        from src.models.schemas import IntentResult

        result = IntentResult(
            category=IntentCategory.GENERAL_CHAT,
            confidence=0.0,
            raw_text="asdfghjkl",
            fallback_used=True,
        )
        assert result.fallback_used is True
        assert result.category == IntentCategory.GENERAL_CHAT
