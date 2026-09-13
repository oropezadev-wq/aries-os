"""routines/loader.py — lee y valida las rutinas de `routines_dir`, un
archivo JSON por rutina (mismo criterio que `plugins/manifest.py`: leer
una definición no debe requerir ejecutar código). Ver
`docs/specs/Routines.spec.md` secciones 1-3.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from croniter import croniter

from ..logging import get_logger
from .cron import ScheduleError, schedule_to_cron
from .models import AgentAction, ChainedAction, RoutineAction, RoutineDefinition, SpeakAction

_ID_PATTERN = re.compile(r"^[a-z0-9_-]+$")
logger = get_logger("routines.loader")


class RoutineError(Exception):
    """Archivo de rutina inválido, ilegible o mal formado.

    Nunca debe llegar sin capturar a quien orquesta la carga
    (`RoutineManager`/`Kernel.initialize()`) — normaliza cualquier
    problema de lectura/parseo/validación en un único tipo, en vez de
    dejar propagar `OSError`/`json.JSONDecodeError`/`KeyError` tal cual."""


def _parse_speak_action(data: dict[str, Any]) -> SpeakAction:
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        raise RoutineError(f"'action.text' debe ser un string no vacío: {text!r}")
    return SpeakAction(text=text)


def _parse_agent_action(data: dict[str, Any]) -> AgentAction:
    agent_name = data.get("agent_name")
    action_name = data.get("action")
    if not isinstance(agent_name, str) or not agent_name.strip():
        raise RoutineError(f"'action.agent_name' debe ser un string no vacío: {agent_name!r}")
    if not isinstance(action_name, str) or not action_name.strip():
        raise RoutineError(f"'action.action' debe ser un string no vacío: {action_name!r}")
    params = data.get("params", {})
    if not isinstance(params, dict):
        raise RoutineError(f"'action.params' debe ser un objeto JSON: {params!r}")
    return AgentAction(agent_name=agent_name, action=action_name, params=dict(params))


def _parse_chained_action(data: dict[str, Any], *, allow_chained: bool) -> ChainedAction:
    if not allow_chained:
        raise RoutineError("'chained' no puede anidar otra 'chained' — solo 'speak'/'agent' dentro de una cadena")
    raw_actions = data.get("actions")
    if not isinstance(raw_actions, list) or not raw_actions:
        raise RoutineError(f"'action.actions' debe ser una lista no vacía: {raw_actions!r}")
    parsed = tuple(_parse_action(item, allow_chained=False) for item in raw_actions)
    return ChainedAction(actions=parsed)  # type: ignore[arg-type]


_ActionParser = Callable[[dict[str, Any], bool], RoutineAction]
_ACTION_PARSERS: dict[str, _ActionParser] = {
    "speak": lambda data, allow_chained: _parse_speak_action(data),
    "agent": lambda data, allow_chained: _parse_agent_action(data),
    "chained": lambda data, allow_chained: _parse_chained_action(data, allow_chained=allow_chained),
}


def _parse_action(data: Any, *, allow_chained: bool = True) -> RoutineAction:
    if not isinstance(data, dict):
        raise RoutineError(f"'action' debe ser un objeto JSON: {data!r}")

    action_type = data.get("type")
    parser = _ACTION_PARSERS.get(action_type) if isinstance(action_type, str) else None
    if parser is None:
        raise RoutineError(f"'action.type' desconocido (esperaba 'speak'/'agent'/'chained'): {action_type!r}")
    return parser(data, allow_chained)


def _resolve_cron(data: dict[str, Any]) -> tuple[str | None, bool]:
    """Devuelve `(cron, on_startup)` — exactamente uno de los dos queda
    seteado (Routines.spec.md sección 1)."""
    on_startup = bool(data.get("on_startup", False))
    has_cron = "cron" in data
    has_schedule = "schedule" in data

    if on_startup:
        if has_cron or has_schedule:
            raise RoutineError("'on_startup' no puede combinarse con 'cron'/'schedule' — son mutuamente excluyentes")
        return None, True

    if has_cron and has_schedule:
        raise RoutineError("'cron' y 'schedule' son mutuamente excluyentes — usar uno de los dos")

    if has_cron:
        cron = data["cron"]
        if not isinstance(cron, str) or not cron.strip():
            raise RoutineError(f"'cron' debe ser un string no vacío: {cron!r}")
    elif has_schedule:
        schedule = data["schedule"]
        if not isinstance(schedule, dict):
            raise RoutineError(f"'schedule' debe ser un objeto JSON: {schedule!r}")
        try:
            cron = schedule_to_cron(schedule)
        except ScheduleError as error:
            raise RoutineError(str(error)) from error
    else:
        raise RoutineError("La rutina debe declarar exactamente uno de 'cron', 'schedule' u 'on_startup'")

    if not croniter.is_valid(cron):
        raise RoutineError(f"Expresión cron inválida: {cron!r}")

    return cron, False


def parse_routine(path: str | Path, *, loaded_at: datetime | None = None) -> RoutineDefinition:
    """Lee y valida un único archivo de rutina en `path`. Levanta
    `RoutineError` con un mensaje claro ante cualquier problema — nunca
    deja escapar la excepción original."""
    routine_path = Path(path)
    if not routine_path.exists():
        raise RoutineError(f"No existe el archivo de rutina: {routine_path}")
    if not routine_path.is_file():
        raise RoutineError(f"La ruta de la rutina no es un archivo: {routine_path}")

    try:
        raw_text = routine_path.read_text(encoding="utf-8")
    except OSError as error:
        raise RoutineError(f"No se pudo leer la rutina {routine_path}: {error}") from error

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as error:
        raise RoutineError(f"JSON inválido en la rutina {routine_path}: {error}") from error

    if not isinstance(data, dict):
        raise RoutineError(f"La rutina debe ser un objeto JSON, no {type(data).__name__}: {routine_path}")

    routine_id = data.get("id")
    if not isinstance(routine_id, str) or not _ID_PATTERN.match(routine_id):
        raise RoutineError(
            f"'id' debe ser minúsculas y sin espacios (solo [a-z0-9_-]): {routine_id!r} en {routine_path}"
        )

    cron, on_startup = _resolve_cron(data)
    action = _parse_action(data.get("action"))

    enabled = data.get("enabled", True)
    if not isinstance(enabled, bool):
        raise RoutineError(f"'enabled' debe ser booleano: {enabled!r} en {routine_path}")

    return RoutineDefinition(
        id=routine_id,
        action=action,
        loaded_at=loaded_at or datetime.now(UTC),
        cron=cron,
        on_startup=on_startup,
        enabled=enabled,
    )


def load_routines(routines_dir: str | Path) -> list[RoutineDefinition]:
    """Carga todas las rutinas válidas de `routines_dir` (un `.json` por
    rutina). Si el directorio no existe, devuelve una lista vacía — no es
    un error, es el estado esperado antes de definir la primera rutina
    (mismo criterio que `Kernel._load_plugins()` con `plugins_dir`
    inexistente). Una rutina inválida individual se loguea y se saltea —
    nunca bloquea la carga de las demás (mismo criterio de aislamiento
    que `Kernel._load_plugins()` con plugins rotos)."""
    directory = Path(routines_dir)
    if not directory.is_dir():
        return []

    loaded_at = datetime.now(UTC)
    routines: list[RoutineDefinition] = []
    for routine_file in sorted(directory.glob("*.json")):
        try:
            routines.append(parse_routine(routine_file, loaded_at=loaded_at))
        except RoutineError as error:
            logger.warning("Rutina inválida, se saltea", routine_file=str(routine_file), error=str(error))
    return routines
