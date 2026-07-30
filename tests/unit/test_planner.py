"""Pruebas para Planner.

`AgentManager` es siempre real (los 4 `IAgent` concretos reales, operando
sobre archivos/git/sqlite reales en `tmp_path`) — nada mockeado ahí.
`InMemoryStore` (Memory) también es siempre real. El único doble es
`FakeLLMProvider`, mismo criterio ya establecido en
`tests/conftest.py`/`tests/unit/test_kernel.py` para no depender de un
servidor Ollama real corriendo durante los tests.
"""

from __future__ import annotations

import json
import subprocess
import sqlite3
import sys
from pathlib import Path

import pytest

from aries.agents.manager import AgentManager
from aries.contracts.agent import ActionStatus
from aries.contracts.llm import ILLMProvider, LLMResponse
from aries.events import AsyncEventBus
from aries.memory.in_memory import InMemoryStore
from aries.planner import (
    ActionCompletedEvent,
    ActionFailedEvent,
    ActionStartedEvent,
    ErrorOccurredEvent,
    IntentDetectedEvent,
    MemoryStoredEvent,
    PlanCreatedEvent,
    PlanExecutedEvent,
    Planner,
)


class FakeLLMProvider(ILLMProvider):
    """Devuelve las respuestas de `responses` en orden, una por llamada a
    `complete()`. Si se agotan, devuelve contenido vacío."""

    def __init__(self, responses: list[str] | None = None, raises: bool = False) -> None:
        self._responses = list(responses or [])
        self.raises = raises
        self.prompts: list[str] = []

    async def complete(self, prompt: str, temperature: float = 0.7, max_tokens: int | None = None, **kwargs) -> LLMResponse:
        self.prompts.append(prompt)
        if self.raises:
            raise RuntimeError("LLM no disponible")
        if not self._responses:
            return LLMResponse(content="", model="fake", tokens_used=0)
        return LLMResponse(content=self._responses.pop(0), model="fake", tokens_used=0)

    async def embed(self, text: str) -> list[float]:
        return []

    async def is_available(self) -> bool:
        return True

    def get_model_name(self) -> str:
        return "fake"


def _intent(steps: list[dict], intent: str = "hacer algo", confidence: float | None = 0.9) -> str:
    return json.dumps({"intent": intent, "confidence": confidence, "steps": steps})


class EventCollector:
    """`asyncio.iscoroutinefunction()` no reconoce un `__call__` async de
    instancia (solo funciones/métodos "de verdad") — `Dispatcher` lo
    trataría como handler síncrono y lo correría en un executor sin
    esperar la corrutina, así que nunca se ejecutaría de verdad. Por eso
    acá se suscribe el método `record` (bound method), no la instancia."""

    def __init__(self) -> None:
        self.events: list[object] = []

    async def record(self, event: object) -> None:
        self.events.append(event)

    @property
    def types(self) -> list[str]:
        return [type(e).__name__ for e in self.events]


async def _subscribe_all(bus: AsyncEventBus, collector: EventCollector) -> None:
    for cls in [
        IntentDetectedEvent,
        PlanCreatedEvent,
        ActionStartedEvent,
        ActionCompletedEvent,
        ActionFailedEvent,
        PlanExecutedEvent,
        ErrorOccurredEvent,
        MemoryStoredEvent,
    ]:
        await bus.subscribe(cls, collector.record)


@pytest.fixture(name="agent_manager")
def fixture_agent_manager() -> AgentManager:
    return AgentManager()


@pytest.fixture(name="memory")
def fixture_memory() -> InMemoryStore:
    return InMemoryStore()


