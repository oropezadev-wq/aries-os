"""routines/manager.py — `RoutineManager`: evalúa qué rutinas están
vencidas y las ejecuta. Orquestador concreto, sin contrato propio
(Routines.spec.md sección 2 — mismo criterio que `Planner`).

El estado de reintento (`RoutineRuntimeState`) y el algoritmo de
`check_due()` están descritos en detalle en Routines.spec.md sección
1.1 — este módulo es la implementación real de ese diseño, no un
resumen aparte.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from croniter import croniter
from structlog.stdlib import BoundLogger

from ..contracts.agent import ActionStatus
from ..contracts.event_bus import IEventBus
from ..contracts.message_bus import IMessageBus
from ..logging import get_logger
from .events import RoutineCompletedEvent, RoutineFailedEvent, RoutineTriggeredEvent
from .models import (
    AgentAction,
    ChainedAction,
    RoutineAction,
    RoutineDefinition,
    RoutineRuntimeState,
    SpeakAction,
)

if TYPE_CHECKING:
    from ..agents.manager import AgentManager

ROUTINES_TOPIC = "routines.due"


class _ConfirmationRequiredError(Exception):
    """Control de flujo interno: una `AgentAction` de la rutina pide
    confirmación (`IAgent.requires_confirmation() == True`) — no hay
    humano en el loop para confirmarla (Routines.spec.md sección 6). La
    rutina se trata como resuelta (no se reintenta), no como un fallo
    transitorio."""


class RoutineManager:
    """Evalúa `RoutineDefinition`s vencidas (vía `croniter`) y las
    ejecuta — `AgentAction` en el mismo proceso vía `AgentManager`,
    `SpeakAction` publicada en `IMessageBus` para que `VoicePipeline` la
    hable (Routines.spec.md sección 4)."""

    def __init__(
        self,
        agent_manager: AgentManager,
        event_bus: IEventBus,
        message_bus: IMessageBus,
        routines_max_staleness_seconds: float,
        routines: list[RoutineDefinition] | None = None,
    ) -> None:
        self.agent_manager = agent_manager
        self.event_bus = event_bus
        self.message_bus = message_bus
        self.routines_max_staleness_seconds = routines_max_staleness_seconds
        self.logger: BoundLogger = get_logger(self.__class__.__name__)
        self._routines: dict[str, RoutineDefinition] = {}
        self._state: dict[str, RoutineRuntimeState] = {}
        self.load_routines(routines or [])

    def load_routines(self, routines: list[RoutineDefinition]) -> None:
        """Reemplaza el conjunto de rutinas conocidas — el estado de
        reintento de una rutina que ya existía (mismo `id`) se conserva;
        una rutina nueva arranca con estado limpio."""
        self._routines = {routine.id: routine for routine in routines}
        self._state = {
            routine_id: self._state.get(routine_id, RoutineRuntimeState()) for routine_id in self._routines
        }

    def list_routines(self) -> list[RoutineDefinition]:
        return list(self._routines.values())

    # ------------------------------------------------------------------
    # Ciclo de evaluación — llamado desde Kernel.run() en cada tick
    # ------------------------------------------------------------------

    async def check_due(self, now: datetime | None = None) -> None:
        """Evalúa todas las rutinas habilitadas; ejecuta (o reintenta)
        las que están vencidas. Nunca propaga excepciones — mismo
        criterio que `IAgent.execute()`/`PluginRegistry.load()` en el
        resto del proyecto: un fallo de una rutina no debe tumbar el
        tick de `Kernel.run()` ni afectar a las demás rutinas."""
        current_time = now or datetime.now(UTC)
        for routine in list(self._routines.values()):
            if not routine.enabled:
                continue
            try:
                await self._check_one(routine, current_time)
            except Exception as error:  # red de seguridad final, no debe pasar en uso normal
                self.logger.exception(
                    "Error inesperado evaluando una rutina, se descarta este tick", routine_id=routine.id, error=str(error)
                )

    async def _check_one(self, routine: RoutineDefinition, now: datetime) -> None:
        state = self._state[routine.id]

        if routine.on_startup and state.fired_on_startup:
            return

        if state.pending_occurrence is not None:
            occurrence = state.pending_occurrence
        elif routine.on_startup:
            occurrence = routine.loaded_at
            state.pending_occurrence = occurrence
        else:
            assert routine.cron is not None  # garantizado por loader.py
            anchor = state.last_fired_occurrence or routine.loaded_at
            occurrence = croniter(routine.cron, anchor).get_next(datetime)
            if occurrence > now:
                return
            state.pending_occurrence = occurrence

        staleness_seconds = (now - occurrence).total_seconds()
        if staleness_seconds > self.routines_max_staleness_seconds:
            await self._emit(
                RoutineFailedEvent(routine_id=routine.id, error=f"Vencida hace {staleness_seconds:.0f}s, descartada")
            )
            self.logger.warning("Rutina descartada por vencida", routine_id=routine.id, staleness_seconds=staleness_seconds)
            self._resolve(routine, state, occurrence)
            return

        if await self._try_execute(routine, occurrence):
            self._resolve(routine, state, occurrence)
        # si no tuvo éxito, pending_occurrence sigue seteado — el próximo
        # tick de Kernel.run() reintenta esta MISMA ocurrencia.

    def _resolve(self, routine: RoutineDefinition, state: RoutineRuntimeState, occurrence: datetime) -> None:
        state.pending_occurrence = None
        if routine.on_startup:
            state.fired_on_startup = True
        else:
            state.last_fired_occurrence = occurrence

    # ------------------------------------------------------------------
    # Ejecución de una rutina puntual
    # ------------------------------------------------------------------

    async def _try_execute(self, routine: RoutineDefinition, occurrence: datetime) -> bool:
        """Devuelve `True` si la rutina quedó resuelta (con éxito, o con
        un fallo permanente que no vale la pena reintentar — ej.
        confirmación requerida sin humano en el loop) y `False` si hay
        que reintentar en el próximo tick (fallo transitorio: Redis
        caído, error de red al despachar un agente, etc.)."""
        await self._emit(RoutineTriggeredEvent(routine_id=routine.id))
        try:
            await self._execute_action(routine.action, routine, occurrence)
        except _ConfirmationRequiredError as error:
            await self._emit(RoutineFailedEvent(routine_id=routine.id, error=str(error)))
            self.logger.warning("Rutina descartada: requiere confirmación, sin humano en el loop", routine_id=routine.id, error=str(error))
            return True
        except Exception as error:
            self.logger.warning("Fallo al ejecutar rutina, se reintenta en el próximo tick", routine_id=routine.id, error=str(error))
            return False
        else:
            await self._emit(RoutineCompletedEvent(routine_id=routine.id))
            return True

    async def _execute_action(self, action: RoutineAction, routine: RoutineDefinition, occurrence: datetime) -> None:
        if isinstance(action, SpeakAction):
            await self._publish_speak(action, routine, occurrence)
        elif isinstance(action, AgentAction):
            await self._dispatch_agent(action)
        elif isinstance(action, ChainedAction):
            # Nota: si un paso intermedio de la cadena falla, un reintento
            # vuelve a correr la cadena DESDE EL PRINCIPIO — los pasos ya
            # exitosos se repiten. Mismo criterio de "preferir duplicar
            # antes que perder" ya aceptado para SpeakAction
            # (MessageBus.spec.md sección 4); no se trackea progreso
            # parcial dentro de una cadena en v1.
            for sub_action in action.actions:
                await self._execute_action(sub_action, routine, occurrence)
        else:
            raise TypeError(f"RoutineAction desconocida: {type(action)!r}")

    async def _dispatch_agent(self, action: AgentAction) -> None:
        agent = self.agent_manager.get_agent(action.agent_name)
        if agent is not None and agent.requires_confirmation(action.action, **action.params):
            raise _ConfirmationRequiredError(
                f"'{action.agent_name}.{action.action}' requiere confirmación — no soportado en rutinas"
            )

        result = await self.agent_manager.dispatch(action.agent_name, action.action, **action.params)
        if result.status != ActionStatus.SUCCESS:
            # Fallo "genérico" de dispatch (agente/acción desconocidos, o
            # el agente falló de verdad) — se trata como transitorio por
            # simplicidad (se reintenta hasta éxito o hasta vencer por
            # staleness); no se distingue "esto nunca va a andar" de "esto
            # falló una vez" porque ActionResult no lo distingue.
            raise RuntimeError(result.error or f"Fallo desconocido despachando {action.agent_name}.{action.action}")

    async def _publish_speak(self, action: SpeakAction, routine: RoutineDefinition, occurrence: datetime) -> None:
        valid_until = occurrence + timedelta(seconds=self.routines_max_staleness_seconds)
        await self.message_bus.publish(
            ROUTINES_TOPIC,
            {
                "routine_id": routine.id,
                "occurrence": occurrence.isoformat(),
                "valid_until": valid_until.isoformat(),
                "text": action.text,
            },
        )

    async def _emit(self, event: object) -> None:
        try:
            await self.event_bus.publish(event)  # type: ignore[arg-type]
        except Exception as error:  # nunca debe romper la ejecución de la rutina
            self.logger.warning("No se pudo publicar evento de rutina", error=str(error))
