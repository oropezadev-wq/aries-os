"""Test de integración end-to-end de `POST /message`.

HTTP real vía `TestClient` de FastAPI, contra la app real (`aries.api.app`)
con el `Planner`/`AgentManager` reales — solo el `ILLMProvider` se
sobreescribe con un fake (mismo criterio ya establecido en
`tests/unit/test_planner.py`, para no depender de un servidor Ollama real).
El resto del camino es real: HTTP -> FastAPI -> Planner -> AgentManager ->
FileSystemAgent -> archivo real en disco -> Brain -> respuesta.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import aries.api as api
from aries.agents.manager import AgentManager
from aries.api import app, get_planner
from aries.contracts.llm import ILLMProvider, LLMResponse
from aries.core.events import KernelStartingEvent
from aries.events import AsyncEventBus
from aries.memory.in_memory import InMemoryStore
from aries.planner import Planner


class FakeLLMProvider(ILLMProvider):
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    async def complete(self, prompt: str, temperature: float = 0.7, max_tokens: int | None = None, **kwargs) -> LLMResponse:
        self.prompts.append(prompt)
        if not self._responses:
            return LLMResponse(content="", model="fake", tokens_used=0)
        return LLMResponse(content=self._responses.pop(0), model="fake", tokens_used=0)

    async def embed(self, text: str) -> list[float]:
        return []

    async def is_available(self) -> bool:
        return True

    def get_model_name(self) -> str:
        return "fake"


def _override_planner(responses: list[str], memory: InMemoryStore | None = None) -> Planner:
    """Sobreescribe `get_planner()` con un Planner fijo — la MISMA instancia
    para todas las requests hasta que se limpie el override (fixture
    `_clear_overrides`). Eso es justamente lo que permite probar que el
    contexto de una sesión sobrevive entre dos `POST /message` seguidos: el
    `memory` (y el resto de las dependencias) es el mismo objeto en ambas
    llamadas, ni más ni menos que como lo sería con los singletons reales de
    `api.py` dentro de un mismo proceso."""
    fake_planner = Planner(
        llm_provider=FakeLLMProvider(responses),
        agent_manager=AgentManager(),
        event_bus=AsyncEventBus(),
        memory=memory if memory is not None else InMemoryStore(),
    )
    app.dependency_overrides[get_planner] = lambda: fake_planner
    return fake_planner


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


class TestHealthStillWorks:
    def test_health_endpoint_unaffected(self) -> None:
        client = TestClient(app)

        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestPostMessageEndToEnd:
    def test_writes_a_real_file_end_to_end(self, tmp_path: Path) -> None:
        target = tmp_path / "hola.txt"
        intent = json.dumps(
            {
                "intent": "crear un archivo",
                "confidence": 0.9,
                "steps": [
                    {
                        "agent_name": "filesystem",
                        "action": "write_file",
                        "parameters": {"path": str(target), "content": "hola desde el endpoint"},
                    }
                ],
            }
        )
        _override_planner([intent, "Listo, se creó el archivo."])
        client = TestClient(app)

        response = client.post("/message", json={"user_input": "crea un archivo"})

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["response_text"] == "Listo, se creó el archivo."
        assert body["plan_id"]
        assert body["needs_confirmation"] is False
        assert body["error"] is None
        assert target.read_text(encoding="utf-8") == "hola desde el endpoint"

    def test_destructive_action_requires_confirmation_via_http(self, tmp_path: Path) -> None:
        target = tmp_path / "importante.txt"
        target.write_text("no me borres", encoding="utf-8")
        intent = json.dumps(
            {
                "intent": "borrar archivo",
                "steps": [
                    {"agent_name": "filesystem", "action": "delete_file", "parameters": {"path": str(target)}}
                ],
            }
        )
        _override_planner([intent])
        client = TestClient(app)

        response = client.post("/message", json={"user_input": "borra el archivo importante"})

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert body["needs_confirmation"] is True
        assert target.exists()

    def test_confirmed_true_executes_destructive_action_via_http(self, tmp_path: Path) -> None:
        target = tmp_path / "importante.txt"
        target.write_text("no me borres", encoding="utf-8")
        intent = json.dumps(
            {
                "intent": "borrar archivo",
                "steps": [
                    {"agent_name": "filesystem", "action": "delete_file", "parameters": {"path": str(target)}}
                ],
            }
        )
        _override_planner([intent, "Listo, se borró."])
        client = TestClient(app)

        response = client.post(
            "/message", json={"user_input": "borra el archivo importante", "confirmed": True}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert not target.exists()

    def test_unsupported_request_returns_graceful_failure_not_500(self) -> None:
        intent = json.dumps({"intent": "bailar", "steps": []})
        _override_planner([intent])
        client = TestClient(app)

        response = client.post("/message", json={"user_input": "hacé que baile la compu"})

        assert response.status_code == 200  # nunca un 500 — Planner nunca propaga
        body = response.json()
        assert body["success"] is False
        assert body["error"] is not None

    def test_session_id_is_accepted(self, tmp_path: Path) -> None:
        target = tmp_path / "a.txt"
        intent = json.dumps(
            {
                "intent": "crear archivo",
                "steps": [
                    {"agent_name": "filesystem", "action": "write_file", "parameters": {"path": str(target), "content": "x"}}
                ],
            }
        )
        _override_planner([intent, "listo"])
        client = TestClient(app)

        response = client.post(
            "/message", json={"user_input": "crea un archivo", "session_id": "sesion-abc"}
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_missing_user_input_returns_422(self) -> None:
        client = TestClient(app)

        response = client.post("/message", json={})

        assert response.status_code == 422  # validación de Pydantic en el request body


class TestConversationContextAcrossRequests:
    """Dos `POST /message` seguidos en la misma sesión: HTTP real, sin
    mockear el Planner — confirma que el segundo mensaje tiene acceso al
    contexto (Memory) del primero."""

    def test_second_message_sees_first_as_context(self, tmp_path: Path) -> None:
        target = tmp_path / "notas.txt"
        first_intent = json.dumps(
            {
                "intent": "crear archivo de notas",
                "steps": [
                    {
                        "agent_name": "filesystem",
                        "action": "write_file",
                        "parameters": {"path": str(target), "content": "hola"},
                    }
                ],
            }
        )
        second_intent = json.dumps({"intent": "referencia al archivo anterior", "steps": []})
        fake_planner = _override_planner(
            [first_intent, "Creé notas.txt.", second_intent, "No hay nada más que hacer."]
        )
        client = TestClient(app)

        first_response = client.post(
            "/message", json={"user_input": "creá un archivo de notas", "session_id": "sesion-http-1"}
        )
        second_response = client.post(
            "/message",
            json={"user_input": "¿y el archivo que creaste recién?", "session_id": "sesion-http-1"},
        )

        assert first_response.status_code == 200
        assert first_response.json()["success"] is True
        assert second_response.status_code == 200

        # El segundo prompt al LLM (el de interpretar intención del segundo
        # mensaje) debe incluir el intercambio anterior como contexto.
        second_intent_prompt = fake_planner.llm_provider.prompts[2]
        assert "creá un archivo de notas" in second_intent_prompt
        assert "notas.txt" in second_intent_prompt

    def test_different_sessions_via_http_do_not_share_context(self, tmp_path: Path) -> None:
        target = tmp_path / "secreto.txt"
        first_intent = json.dumps(
            {
                "intent": "crear archivo secreto",
                "steps": [
                    {
                        "agent_name": "filesystem",
                        "action": "write_file",
                        "parameters": {"path": str(target), "content": "shh"},
                    }
                ],
            }
        )
        second_intent = json.dumps({"intent": "algo sin relación", "steps": []})
        fake_planner = _override_planner([first_intent, "Listo.", second_intent, "ok"])
        client = TestClient(app)

        client.post("/message", json={"user_input": "creá secreto.txt", "session_id": "sesion-A"})
        client.post("/message", json={"user_input": "hola", "session_id": "sesion-B"})

        second_intent_prompt = fake_planner.llm_provider.prompts[2]
        assert "secreto.txt" not in second_intent_prompt


def _write_greeter_plugin(plugins_dir: Path, name: str = "greeter") -> None:
    """Escribe un plugin real (`manifest.json` + `plugin.py`) con una sola
    capability funcional (`"greet"`) — mismo patrón que
    `tests/unit/test_kernel_plugins.py`, sin el archivo de log (acá no hace
    falta verificar orden, solo que el resultado llegue por HTTP)."""
    plugin_dir = plugins_dir / name
    plugin_dir.mkdir()

    manifest = {
        "name": name,
        "version": "1.0.0",
        "author": "tests",
        "description": "plugin de prueba para el flujo POST /message",
        "requires": [],
        "entry_point": "plugin:Plugin",
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    code = '''
from __future__ import annotations
from typing import Any, Callable
from aries.contracts.agent import ActionResult, ActionStatus
from aries.contracts.plugin import IPlugin, PluginMetadata


class Plugin(IPlugin):
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="greeter", version="1.0.0", author="tests",
            description="x", requires=[], entry_point="plugin:Plugin",
        )

    async def initialize(self, context: dict[str, Any]) -> bool:
        return True

    async def shutdown(self) -> bool:
        return True

    def register_hooks(self) -> dict[str, Callable[..., Any]]:
        return {}

    def get_capabilities(self) -> list[str]:
        return ["greet"]

    async def execute(self, action: str, **params: Any) -> ActionResult:
        if action != "greet":
            return ActionResult(status=ActionStatus.FAILED, error=f"acción desconocida: {action}")
        return ActionResult(status=ActionStatus.SUCCESS, output=f"hola, {params.get('who', '?')}")

    def is_compatible(self, kernel_version: str) -> bool:
        return True
'''
    (plugin_dir / "plugin.py").write_text(code, encoding="utf-8")


class TestPluginLoadedByKernelIsDispatchableViaAPI:
    """El objetivo real de conectar `plugins/` al Kernel: un plugin que el
    Kernel carga en su `initialize()` (disparado por el evento de startup
    real de `aries.api`, ver `api.py`) debe quedar invocable por un usuario
    de verdad a través de `POST /message` — mismo `_agent_manager` que usa
    el Planner, no una copia aislada."""

    def test_plugin_capability_reachable_via_post_message(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "installed_plugins"
        plugins_dir.mkdir()
        _write_greeter_plugin(plugins_dir)

        # `api.settings`/`api._kernel` son singletons de módulo compartidos
        # por todo el proceso de test — se restaura el valor original para
        # no filtrar estado hacia otros tests que corran después.
        original_plugins_dir = api.settings.plugins_dir
        api.settings.plugins_dir = str(plugins_dir)

        intent = json.dumps(
            {
                "intent": "saludar",
                "steps": [
                    {
                        "agent_name": "greeter",
                        "action": "greet",
                        "parameters": {"who": "Aries"},
                    }
                ],
            }
        )
        fake_planner = Planner(
            llm_provider=FakeLLMProvider([intent, "Listo, saludé."]),
            agent_manager=api._agent_manager,  # el AgentManager real y compartido, no uno nuevo
            event_bus=AsyncEventBus(),
            memory=InMemoryStore(),
        )
        app.dependency_overrides[get_planner] = lambda: fake_planner

        try:
            # `with` dispara el ciclo de vida real de la app (startup ->
            # Kernel.initialize() carga el plugin en `api._agent_manager`
            # -> ... -> shutdown -> Kernel.shutdown() lo descarga), a
            # diferencia de `TestClient(app)` sin `with`, que no lo dispara.
            with TestClient(app) as client:
                assert "greeter" in api._agent_manager.list_agents()

                response = client.post(
                    "/message", json={"user_input": "saludá a Aries de mi parte"}
                )
        finally:
            api.settings.plugins_dir = original_plugins_dir

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["response_text"] == "Listo, saludé."

        # El shutdown real de la app ya corrió (al salir del `with`) y
        # descargó el plugin — no debe quedar registrado para otros tests.
        assert "greeter" not in api._agent_manager.list_agents()


class TestKernelRunBackgroundTaskViaAPI:
    """`kernel.run()` (el bucle de housekeeping de fondo) ahora se lanza
    como tarea de fondo en el startup real de `aries.api` y se espera
    limpio en el shutdown real (ver `startup_event()`/`shutdown_event()`
    en `api.py`) — nada de esto ocurre con `TestClient(app)` sin `with`,
    que no dispara el ciclo de vida de la app (verificado empíricamente en
    la tarea anterior, ver `TestPluginLoadedByKernelIsDispatchableViaAPI`)."""

    @pytest.mark.asyncio
    async def test_run_task_publishes_starting_event_does_housekeeping_and_exits_cleanly(
        self,
    ) -> None:
        # Intervalo corto solo para este test — se restaura en el finally
        # para no filtrar estado hacia otros tests (mismo criterio que
        # `api.settings.plugins_dir` en el test de arriba).
        original_interval = api.settings.kernel_housekeeping_interval_seconds
        api.settings.kernel_housekeeping_interval_seconds = 0.05

        received: list[KernelStartingEvent] = []

        async def on_starting(event: KernelStartingEvent) -> None:
            received.append(event)

        await api._event_bus.subscribe(KernelStartingEvent, on_starting)

        # Item ya vencido en la Memory real y compartida — si el
        # housekeeping corre de verdad (no solo "la task existe"), debería
        # desaparecer solo, sin llamar a `clear_expired()` a mano.
        expired_item = await api._memory.store(
            "dato viejo", "context", expires_at=datetime.now() - timedelta(seconds=1)
        )

        try:
            with TestClient(app) as client:
                client.get("/health")  # confirma que la app ya está arriba

                await asyncio.sleep(0.2)  # al menos un par de ciclos de housekeeping

                assert len(received) == 1
                assert isinstance(received[0], KernelStartingEvent)
                assert await api._memory.retrieve(expired_item.id) is None
        finally:
            api.settings.kernel_housekeeping_interval_seconds = original_interval
            await api._event_bus.unsubscribe(KernelStartingEvent, on_starting)

        # Al salir del `with`, shutdown_event() corrió: kernel.shutdown()
        # señaló el `asyncio.Event` que hace salir a `run()` de su bucle, y
        # luego se hizo `await` (sin cancelar) a la task guardada — acá se
        # confirma que ese `await` realmente esperó a que terminara limpio,
        # sin quedar colgada ni haber sido cancelada a la fuerza.
        assert api._kernel_run_task is not None
        assert api._kernel_run_task.done()
        assert not api._kernel_run_task.cancelled()
        assert api._kernel_run_task.exception() is None
