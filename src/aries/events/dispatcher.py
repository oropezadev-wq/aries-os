from __future__ import annotations

import asyncio
import time

from structlog.stdlib import BoundLogger

from ..types import AsyncEventHandler, EventHandler
from .event import BaseEvent

Handler = AsyncEventHandler | EventHandler


class Dispatcher:
    """Dispatcher responsable de ejecutar handlers sin afectar otros handlers."""

    def __init__(self, logger: BoundLogger) -> None:
        self.logger = logger

    async def dispatch(
        self,
        event: BaseEvent,
        handlers: list[Handler],
    ) -> list[tuple[Handler, Exception | None]]:
        tasks = [self._run_handler(event, handler) for handler in handlers]
        return await asyncio.gather(*tasks)

    async def _run_handler(self, event: BaseEvent, handler: Handler) -> tuple[Handler, Exception | None]:
        handler_name = self._handler_name(handler)
        start = time.perf_counter()
        self.logger.debug(
            "Ejecutando handler de evento",
            handler=handler_name,
            event_type=event.event_type,
        )

        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                await self._run_sync_handler(handler, event)

            duration_ms = int((time.perf_counter() - start) * 1000)
            self.logger.info(
                "Handler completado",
                handler=handler_name,
                event_type=event.event_type,
                duration_ms=duration_ms,
            )
            return handler, None
        except asyncio.CancelledError:
            self.logger.debug(
                "Handler cancelado",
                handler=handler_name,
                event_type=event.event_type,
            )
            raise
        except Exception as error:
            duration_ms = int((time.perf_counter() - start) * 1000)
            self.logger.error(
                "Error en handler de evento",
                handler=handler_name,
                event_type=event.event_type,
                duration_ms=duration_ms,
                error=error,
            )
            return handler, error

    async def _run_sync_handler(self, handler: Handler, event: BaseEvent) -> None:
        loop = asyncio.get_running_loop()
        sync_future = loop.run_in_executor(None, handler, event)

        try:
            await sync_future
        except asyncio.CancelledError:
            self.logger.debug(
                "Cancelación recibida durante handler sincrónico",
                handler=self._handler_name(handler),
                event_type=event.event_type,
            )
            if not sync_future.done():
                try:
                    await asyncio.shield(sync_future)
                except Exception as error:
                    self.logger.error(
                        "Error en handler sincrónico tras cancelación",
                        handler=self._handler_name(handler),
                        event_type=event.event_type,
                        error=error,
                    )
            raise

    @staticmethod
    def _handler_name(handler: Handler) -> str:
        return getattr(handler, "__qualname__", repr(handler))
