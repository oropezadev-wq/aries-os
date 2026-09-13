"""Tests de `routines/manager.py` — el estado de reintento
(`RoutineRuntimeState`) es la parte que motivó una revisión completa del
diseño (Routines.spec.md sección 1.1) antes de escribir código: estos
tests existen específicamente para verificar que "el próximo tick
reintenta la MISMA ocurrencia hasta éxito o staleness" es cierto en el
código, no solo en la especificación.

`event_bus` es el `AsyncEventBus` real (en memoria, sin nada que
mockear) — mismo criterio que el resto del proyecto para `IEventBus`.
`message_bus` es un doble en memoria (`FakeMessageBus`): `IMessageBus`
real (`RedisStreamsMessageBus`) tiene su propia suite contra un Redis
real en `test_redis_streams_bus.py`; estos tests son sobre la lógica de
`RoutineManager`, no sobre Redis.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aries.agents.manager import AgentManager
from aries.contracts.agent import ActionResult, ActionStatus, IAgent
from aries.events import AsyncEventBus
from aries.routines.events import RoutineCompletedEvent, RoutineFailedEvent, RoutineTriggeredEvent
from aries.routines.manager import ROUTINES_TOPIC, RoutineManager
from aries.routines.models import AgentAction, ChainedAction, RoutineDefinition, SpeakAction


class FakeAgent(IAgent):
    """Agente controlable: puede fallar a demanda y puede exigir
    confirmación — para ejercitar las dos ramas de `_dispatch_agent`."""

    def __init__(self, name: str = "fake", *, fail: bool = False, confirm: bool = False) -> None:
        self._name = name
        self.fail = fail
        self.confirm = confirm
        self.calls: list[dict[str, object]] = []

    def get_agent_name(self) -> str:
        return self._name

    def get_capabilities(self) -> list[str]:
        return ["do_it"]

    def requires_confirmation(self, action: str, **_: object) -> bool:
        return self.confirm

    async def is_available(self) -> bool:
        return True

    async def execute(self, action: str, **kwargs: object) -> ActionResult:
        self.calls.append(kwargs)
        if self.fail:
            return ActionResult(status=ActionStatus.FAILED, error="fallo simulado")
        return ActionResult(status=ActionStatus.SUCCESS, output="ok")


class FakeMessageBus:
    """Doble en memoria de `IMessageBus` — solo `publish()`, que es lo
    único que usa `RoutineManager`. `fail_times` controla cuántas
    llamadas seguidas fallan con `MessageBusError` antes de empezar a
    aceptar publicaciones (para simular "Redis caído, después vuelve")."""

    def __init__(self, fail_times: int = 0) -> None:
        self.published: list[tuple[str, dict]] = []
        self._fail_times = fail_times

    async def publish(self, topic: str, payload: dict) -> str:
        if self._fail_times > 0:
            self._fail_times -= 1
            from aries.exceptions import MessageBusError

            raise MessageBusError("Redis no disponible (simulado)")
        self.published.append((topic, payload))
        return f"msg-{len(self.published)}"

    def subscribe(self, *args: object, **kwargs: object):  # pragma: no cover - no usado por RoutineManager
        raise NotImplementedError

    async def ack(self, *args: object, **kwargs: object) -> None:  # pragma: no cover
        raise NotImplementedError


def _make_manager(
    *,
    agent: IAgent | None = None,
    message_bus: FakeMessageBus | None = None,
    routines: list[RoutineDefinition] | None = None,
    max_staleness: float = 1800.0,
) -> tuple[RoutineManager, AsyncEventBus, list[object]]:
    agent_manager = AgentManager(agents=[agent] if agent else [])
    event_bus = AsyncEventBus()
    received: list[object] = []

    manager = RoutineManager(
        agent_manager=agent_manager,
        event_bus=event_bus,
        message_bus=message_bus or FakeMessageBus(),
        routines_max_staleness_seconds=max_staleness,
        routines=routines or [],
    )
    return manager, event_bus, received


async def _subscribe_all(event_bus: AsyncEventBus, received: list[object]) -> None:
    async def _collect(event: object) -> None:
        received.append(event)

    for event_type in (RoutineTriggeredEvent, RoutineCompletedEvent, RoutineFailedEvent):
        await event_bus.subscribe(event_type, _collect)


def _cron_routine(routine_id: str, cron: str, action, loaded_at: datetime) -> RoutineDefinition:
    return RoutineDefinition(id=routine_id, action=action, loaded_at=loaded_at, cron=cron)


class TestOnStartup:
    @pytest.mark.asyncio
    async def test_fires_exactly_once(self) -> None:
        now = datetime.now(UTC)
        agent = FakeAgent()
        routine = RoutineDefinition(
            id="r", action=AgentAction(agent_name="fake", action="do_it"), loaded_at=now, on_startup=True
        )
        manager, event_bus, received = _make_manager(agent=agent, routines=[routine])
        await _subscribe_all(event_bus, received)

        await manager.check_due(now)
        await manager.check_due(now + timedelta(seconds=5))
        await manager.check_due(now + timedelta(days=1))

        assert len(agent.calls) == 1


class TestCronRetryState:
    """El núcleo de la revisión: pending_occurrence separa "cuándo le
    toca" de "se confirmó publicada" — sin esto, un fallo a las 7:00 no
    se reintenta hasta mañana."""

    @pytest.mark.asyncio
    async def test_failed_dispatch_is_retried_next_tick_same_occurrence(self) -> None:
        loaded_at = datetime(2026, 1, 2, tzinfo=UTC)
        agent = FakeAgent(fail=True)
        routine = _cron_routine("r", "0 7 * * *", AgentAction(agent_name="fake", action="do_it"), loaded_at)
        manager, event_bus, received = _make_manager(agent=agent, routines=[routine])
        await _subscribe_all(event_bus, received)

        due_time = datetime(2026, 1, 2, 7, 0, 30, tzinfo=UTC)  # 30s después de las 7:00

        await manager.check_due(due_time)
        assert len(agent.calls) == 1  # lo intentó y falló
        state = manager._state["r"]
        assert state.pending_occurrence == datetime(2026, 1, 2, 7, 0, tzinfo=UTC)
        assert state.last_fired_occurrence is None  # NO avanzó pese al intento

        # Reintento en un tick posterior, todavía el mismo día — si el
        # ancla se hubiera actualizado al evaluar (el bug que motivó
        # esta revisión), croniter ya habría saltado al día siguiente acá.
        agent.fail = False
        await manager.check_due(due_time + timedelta(seconds=30))

        assert len(agent.calls) == 2
        assert state.pending_occurrence is None
        assert state.last_fired_occurrence == datetime(2026, 1, 2, 7, 0, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_successful_occurrence_is_not_reevaluated_same_tick_window(self) -> None:
        loaded_at = datetime(2026, 1, 2, tzinfo=UTC)
        agent = FakeAgent()
        routine = _cron_routine("r", "0 7 * * *", AgentAction(agent_name="fake", action="do_it"), loaded_at)
        manager, _event_bus, _received = _make_manager(agent=agent, routines=[routine])

        due_time = datetime(2026, 1, 2, 7, 0, 10, tzinfo=UTC)
        await manager.check_due(due_time)
        await manager.check_due(due_time + timedelta(seconds=10))

        assert len(agent.calls) == 1  # no se reejecuta la misma ocurrencia dos veces

    @pytest.mark.asyncio
    async def test_stale_occurrence_is_discarded_not_retried_forever(self) -> None:
        loaded_at = datetime(2026, 1, 2, tzinfo=UTC)
        agent = FakeAgent(fail=True)
        routine = _cron_routine("r", "0 7 * * *", AgentAction(agent_name="fake", action="do_it"), loaded_at)
        manager, event_bus, received = _make_manager(agent=agent, routines=[routine], max_staleness=60.0)
        await _subscribe_all(event_bus, received)

        due_time = datetime(2026, 1, 2, 7, 0, 0, tzinfo=UTC)
        await manager.check_due(due_time)  # falla, queda pending
        assert len(agent.calls) == 1

        way_later = due_time + timedelta(seconds=120)  # supera max_staleness=60s
        await manager.check_due(way_later)

        assert len(agent.calls) == 1  # NO se reintentó — se descartó en cambio
        state = manager._state["r"]
        assert state.pending_occurrence is None
        assert state.last_fired_occurrence == due_time  # se marca resuelta igual, no reintenta
        assert any(isinstance(event, RoutineFailedEvent) for event in received)


class TestRequiresConfirmation:
    @pytest.mark.asyncio
    async def test_confirmable_action_never_executes_and_resolves_permanently(self) -> None:
        loaded_at = datetime(2026, 1, 2, tzinfo=UTC)
        agent = FakeAgent(confirm=True)
        routine = _cron_routine("r", "0 7 * * *", AgentAction(agent_name="fake", action="do_it"), loaded_at)
        manager, event_bus, received = _make_manager(agent=agent, routines=[routine])
        await _subscribe_all(event_bus, received)

        due_time = datetime(2026, 1, 2, 7, 0, 0, tzinfo=UTC)
        await manager.check_due(due_time)

        assert agent.calls == []  # nunca se despachó
        state = manager._state["r"]
        assert state.pending_occurrence is None  # resuelto, no reintenta
        assert state.last_fired_occurrence == due_time
        assert any(isinstance(event, RoutineFailedEvent) for event in received)

        # Confirmamos que un tick siguiente tampoco reintenta.
        await manager.check_due(due_time + timedelta(seconds=5))
        assert agent.calls == []


class TestSpeakAction:
    @pytest.mark.asyncio
    async def test_publishes_payload_with_occurrence_and_valid_until(self) -> None:
        loaded_at = datetime(2026, 1, 2, tzinfo=UTC)
        bus = FakeMessageBus()
        routine = _cron_routine("buenos-dias", "0 7 * * *", SpeakAction(text="Buenos días"), loaded_at)
        manager, _event_bus, _received = _make_manager(message_bus=bus, routines=[routine], max_staleness=1800.0)

        due_time = datetime(2026, 1, 2, 7, 0, 0, tzinfo=UTC)
        await manager.check_due(due_time)

        assert len(bus.published) == 1
        topic, payload = bus.published[0]
        assert topic == ROUTINES_TOPIC
        assert payload["routine_id"] == "buenos-dias"
        assert payload["text"] == "Buenos días"
        assert payload["occurrence"] == due_time.isoformat()
        assert payload["valid_until"] == (due_time + timedelta(seconds=1800)).isoformat()

    @pytest.mark.asyncio
    async def test_publish_failure_is_retried_next_tick(self) -> None:
        loaded_at = datetime(2026, 1, 2, tzinfo=UTC)
        bus = FakeMessageBus(fail_times=1)  # falla una vez (ej. Redis caído), después anda
        routine = _cron_routine("r", "0 7 * * *", SpeakAction(text="hola"), loaded_at)
        manager, _event_bus, _received = _make_manager(message_bus=bus, routines=[routine])

        due_time = datetime(2026, 1, 2, 7, 0, 0, tzinfo=UTC)
        await manager.check_due(due_time)
        assert bus.published == []  # la primera falló

        await manager.check_due(due_time + timedelta(seconds=30))
        assert len(bus.published) == 1
        assert bus.published[0][1]["occurrence"] == due_time.isoformat()  # misma ocurrencia, no una nueva


class TestChainedAction:
    @pytest.mark.asyncio
    async def test_executes_sub_actions_in_order(self) -> None:
        loaded_at = datetime(2026, 1, 2, tzinfo=UTC)
        agent = FakeAgent()
        bus = FakeMessageBus()
        action = ChainedAction(actions=(AgentAction(agent_name="fake", action="do_it"), SpeakAction(text="listo")))
        routine = _cron_routine("r", "0 7 * * *", action, loaded_at)
        manager, _event_bus, _received = _make_manager(agent=agent, message_bus=bus, routines=[routine])

        await manager.check_due(datetime(2026, 1, 2, 7, 0, 0, tzinfo=UTC))

        assert len(agent.calls) == 1
        assert len(bus.published) == 1
        assert bus.published[0][1]["text"] == "listo"


class TestDisabledRoutine:
    @pytest.mark.asyncio
    async def test_never_evaluated(self) -> None:
        loaded_at = datetime(2026, 1, 2, tzinfo=UTC)
        agent = FakeAgent()
        routine = RoutineDefinition(
            id="r",
            action=AgentAction(agent_name="fake", action="do_it"),
            loaded_at=loaded_at,
            cron="0 7 * * *",
            enabled=False,
        )
        manager, _event_bus, _received = _make_manager(agent=agent, routines=[routine])

        await manager.check_due(datetime(2026, 1, 2, 7, 0, 30, tzinfo=UTC))

        assert agent.calls == []


class TestEventsOnSuccess:
    @pytest.mark.asyncio
    async def test_triggered_then_completed(self) -> None:
        loaded_at = datetime(2026, 1, 2, tzinfo=UTC)
        agent = FakeAgent()
        routine = _cron_routine("r", "0 7 * * *", AgentAction(agent_name="fake", action="do_it"), loaded_at)
        manager, event_bus, received = _make_manager(agent=agent, routines=[routine])
        await _subscribe_all(event_bus, received)

        await manager.check_due(datetime(2026, 1, 2, 7, 0, 0, tzinfo=UTC))

        kinds = [type(event) for event in received]
        assert kinds == [RoutineTriggeredEvent, RoutineCompletedEvent]
