"""Eventos de dominio publicados por `RoutineManager`.

Viven acá, junto a quien los publica — mismo criterio que
`planner/events.py`/`plugins/events.py` (ver ese primero para la
justificación completa). No forman parte del catálogo fijo de 15
eventos de `docs/contracts/IPlugin.md` — son eventos de dominio nuevos,
publicables/suscribibles por cualquier handler del `EventBus` real igual
que los demás (Routines.spec.md sección 7).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..events.event import BaseEvent


@dataclass(frozen=True)
class RoutineTriggeredEvent(BaseEvent):
    """Publicado cuando una rutina se evalúa como vencida y arranca su
    ejecución (antes de saber si tuvo éxito)."""

    routine_id: str = ""


@dataclass(frozen=True)
class RoutineCompletedEvent(BaseEvent):
    """Publicado cuando la acción de una rutina se confirmó completada
    (dispatch()/publish() sin excepción)."""

    routine_id: str = ""


@dataclass(frozen=True)
class RoutineFailedEvent(BaseEvent):
    """Publicado cuando una rutina falla o se descarta (vencida hace
    demasiado, acción confirmable sin humano en el loop, etc.)."""

    routine_id: str = ""
    error: str = ""