class TestHandleBasicValidation:
    @pytest.mark.asyncio
    async def test_empty_user_input_fails_gracefully(
        self, agent_manager: AgentManager, memory: InMemoryStore
    ) -> None:
        planner = Planner(FakeLLMProvider(), agent_manager, AsyncEventBus(), memory)

        result = await planner.handle("   ")

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_llm_exception_during_parse_fails_gracefully(
        self, agent_manager: AgentManager, memory: InMemoryStore
    ) -> None:
        planner = Planner(FakeLLMProvider(raises=True), agent_manager, AsyncEventBus(), memory)

        result = await planner.handle("hace algo")

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_invalid_json_both_attempts_fails_gracefully_and_publishes_error(
        self, agent_manager: AgentManager, memory: InMemoryStore
    ) -> None:
        bus = AsyncEventBus()
        collector = EventCollector()
        await _subscribe_all(bus, collector)
        llm = FakeLLMProvider(["no es json", "tampoco esto"])
        planner = Planner(llm, agent_manager, bus, memory)

        result = await planner.handle("hace algo")

        assert result.success is False
        assert len(llm.prompts) == 2  # intento + 1 reintento, ninguno más
        assert "ErrorOccurredEvent" in collector.types

    @pytest.mark.asyncio
    async def test_invalid_json_then_valid_json_succeeds_via_retry(
        self, agent_manager: AgentManager, memory: InMemoryStore, tmp_path: Path
    ) -> None:
        target = tmp_path / "a.txt"
        valid = _intent([{"agent_name": "filesystem", "action": "write_file", "parameters": {"path": str(target), "content": "x"}}])
        llm = FakeLLMProvider(["esto no es json", valid, "listo"])
        planner = Planner(llm, agent_manager, AsyncEventBus(), memory)

        result = await planner.handle("crea un archivo")

        assert result.success is True
        assert len(llm.prompts) == 3  # 1 fallido + 1 ok (parse) + 1 (brain)
        assert target.read_text(encoding="utf-8") == "x"

    @pytest.mark.asyncio
    async def test_no_matching_capability_fails_gracefully(
        self, agent_manager: AgentManager, memory: InMemoryStore
    ) -> None:
        bus = AsyncEventBus()
        collector = EventCollector()
        await _subscribe_all(bus, collector)
        llm = FakeLLMProvider([_intent([], intent="bailar")])
        planner = Planner(llm, agent_manager, bus, memory)

        result = await planner.handle("hace que baile la compu")

        assert result.success is False
        assert "bailar" in result.error
        assert collector.types == ["IntentDetectedEvent", "ErrorOccurredEvent", "MemoryStoredEvent"]

    @pytest.mark.asyncio
    async def test_unknown_agent_name_fails_gracefully(
        self, agent_manager: AgentManager, memory: InMemoryStore
    ) -> None:
        llm = FakeLLMProvider([_intent([{"agent_name": "no_existe", "action": "x", "parameters": {}}])])
        planner = Planner(llm, agent_manager, AsyncEventBus(), memory)

        result = await planner.handle("algo")

        assert result.success is False
        assert "no_existe" in result.error


