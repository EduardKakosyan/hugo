"""Tests for the async event bus."""

import pytest

from src.events import Event, EventBus


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


class TestEventBus:
    async def test_emit_calls_handler(self, event_bus: EventBus) -> None:
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        event_bus.on("test", handler)
        await event_bus.emit(Event(type="test", data={"key": "value"}))

        assert len(received) == 1
        assert received[0].data["key"] == "value"

    async def test_off_removes_handler(self, event_bus: EventBus) -> None:
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        event_bus.on("test", handler)
        event_bus.off("test", handler)
        await event_bus.emit(Event(type="test"))

        assert len(received) == 0

    async def test_multiple_handlers(self, event_bus: EventBus) -> None:
        results: list[str] = []

        async def handler_a(event: Event) -> None:
            results.append("a")

        async def handler_b(event: Event) -> None:
            results.append("b")

        event_bus.on("test", handler_a)
        event_bus.on("test", handler_b)
        await event_bus.emit(Event(type="test"))

        assert results == ["a", "b"]

    async def test_handler_error_doesnt_break_others(self, event_bus: EventBus) -> None:
        results: list[str] = []

        async def bad_handler(event: Event) -> None:
            raise ValueError("oops")

        async def good_handler(event: Event) -> None:
            results.append("ok")

        event_bus.on("test", bad_handler)
        event_bus.on("test", good_handler)
        await event_bus.emit(Event(type="test"))

        assert results == ["ok"]

    async def test_no_handlers_is_noop(self, event_bus: EventBus) -> None:
        # Should not raise
        await event_bus.emit(Event(type="unhandled"))

    async def test_event_source_preserved(self, event_bus: EventBus) -> None:
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        event_bus.on("test", handler)
        await event_bus.emit(Event(type="test", source="voice"))

        assert received[0].source == "voice"

    async def test_different_event_types_isolated(self, event_bus: EventBus) -> None:
        a_events: list[Event] = []
        b_events: list[Event] = []

        async def handler_a(event: Event) -> None:
            a_events.append(event)

        async def handler_b(event: Event) -> None:
            b_events.append(event)

        event_bus.on("type_a", handler_a)
        event_bus.on("type_b", handler_b)

        await event_bus.emit(Event(type="type_a"))
        await event_bus.emit(Event(type="type_b"))

        assert len(a_events) == 1
        assert len(b_events) == 1
