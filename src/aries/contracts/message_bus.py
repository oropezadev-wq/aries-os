"""Contrato: Bus de mensajes entre procesos (`IMessageBus`)

Ver `docs/contracts/IMessageBus.md` para el contrato completo y
`docs/specs/MessageBus.spec.md` para el razonamiento de diseño —
deliberadamente **no** es el mismo contrato que `IEventBus`
(`contracts/event_bus.py`, in-process, tipado sobre `BaseEvent`): este
es genérico (`topic`/`payload`), cross-proceso, con garantía de entrega
al menos una vez (ack explícito).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BusMessage:
    """Un mensaje entregado por `IMessageBus.subscribe()`."""

    id: str
    topic: str
    payload: dict[str, Any]


class IMessageBus(ABC):
    """Entrega de mensajes confiable entre procesos distintos.

    `subscribe()` no hace ack automático — el llamador debe confirmar
    cada mensaje explícitamente con `ack()` después de procesarlo con
    éxito (docs/contracts/IMessageBus.md, sección "Cuándo se hace ack").
    """

    @abstractmethod
    async def publish(self, topic: str, payload: dict[str, Any]) -> str:
        """Publica `payload` en `topic`. Devuelve el id asignado por el bus.

        Raises:
            MessageBusError: el bus no está disponible. Nunca se
                reintenta internamente — ver `docs/specs/MessageBus.spec.md`
                sección 3.
        """
        ...

    @abstractmethod
    def subscribe(self, topic: str, group: str, consumer: str) -> AsyncIterator[BusMessage]:
        """Itera mensajes de `topic` para el grupo de consumo `group`,
        identificándose como `consumer` (debe ser estable entre
        reinicios — ver `docs/contracts/IMessageBus.md`).

        De larga duración — quien lo consume debe correrlo como una task
        de fondo, nunca bloquear el loop principal esperándolo.
        """
        ...

    @abstractmethod
    async def ack(self, topic: str, group: str, message_id: str) -> None:
        """Confirma que `message_id` se procesó. No borra el mensaje del
        topic — ack y retención son mecanismos independientes."""
        ...
