from __future__ import annotations

from .event import BaseEvent
from .event_bus import EventBus


class EventPublisher:
    """Publicador de eventos que delega en un EventBus."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    async def publish(self, event: BaseEvent) -> None:
        """Publica un evento en el bus."""
        await self._event_bus.publish(event)
