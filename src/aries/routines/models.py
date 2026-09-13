"""routines/models.py — modelo tipado de rutinas y sus acciones.

Ver `docs/specs/Routines.spec.md` secciones 1-3: no hay `IRoutineManager`
(RoutineManager es un orquestador concreto, como Planner) pero sí un
modelo tipado para la acción que dispara una rutina — union de
dataclasses, no una interfaz con métodos abstractos (no hay una segunda
"forma de ejecutar" que intercambiar, a diferencia de ITTSProvider/
IWakeWordProvider).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class SpeakAction:
    """Hablar `text` por TTS — se publica en `IMessageBus` para que
    `VoicePipeline` lo sintetice/reproduzca (Routines.spec.md sección 4),
    nunca se ejecuta en el proceso de la API."""

    text: str


@dataclass(frozen=True)
class AgentAction:
    """Despachar `action` de `agent_name` vía `AgentManager.dispatch()`,
    en el mismo proceso que `RoutineManager`."""

    agent_name: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChainedAction:
    """Ejecuta cada acción de `actions` en orden. Solo admite
    `SpeakAction`/`AgentAction` (no anidar `ChainedAction` dentro de
    `ChainedAction` — no hay caso real que lo justifique todavía)."""

    actions: tuple[SpeakAction | AgentAction, ...]


RoutineAction = SpeakAction | AgentAction | ChainedAction


@dataclass(frozen=True)
class RoutineDefinition:
    """Definición inmutable de una rutina, cargada desde un archivo en
    `routines_dir` (Routines.spec.md sección 3). `loaded_at` la fija
    `loader.py` al cargar — es el ancla de fallback que usa
    `RoutineManager` cuando `RoutineRuntimeState.last_fired_occurrence`
    todavía es `None` (nunca se disparó desde que el proceso arrancó)."""

    id: str
    action: RoutineAction
    loaded_at: datetime
    cron: str | None = None
    on_startup: bool = False
    enabled: bool = True


@dataclass
class RoutineRuntimeState:
    """Estado mutable en memoria, por rutina — vive en `RoutineManager`,
    separado de `RoutineDefinition` (inmutable). NO se persiste entre
    reinicios del proceso (Routines.spec.md sección 1.1, límite conocido
    y declarado a propósito)."""

    last_fired_occurrence: datetime | None = None
    """La ocurrencia que se ejecutó CON ÉXITO por última vez — el ancla
    real que usa `croniter.get_next()`. Se actualiza ÚNICAMENTE cuando la
    acción se confirma completada (`AgentAction`: `dispatch()` volvió sin
    excepción; `SpeakAction`: `IMessageBus.publish()` devolvió un id).
    NUNCA se actualiza solo por evaluar la rutina como vencida."""

    pending_occurrence: datetime | None = None
    """Si no es `None`: hay una ocurrencia vencida que ya se intentó
    ejecutar y todavía no se confirmó con éxito. Mientras no sea `None`,
    el tick reintenta ESA MISMA ocurrencia, no recalcula una nueva."""

    fired_on_startup: bool = False
    """Para rutinas `on_startup=True`: si ya se disparó una vez desde que
    el proceso arrancó. A diferencia de `last_fired_occurrence` (que
    `croniter` usa para calcular la próxima ocurrencia), `on_startup` no
    tiene "próxima ocurrencia" — es un disparo único por arranque."""