class TestEndToEndFileSystem:
    @pytest.mark.asyncio
    async def test_write_file_success_full_event_sequence(
        self, agent_manager: AgentManager, memory: InMemoryStore, tmp_path: Path
    ) -> None:
        target = tmp_path / "hola.txt"
        bus = AsyncEventBus()
        collector = EventCollector()
        await _subscribe_all(bus, collector)
        llm = FakeLLMProvider(
            [_intent([{"agent_name": "filesystem", "action": "write_file", "parameters": {"path": str(target), "content": "hola"}}]),
             "Listo, se creó el archivo."]
        )
        planner = Planner(llm, agent_manager, bus, memory)

        result = await planner.handle("crea un archivo con hola")

        assert result.success is True
        assert result.response_text == "Listo, se creó el archivo."
        assert target.read_text(encoding="utf-8") == "hola"
        assert len(result.steps) == 1
        assert result.steps[0].status == ActionStatus.SUCCESS
        assert collector.types == [
            "IntentDetectedEvent",
            "PlanCreatedEvent",
            "ActionStartedEvent",
            "ActionCompletedEvent",
            "PlanExecutedEvent",
            "MemoryStoredEvent",
        ]

    @pytest.mark.asyncio
    async def test_session_id_propagates_to_event_metadata(
        self, agent_manager: AgentManager, memory: InMemoryStore, tmp_path: Path
    ) -> None:
        target = tmp_path / "a.txt"
        bus = AsyncEventBus()
        collector = EventCollector()
        await _subscribe_all(bus, collector)
        llm = FakeLLMProvider(
            [_intent([{"agent_name": "filesystem", "action": "write_file", "parameters": {"path": str(target), "content": "x"}}]), "ok"]
        )
        planner = Planner(llm, agent_manager, bus, memory)

        await planner.handle("crea un archivo", session_id="sesion-123")

        assert all(e.metadata.get("session_id") == "sesion-123" for e in collector.events)

    @pytest.mark.asyncio
    async def test_action_failure_publishes_action_failed_and_plan_executed_false(
        self, agent_manager: AgentManager, memory: InMemoryStore, tmp_path: Path
    ) -> None:
        missing = tmp_path / "no_existe.txt"
        bus = AsyncEventBus()
        collector = EventCollector()
        await _subscribe_all(bus, collector)
        llm = FakeLLMProvider(
            [_intent([{"agent_name": "filesystem", "action": "read_file", "parameters": {"path": str(missing)}}]),
             "No se pudo leer el archivo."]
        )
        planner = Planner(llm, agent_manager, bus, memory)

        result = await planner.handle("lee el archivo")

        assert result.success is False
        assert result.steps[0].status == ActionStatus.FAILED
        assert collector.types == [
            "IntentDetectedEvent",
            "PlanCreatedEvent",
            "ActionStartedEvent",
            "ActionFailedEvent",
            "PlanExecutedEvent",
            "MemoryStoredEvent",
        ]


class TestConfirmation:
    @pytest.mark.asyncio
    async def test_destructive_action_without_confirmed_is_blocked(
        self, agent_manager: AgentManager, memory: InMemoryStore, tmp_path: Path
    ) -> None:
        target = tmp_path / "importante.txt"
        target.write_text("no me borres", encoding="utf-8")
        llm = FakeLLMProvider([_intent([{"agent_name": "filesystem", "action": "delete_file", "parameters": {"path": str(target)}}])])
        planner = Planner(llm, agent_manager, AsyncEventBus(), memory)

        result = await planner.handle("borra el archivo importante")

        assert result.success is False
        assert result.needs_confirmation is True
        assert target.exists()

    @pytest.mark.asyncio
    async def test_needs_confirmation_is_not_stored_in_memory(
        self, agent_manager: AgentManager, memory: InMemoryStore, tmp_path: Path
    ) -> None:
        target = tmp_path / "importante.txt"
        target.write_text("no me borres", encoding="utf-8")
        llm = FakeLLMProvider([_intent([{"agent_name": "filesystem", "action": "delete_file", "parameters": {"path": str(target)}}])])
        planner = Planner(llm, agent_manager, AsyncEventBus(), memory)

        await planner.handle("borra el archivo importante", session_id="s1")

        assert await memory.get_by_type("conversation") == []

    @pytest.mark.asyncio
    async def test_destructive_action_with_confirmed_executes(
        self, agent_manager: AgentManager, memory: InMemoryStore, tmp_path: Path
    ) -> None:
        target = tmp_path / "importante.txt"
        target.write_text("no me borres", encoding="utf-8")
        llm = FakeLLMProvider(
            [_intent([{"agent_name": "filesystem", "action": "delete_file", "parameters": {"path": str(target)}}]), "Listo, se borró."]
        )
        planner = Planner(llm, agent_manager, AsyncEventBus(), memory)

        result = await planner.handle("borra el archivo importante", confirmed=True)

        assert result.success is True
        assert not target.exists()

    @pytest.mark.asyncio
    async def test_git_reset_hard_requires_confirmation_with_mode_kwarg(
        self, agent_manager: AgentManager, memory: InMemoryStore, tmp_path: Path
    ) -> None:
        # GitAgent.requires_confirmation acepta mode= como kwarg de extensión
        # — confirma que el Planner lo reenvía correctamente.
        subprocess.run(["git", "init", "-q", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.local"], cwd=tmp_path, check=True)
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "c1"], cwd=tmp_path, check=True)

        llm = FakeLLMProvider(
            [_intent([{"agent_name": "git", "action": "reset", "parameters": {"mode": "hard", "repo_path": str(tmp_path)}}])]
        )
        planner = Planner(llm, agent_manager, AsyncEventBus(), memory)

        result = await planner.handle("resetea fuerte el repo")

        assert result.needs_confirmation is True

    @pytest.mark.asyncio
    async def test_filesystem_agent_accepts_extra_kwargs_without_raising(
        self, agent_manager: AgentManager, memory: InMemoryStore, tmp_path: Path
    ) -> None:
        # FileSystemAgent.requires_confirmation ahora tiene **kwargs
        # catch-all (igual que los otros 3 agentes) — el Planner le pasa
        # `parameters` completo sin filtrar, esto confirma que no revienta.
        target = tmp_path / "x.txt"
        llm = FakeLLMProvider(
            [_intent([{"agent_name": "filesystem", "action": "write_file", "parameters": {"path": str(target), "content": "hola", "overwrite": True}}]), "ok"]
        )
        planner = Planner(llm, agent_manager, AsyncEventBus(), memory)

        result = await planner.handle("crea un archivo")

        assert result.success is True  # no debe reventar con TypeError


