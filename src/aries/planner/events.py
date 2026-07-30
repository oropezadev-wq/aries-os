"""Eventos de dominio publicados por el Planner.

Viven acá, junto al código que los publica — mismo criterio ya usado en
`plugins/events.py` (cada subsistema define los suyos, en vez de
amontonarlos en `core/events.py`; ver ese módulo para la justificación
completa). Payloads tomados de `docs/audits/2026-07-24-diagnostico.md`
(sección "Propuesta catálogo de eventos").

Con estos 7 eventos, de los 15 que `docs/contracts/IPlugin.md` espera
quedaron reales: los 4 que ya existían (`KernelInitializedEvent`,
`KernelShutdownEvent`, `PluginLoadedEvent`, `PluginUnloadedEvent`) más estos
7 (`INTENT_DETECTED`, `PLAN_CREATED`, `PLAN_EXECUTED`, `ACTION_STARTED`,
`ACTION_COMPLETED`, `ACTION_FAILED`, `ERROR_OCCURRED`) — 11 de 15. **Nota de
alcance:** `plugins/registry.py` (`CONTRACT_EVENTS`) no se actualizó para
reflejar esto — se dejó deliberadamente fuera de esa tarea (que pidió
explícitamente no desviarse a `plugins/`); ver `PROGRESS.md` para el
detalle de ese gap conocido.

`MemoryStoredEvent` (2026-07-26) se agregó acá, no en un futuro
`memory/events.py`, porque **quien lo publica hoy es el Planner, no
`IMemory`** — `InMemoryStore` no recibe una referencia a `IEventBus` en su
constructor (ver `docs/audits/2026-07-24-diagnostico.md`), así que el
Planner llama `memory.store(...)` y publica el evento él mismo, por ahora.
Si en el futuro `memory/` termina publicando sus propios eventos
directamente, esta clase se movería ahí — hoy vive donde vive quien la usa,
no donde "debería" vivir conceptualmente. Con este evento, de los 15 del
contrato ya son reales 12 (quedan `KERNEL_STARTING`, `MEMORY_DELETED` y
`MEMORY_SEARCHED`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..events.event import BaseEvent


@dataclass(frozen=True)
class IntentDetectedEvent(BaseEvent):
    """Publicado cuando el Planner interpreta el texto del usuario y
    determina una intención."""

    intent: str = ""
    confidence: float | None = None
    raw_input: str = ""


@dataclass(frozen=True)
class PlanCreatedEvent(BaseEvent):
    """Publicado cuando el Planner arma la secuencia de pasos para cumplir
    la intención detectada."""

    plan_id: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)
    intent: str = ""


@dataclass(frozen=True)
class PlanExecutedEvent(BaseEvent):
    """Publicado cuando el Planner termina de ejecutar un plan (con éxito o
    abortado por el fallo de un paso — decisión 6 de `Planner.spec.md`)."""

    plan_id: str = ""
    success: bool = False
    results: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class ActionStartedEvent(BaseEvent):
    """Publicado justo antes de invocar `IAgent.execute()`/`ITool.execute()`
    para un paso del plan."""

    actor_type: str = ""
    actor_name: str = ""
    action: str = ""


@dataclass(frozen=True)
class ActionCompletedEvent(BaseEvent):
    """Publicado cuando un paso del plan termina con éxito."""

    actor_type: str = ""
    actor_name: str = ""
    action: str = ""


@dataclass(frozen=True)
class ActionFailedEvent(BaseEvent):
    """Publicado cuando un paso del plan termina en error."""

    actor_type: str = ""
    actor_name: str = ""
    action: str = ""
    error: str = ""


@dataclass(frozen=True)
class ErrorOccurredEvent(BaseEvent):
    """Publicado ante cualquier fallo no recuperable dentro del Planner
    (parseo de intención, capacidad no encontrada, excepción inesperada)."""

    source: str = ""
    error: str = ""
    context: dict[str, Any] | None = None


@dataclass(frozen=True)
class MemoryStoredEvent(BaseEvent):
    """Publicado cuando el Planner guarda un intercambio de conversación en
    `IMemory`. Payload igual al ya especificado en
    `docs/audits/2026-07-24-diagnostico.md` para este evento."""

    memory_id: str = ""
    memory_type: str = ""
