from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from structlog.stdlib import BoundLogger

from ..contracts.event_bus import Handler, IEventBus
from ..logging import get_logger
from .dispatcher import Dispatcher
from .event import BaseEvent

if TYPE_CHECKING:
    # `EventType` no se importa en tiempo de ejecución para evitar un ciclo
    # con `aries.contracts.event_bus` (ver docs/audits/2026-07-24-diagnostico.md).
    # Es seguro porque este módulo usa `from __future__ import annotations`,
    # así que las anotaciones nunca se evalúan en runtime.
    from ..contracts.event_bus import EventType


class AsyncEventBus(IEventBus):
    """Implementación asincrónica del Event Bus.

    Internamente usa identificadores estables basados en módulo y qualname para
    evitar colisiones entre eventos definidos en distintos módulos o plugins.
    El nombre corto `event_type` se mantiene para compatibilidad con suscripciones
    antiguas.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, set[Handler]] = {}
        self._lock = asyncio.Lock()
        self.logger: BoundLogger = get_logger(self.__class__.__name__)
        self._dispatcher = Dispatcher(self.logger)

    async def publish(self, event: BaseEvent) -> None:
        start = time.perf_counter()
        event_id = event.event_id
        event_type = event.event_type

        async with self._lock:
            handlers_set: set[Handler] = set(self._handlers.get(event_id, set()))
            handlers_set.update(self._handlers.get(event_type, set()))
            handlers = list(handlers_set)

        self.logger.info(
            "Publicando evento",
            event_type=event_type,
            event_id=event_id,
            handler_count=len(handlers),
            payload=event.to_dict(),
        )

        if not handlers:
            self.logger.debug(
                "No hay handlers registrados para el evento",
                event_type=event_type,
                event_id=event_id,
            )
            return

        results = await self._dispatcher.dispatch(event, handlers)
        errors = [error for _, error in results if error is not None]

        duration_ms = int((time.perf_counter() - start) * 1000)
        self.logger.info(
            "Evento publicado",
            event_type=event_type,
            event_id=event_id,
            handler_count=len(handlers),
            error_count=len(errors),
            duration_ms=duration_ms,
        )

    async def subscribe(self, event_type: EventType, handler: Handler) -> None:
        normalized = self._normalize_event_type(event_type)

        async with self._lock:
            self._handlers.setdefault(normalized, set()).add(handler)

        self.logger.debug(
            "Handler suscrito",
            event_type=normalized,
            handler=self._handler_name(handler),
        )

    async def unsubscribe(self, event_type: EventType, handler: Handler) -> None:
        normalized = self._normalize_event_type(event_type)

        async with self._lock:
            handlers = self._handlers.get(normalized)
            if handlers is None or handler not in handlers:
                self.logger.debug(
                    "Handler no encontrado al desuscribir",
                    event_type=normalized,
                    handler=self._handler_name(handler),
                )
                return

            handlers.remove(handler)
            if not handlers:
                self._handlers.pop(normalized, None)

        self.logger.debug(
            "Handler desuscrito",
            event_type=normalized,
            handler=self._handler_name(handler),
        )

    @staticmethod
    def _normalize_event_type(event_type: EventType) -> str:
        if isinstance(event_type, str):
            return event_type
        return f"{event_type.__module__}.{event_type.__qualname__}"

    @staticmethod
    def _handler_name(handler: Handler) -> str:
        return getattr(handler, "__qualname__", repr(handler))
