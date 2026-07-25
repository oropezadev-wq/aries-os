from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts.event_bus import Handler, IEventBus
from .event import BaseEvent

if TYPE_CHECKING:
    # `EventType` no se importa en tiempo de ejecución para evitar un ciclo
    # con `aries.contracts.event_bus` (ver docs/audits/2026-07-24-diagnostico.md).
    # Es seguro porque este módulo usa `from __future__ import annotations`,
    # así que las anotaciones nunca se evalúan en runtime.
    from ..contracts.event_bus import EventType


class EventSubscriber:
    """Suscriptor que registra handlers en un EventBus.

    El ciclo de vida de un handler es:
    1. Registro con `subscribe`.
    2. Ejecución cada vez que se publica un evento coincidente.
    3. Desregistro con `unsubscribe`.

    Para un Plugin Manager, el plugin debe desuscribir todos sus handlers
    al descargarse para evitar retener referencias en el bus.
    """

    def __init__(self, event_bus: IEventBus) -> None:
        self._event_bus = event_bus

    async def subscribe(self, event_type: EventType, handler: Handler) -> None:
        """Registra un handler para un tipo de evento."""
        await self._event_bus.subscribe(event_type, handler)

    async def unsubscribe(self, event_type: str | type[BaseEvent], handler: Handler) -> None:
        """Quita un handler registrado de un tipo de evento."""
        await self._event_bus.unsubscribe(event_type, handler)
