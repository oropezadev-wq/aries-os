from __future__ import annotations

from ..types import AsyncEventHandler, EventHandler
from .event import BaseEvent
from .event_bus import EventBus

Handler = AsyncEventHandler | EventHandler


class EventSubscriber:
    """Suscriptor que registra handlers en un EventBus.

    El ciclo de vida de un handler es:
    1. Registro con `subscribe`.
    2. Ejecución cada vez que se publica un evento coincidente.
    3. Desregistro con `unsubscribe`.

    Para un Plugin Manager, el plugin debe desuscribir todos sus handlers
    al descargarse para evitar retener referencias en el bus.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    async def subscribe(self, event_type: str | type[BaseEvent], handler: Handler) -> None:
        """Registra un handler para un tipo de evento."""
        await self._event_bus.subscribe(event_type, handler)

    async def unsubscribe(self, event_type: str | type[BaseEvent], handler: Handler) -> None:
        """Quita un handler registrado de un tipo de evento."""
        await self._event_bus.unsubscribe(event_type, handler)
