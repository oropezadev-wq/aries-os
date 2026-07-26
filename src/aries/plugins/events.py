"""Eventos de dominio publicados por el sistema de plugins.

Viven acá, junto al código que los publica, no en `core/events.py` — a
propósito: `docs/audits/2026-07-24-diagnostico.md` (sección "Ubicación de
eventos concretos fuera del paquete `events/`") ya señaló como problema que
`KernelInitializedEvent`/`KernelShutdownEvent` viven en `core/` en vez de
junto a `events/` o al subsistema dueño. No se corrigen esos dos acá (mover
eventos existentes no es parte de esta tarea — la instrucción de esta noche
es no tocar agentes ni Planner, y mover código de `core/` tampoco se pidió),
pero los eventos nuevos que este sistema de plugins necesita sí siguen el
patrón correcto desde el principio: cada subsistema define los suyos.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..events.event import BaseEvent


@dataclass(frozen=True)
class PluginLoadedEvent(BaseEvent):
    """Publicado por `PluginRegistry.load()` cuando un plugin se carga e
    inicializa con éxito."""

    plugin_name: str = ""
    version: str = ""


@dataclass(frozen=True)
class PluginUnloadedEvent(BaseEvent):
    """Publicado por `PluginRegistry.unload()` cuando un plugin se descarga."""

    plugin_name: str = ""
