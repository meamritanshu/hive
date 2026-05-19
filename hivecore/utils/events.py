"""Internal event bus for decoupled component communication."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)


class EventBus:
    """Simple async event bus for internal component communication.

    Allows components to communicate without direct dependencies
    using a publish/subscribe pattern.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[..., Coroutine]]] = {}

    def subscribe(self, event: str, handler: Callable[..., Coroutine]) -> None:
        """Subscribe a handler to an event.

        Args:
            event: Event name.
            handler: Async function to call when event is emitted.
        """
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(handler)

    def unsubscribe(self, event: str, handler: Callable[..., Coroutine]) -> None:
        """Unsubscribe a handler from an event."""
        if event in self._handlers:
            self._handlers[event] = [h for h in self._handlers[event] if h != handler]

    async def emit(self, event: str, **kwargs: Any) -> None:
        """Emit an event, calling all subscribed handlers.

        Args:
            event: Event name.
            **kwargs: Event data to pass to handlers.
        """
        handlers = self._handlers.get(event, [])
        for handler in handlers:
            try:
                await handler(**kwargs)
            except Exception as e:
                logger.error("Event handler error (%s): %s", event, e)

    def clear(self) -> None:
        """Remove all subscriptions."""
        self._handlers.clear()


# Global event bus instance
event_bus = EventBus()