class TestMultiStepPlan:
    @pytest.mark.asyncio
    async def test_multi_step_plan_all_succeed(
        self, agent_manager: AgentManager, memory: InMemoryStore, tmp_path: Path
    ) -> None:
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        llm = FakeLLMProvider(
            [
                _intent(
                    [
                        {"agent_name": "filesystem", "action": "write_file", "parameters": {"path": str(a), "content": "1"}},
                        {"agent_name": "filesystem", "action": "write_file", "parameters": {"path": str(b), "content": "2"}},
                    ]
                ),
                "Listo, ambos archivos creados.",
            ]
        )
        planner = Planner(llm, agent_manager, AsyncEventBus(), memory)

        result = await planner.handle("crea dos archivos")

        assert result.success is True
        assert len(result.steps) == 2
        assert a.read_text(encoding="utf-8") == "1"
        assert b.read_text(encoding="utf-8") == "2"

    @pytest.mark.asyncio
    async def test_multi_step_plan_aborts_on_first_failure_second_step_never_runs(
        self, agent_manager: AgentManager, memory: InMemoryStore, tmp_path: Path
    ) -> None:
        missing = tmp_path / "no_existe.txt"
        b = tmp_path / "b.txt"
        bus = AsyncEventBus()
        collector = EventCollector()
        await _subscribe_all(bus, collector)
        llm = FakeLLMProvider(
            [
                _intent(
                    [
                        {"agent_name": "filesystem", "action": "read_file", "parameters": {"path": str(missing)}},
                        {"agent_name": "filesystem", "action": "write_file", "parameters": {"path": str(b), "content": "no debería crearse"}},
                    ]
                ),
                "Falló el primer paso.",
            ]
        )
        planner = Planner(llm, agent_manager, bus, memory)

        result = await planner.handle("hace dos cosas")

        assert result.success is False
        assert len(result.steps) == 1  # el segundo paso nunca corrió
        assert not b.exists()  # confirma que write_file nunca se ejecutó
        # Solo un ActionStartedEvent (el del paso que falló), no dos.
        assert collector.types.count("ActionStartedEvent") == 1
        assert collector.types.count("ActionFailedEvent") == 1
        assert collector.types.count("ActionCompletedEvent") == 0


