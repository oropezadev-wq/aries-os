"""Contrato: Bus de Eventos

Define la interfaz del Event Bus sin acoplar a la implementación concreta.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..types import AsyncEventHandler, EventHandler

Handler = AsyncEventHandler | EventHandler


class IEventBus(ABC):
    """Interface para el bus de eventos asincrónico.

    Responsabilidades:
    - Publicar eventos tipados
    - Suscribir handlers a tipos de eventos
    - Desuscribir handlers
    """

    @abstractmethod
    async def publish(self, event: BaseEvent) -> None:
        """Publica un evento en el bus."""
        ...

    @abstractmethod
    async def subscribe(self, event_type: EventType, handler: Handler) -> None:
        """Suscribe un handler a un tipo de evento."""
        ...

    @abstractmethod
    async def unsubscribe(self, event_type: EventType, handler: Handler) -> None:
        """Desuscribe un handler de un tipo de evento."""
        ...


# Import diferido a propósito: `aries.events` importa este módulo (necesita
# `Handler`/`IEventBus`, ya definidos arriba) al cargarse, así que si este
# import estuviera al principio del archivo se produciría un ciclo de import
# (aries.contracts.event_bus -> aries.events -> aries.events.event_bus ->
# aries.contracts.event_bus, incompleto). Ver docs/audits/2026-07-24-diagnostico.md.
from ..events.event import BaseEvent  # noqa: E402

EventType = str | type[BaseEvent]
