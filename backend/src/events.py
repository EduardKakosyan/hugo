"""Lightweight async event bus for cross-modal coordination."""

import logging
from collections import defaultdict
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("hugo.events")

EventHandler = Callable[["Event"], Coroutine[Any, Any, None]]

# Event type constants
TRANSCRIPT_READY = "transcript:ready"
RESPONSE_COMPLETE = "response:complete"
VOICE_SPEAK = "voice:speak"
VISION_RESULT = "vision:result"
SESSION_RESET = "session:reset"


@dataclass
class Event:
    """An event that flows through the system."""

    type: str
    data: dict[str, Any] = field(default_factory=dict)
    source: str = ""


class EventBus:
    """Async pub/sub event bus for decoupled component communication."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def on(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe a handler to an event type."""
        self._handlers[event_type].append(handler)
        logger.debug("Registered handler for '%s': %s", event_type, handler.__name__)

    def off(self, event_type: str, handler: EventHandler) -> None:
        """Unsubscribe a handler from an event type."""
        self._handlers[event_type] = [h for h in self._handlers[event_type] if h is not handler]

    async def emit(self, event: Event) -> None:
        """Emit an event to all registered handlers."""
        handlers = self._handlers.get(event.type, [])
        if not handlers:
            logger.debug("No handlers for event '%s'", event.type)
            return
        logger.debug("Emitting '%s' to %d handlers", event.type, len(handlers))
        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Handler %s failed for event '%s'",
                    handler.__name__,
                    event.type,
                )


# Global event bus singleton
bus = EventBus()