class TestEndToEndOtherAgents:
    @pytest.mark.asyncio
    async def test_process_agent_run_command(
        self, agent_manager: AgentManager, memory: InMemoryStore
    ) -> None:
        command = f'"{sys.executable}" -c "print(6*7)"'
        llm = FakeLLMProvider(
            [_intent([{"agent_name": "process", "action": "run_command", "parameters": {"command": command}}]), "El resultado es 42."]
        )
        planner = Planner(llm, agent_manager, AsyncEventBus(), memory)

        result = await planner.handle("cuánto es 6 por 7")

        assert result.success is True
        assert result.steps[0].output.strip() == "42"

    @pytest.mark.asyncio
    async def test_database_agent_list_tables(
        self, agent_manager: AgentManager, memory: InMemoryStore, tmp_path: Path
    ) -> None:
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE notas (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()

        llm = FakeLLMProvider(
            [_intent([{"agent_name": "database", "action": "list_tables", "parameters": {"db_path": str(db_path)}}]), "Hay una tabla: notas."]
        )
        planner = Planner(llm, agent_manager, AsyncEventBus(), memory)

        result = await planner.handle("qué tablas hay")

        assert result.success is True
        assert "notas" in result.steps[0].data["tables"]

    @pytest.mark.asyncio
    async def test_git_status_real_repo(
        self, agent_manager: AgentManager, memory: InMemoryStore, tmp_path: Path
    ) -> None:
        subprocess.run(["git", "init", "-q", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.local"], cwd=tmp_path, check=True)

        llm = FakeLLMProvider(
            [_intent([{"agent_name": "git", "action": "status", "parameters": {"repo_path": str(tmp_path)}}]), "El repo está limpio."]
        )
        planner = Planner(llm, agent_manager, AsyncEventBus(), memory)

        result = await planner.handle("cómo está el repo")

        assert result.success is True
        assert result.steps[0].data["clean"] is True


class TestMemoryIntegration:
    """Conexión IMemory <-> Planner: guardar cada intercambio y recuperar
    contexto reciente de la misma sesión antes de interpretar el próximo
    pedido."""

    @pytest.mark.asyncio
    async def test_exchange_is_stored_with_session_id_in_metadata(
        self, agent_manager: AgentManager, memory: InMemoryStore, tmp_path: Path
    ) -> None:
        target = tmp_path / "a.txt"
        llm = FakeLLMProvider(
            [_intent([{"agent_name": "filesystem", "action": "write_file", "parameters": {"path": str(target), "content": "x"}}]), "Listo."]
        )
        planner = Planner(llm, agent_manager, AsyncEventBus(), memory)

        await planner.handle("crea un archivo", session_id="sesion-abc")

        items = await memory.get_by_type("conversation")
        assert len(items) == 1
        assert items[0].metadata["session_id"] == "sesion-abc"
        assert items[0].metadata["user_input"] == "crea un archivo"
        assert items[0].metadata["response_text"] == "Listo."
        assert "crea un archivo" in items[0].content
        assert "Listo." in items[0].content

    @pytest.mark.asyncio
    async def test_exchange_without_session_id_is_still_stored(
        self, agent_manager: AgentManager, memory: InMemoryStore, tmp_path: Path
    ) -> None:
        target = tmp_path / "a.txt"
        llm = FakeLLMProvider(
            [_intent([{"agent_name": "filesystem", "action": "write_file", "parameters": {"path": str(target), "content": "x"}}]), "Listo."]
        )
        planner = Planner(llm, agent_manager, AsyncEventBus(), memory)

        await planner.handle("crea un archivo")

        items = await memory.get_by_type("conversation")
        assert len(items) == 1
        assert items[0].metadata["session_id"] is None

    @pytest.mark.asyncio
    async def test_failed_exchange_stores_error_as_response(
        self, agent_manager: AgentManager, memory: InMemoryStore
    ) -> None:
        llm = FakeLLMProvider([_intent([], intent="bailar")])
        planner = Planner(llm, agent_manager, AsyncEventBus(), memory)

        await planner.handle("hace que baile la compu")

        items = await memory.get_by_type("conversation")
        assert len(items) == 1
        assert items[0].metadata["success"] is False
        assert items[0].metadata["response_text"] is None
        assert "bailar" in items[0].content

    @pytest.mark.asyncio
    async def test_publishes_memory_stored_event(
        self, agent_manager: AgentManager, memory: InMemoryStore, tmp_path: Path
    ) -> None:
        target = tmp_path / "a.txt"
        bus = AsyncEventBus()
        collector = EventCollector()
        await _subscribe_all(bus, collector)
        llm = FakeLLMProvider(
            [_intent([{"agent_name": "filesystem", "action": "write_file", "parameters": {"path": str(target), "content": "x"}}]), "Listo."]
        )
        planner = Planner(llm, agent_manager, bus, memory)

        await planner.handle("crea un archivo")

        memory_events = [e for e in collector.events if type(e).__name__ == "MemoryStoredEvent"]
        assert len(memory_events) == 1
        stored = await memory.get_by_type("conversation")
        assert memory_events[0].memory_id == stored[0].id
        assert memory_events[0].memory_type == "conversation"

    @pytest.mark.asyncio
    async def test_second_call_in_same_session_receives_first_as_context(
        self, agent_manager: AgentManager, memory: InMemoryStore, tmp_path: Path
    ) -> None:
        target = tmp_path / "a.txt"
        llm = FakeLLMProvider(
            [
                _intent([{"agent_name": "filesystem", "action": "write_file", "parameters": {"path": str(target), "content": "x"}}]),
                "Creé el archivo a.txt.",
            ]
        )
        planner = Planner(llm, agent_manager, AsyncEventBus(), memory)
        await planner.handle("crea un archivo llamado a.txt", session_id="sesion-1")

        # Segunda llamada: un LLM fresco (mismo objeto Planner) — lo único
        # que puede "saber" del primer intercambio es lo que el Planner le
        # inyecte como contexto en el prompt.
        llm2 = FakeLLMProvider([_intent([], intent="referencia al archivo anterior")])
        planner2 = Planner(llm2, agent_manager, AsyncEventBus(), memory)
        await planner2.handle("¿y el archivo que creaste recién?", session_id="sesion-1")

        assert len(llm2.prompts) >= 1
        assert "a.txt" in llm2.prompts[0]
        assert "crea un archivo llamado a.txt" in llm2.prompts[0]

    @pytest.mark.asyncio
    async def test_different_sessions_do_not_share_context(
        self, agent_manager: AgentManager, memory: InMemoryStore, tmp_path: Path
    ) -> None:
        target = tmp_path / "secreto.txt"
        llm = FakeLLMProvider(
            [_intent([{"agent_name": "filesystem", "action": "write_file", "parameters": {"path": str(target), "content": "x"}}]), "Listo."]
        )
        planner = Planner(llm, agent_manager, AsyncEventBus(), memory)
        await planner.handle("crea secreto.txt", session_id="sesion-A")

        llm2 = FakeLLMProvider([_intent([], intent="algo")])
        planner2 = Planner(llm2, agent_manager, AsyncEventBus(), memory)
        await planner2.handle("hola", session_id="sesion-B")

        assert "secreto.txt" not in llm2.prompts[0]

    @pytest.mark.asyncio
    async def test_memory_failure_does_not_break_handle(
        self, agent_manager: AgentManager, tmp_path: Path
    ) -> None:
        class BrokenMemory(InMemoryStore):
            async def store(self, *args, **kwargs):
                raise RuntimeError("disco lleno")

            async def get_by_type(self, *args, **kwargs):
                raise RuntimeError("disco lleno")

        target = tmp_path / "a.txt"
        llm = FakeLLMProvider(
            [_intent([{"agent_name": "filesystem", "action": "write_file", "parameters": {"path": str(target), "content": "x"}}]), "Listo."]
        )
        planner = Planner(llm, agent_manager, AsyncEventBus(), BrokenMemory())

        result = await planner.handle("crea un archivo", session_id="s1")

        assert result.success is True  # la falla de memoria no debe romper el pedido
