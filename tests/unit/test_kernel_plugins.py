"""Pruebas de integración: Kernel real cargando/descargando plugins reales
desde disco en `initialize()`/`shutdown()`.

Nada mockeado salvo `ILLMProvider` (mismo `FakeLLMProvider` ya establecido
en `test_kernel.py`, para no depender de un servidor Ollama real): la
`InMemoryStore`, el `PluginRegistry` y los plugins en sí son reales,
escritos a un directorio temporal y cargados vía `importlib` de verdad —
mismo criterio que `test_plugin_registry.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aries.agents.manager import AgentManager
from aries.config.settings import Settings
from aries.contracts.agent import ActionStatus
from aries.contracts.event_bus import IEventBus
from aries.contracts.llm import ILLMProvider, LLMResponse
from aries.core.kernel import Kernel
from aries.events import BaseEvent
from aries.memory.in_memory import InMemoryStore
from aries.plugins.events import PluginLoadedEvent, PluginUnloadedEvent


class FakeLLMProvider(ILLMProvider):
    async def complete(self, prompt: str, temperature: float = 0.7, max_tokens: int | None = None, **kwargs) -> LLMResponse:
        return LLMResponse(content="", model="fake", tokens_used=0)

    async def embed(self, text: str) -> list[float]:
        return []

    async def is_available(self) -> bool:
        return True

    def get_model_name(self) -> str:
        return "fake"


class FakeEventBus(IEventBus):
    """Bus de eventos fake — mismo criterio que `test_kernel.py`: no hace
    falta un despacho real de eventos para estas pruebas, solo trackear qué
    se publicó."""

    def __init__(self) -> None:
        self.published: list[BaseEvent] = []

    async def publish(self, event: BaseEvent) -> None:
        self.published.append(event)

    async def subscribe(self, event_type, handler) -> None:
        return None

    async def unsubscribe(self, event_type, handler) -> None:
        return None


def _write_plugin(plugins_dir: Path, name: str, log_path: Path, *, valid: bool = True) -> None:
    """Escribe un plugin real (`manifest.json` + `plugin.py`) en
    `plugins_dir / name`. Cada `initialize()`/`shutdown()` real deja una
    línea en `log_path` — así se puede verificar orden de carga/descarga
    real sin necesitar un objeto compartido entre módulos importados por
    separado (cada plugin se importa como un módulo `importlib` distinto)."""
    plugin_dir = plugins_dir / name
    plugin_dir.mkdir()

    manifest = {
        "name": name,
        "version": "1.0.0",
        "author": "tests",
        "description": "plugin de prueba para Kernel + plugins",
        "requires": [],
        "entry_point": "plugin:Plugin",
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    early_action = 'raise RuntimeError("initialize() roto a propósito")' if not valid else "pass"

    code = f'''
from __future__ import annotations
from pathlib import Path
from typing import Any, Callable
from aries.contracts.agent import ActionResult, ActionStatus
from aries.contracts.plugin import IPlugin, PluginMetadata

LOG_PATH = Path(r"{log_path}")


class Plugin(IPlugin):
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="{name}", version="1.0.0", author="tests",
            description="x", requires=[], entry_point="plugin:Plugin",
        )

    async def initialize(self, context: dict[str, Any]) -> bool:
        {early_action}
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write("init:{name}\\n")
        return True

    async def shutdown(self) -> bool:
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write("shutdown:{name}\\n")
        return True

    def register_hooks(self) -> dict[str, Callable[..., Any]]:
        return {{}}

    def get_capabilities(self) -> list[str]:
        return ["greet"]

    async def execute(self, action: str, **params: Any) -> ActionResult:
        if action != "greet":
            return ActionResult(status=ActionStatus.FAILED, error=f"acción desconocida: {{action}}")
        return ActionResult(status=ActionStatus.SUCCESS, output=f"hola, {{params.get('who', '?')}} desde {name}")

    def is_compatible(self, kernel_version: str) -> bool:
        return True
'''
    (plugin_dir / "plugin.py").write_text(code, encoding="utf-8")


def test_default_plugins_dir_setting() -> None:
    assert Settings().plugins_dir == "installed_plugins"


@pytest.mark.asyncio
async def test_kernel_with_missing_plugins_dir_loads_nothing_without_error(tmp_path: Path) -> None:
    settings = Settings(plugins_dir=str(tmp_path / "no_existe"))
    kernel = Kernel(settings, InMemoryStore(), FakeLLMProvider(), FakeEventBus(), AgentManager())

    await kernel.initialize()

    assert kernel.plugin_registry.list_plugins() == {}

    await kernel.shutdown()  # no debe fallar aunque no haya nada que descargar


@pytest.mark.asyncio
async def test_kernel_loads_valid_plugins_and_isolates_broken_one(tmp_path: Path) -> None:
    """Un plugin roto (manifest válido, `initialize()` que lanza una
    excepción) no debe tumbar el Kernel ni bloquear la carga de los
    demás — regla de aislamiento explícita de la tarea."""
    plugins_dir = tmp_path / "installed_plugins"
    plugins_dir.mkdir()
    log_path = tmp_path / "plugin_log.txt"

    _write_plugin(plugins_dir, "a_first_good", log_path, valid=True)
    _write_plugin(plugins_dir, "b_broken", log_path, valid=False)
    _write_plugin(plugins_dir, "c_second_good", log_path, valid=True)

    settings = Settings(plugins_dir=str(plugins_dir))
    kernel = Kernel(settings, InMemoryStore(), FakeLLMProvider(), FakeEventBus(), AgentManager())

    await kernel.initialize()

    loaded = kernel.plugin_registry.list_plugins()
    assert "b_broken" not in loaded
    # Orden de carga = orden alfabético de los directorios candidatos.
    assert list(loaded) == ["a_first_good", "c_second_good"]

    log_lines = log_path.read_text(encoding="utf-8").splitlines()
    assert log_lines == ["init:a_first_good", "init:c_second_good"]


@pytest.mark.asyncio
async def test_kernel_shutdown_unloads_plugins_in_reverse_order(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "installed_plugins"
    plugins_dir.mkdir()
    log_path = tmp_path / "plugin_log.txt"

    _write_plugin(plugins_dir, "a_first_good", log_path, valid=True)
    _write_plugin(plugins_dir, "b_broken", log_path, valid=False)
    _write_plugin(plugins_dir, "c_second_good", log_path, valid=True)

    settings = Settings(plugins_dir=str(plugins_dir))
    kernel = Kernel(settings, InMemoryStore(), FakeLLMProvider(), FakeEventBus(), AgentManager())

    await kernel.initialize()
    await kernel.shutdown()

    log_lines = log_path.read_text(encoding="utf-8").splitlines()
    assert log_lines == [
        "init:a_first_good",
        "init:c_second_good",
        "shutdown:c_second_good",
        "shutdown:a_first_good",
    ]
    assert kernel.plugin_registry.list_plugins() == {}


@pytest.mark.asyncio
async def test_kernel_plugin_lifecycle_publishes_plugin_events(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "installed_plugins"
    plugins_dir.mkdir()
    log_path = tmp_path / "plugin_log.txt"
    _write_plugin(plugins_dir, "solo-plugin", log_path, valid=True)

    settings = Settings(plugins_dir=str(plugins_dir))
    event_bus = FakeEventBus()
    kernel = Kernel(settings, InMemoryStore(), FakeLLMProvider(), event_bus, AgentManager())

    await kernel.initialize()
    assert any(isinstance(event, PluginLoadedEvent) for event in event_bus.published)

    await kernel.shutdown()
    assert any(isinstance(event, PluginUnloadedEvent) for event in event_bus.published)


@pytest.mark.asyncio
async def test_plugin_capability_is_dispatchable_via_agent_manager_like_a_native_agent(
    tmp_path: Path,
) -> None:
    """Paso 4: la capability de un plugin cargado por el Kernel se invoca
    por el mismo camino que un `IAgent` nativo — `AgentManager.dispatch()`
    no tiene ningún `if` especial para plugins, solo ve otro `IAgent` (el
    `PluginAgentAdapter`, ver `plugins/agent_adapter.py`)."""
    plugins_dir = tmp_path / "installed_plugins"
    plugins_dir.mkdir()
    log_path = tmp_path / "plugin_log.txt"
    _write_plugin(plugins_dir, "greeter", log_path, valid=True)

    settings = Settings(plugins_dir=str(plugins_dir))
    kernel = Kernel(settings, InMemoryStore(), FakeLLMProvider(), FakeEventBus(), AgentManager())

    await kernel.initialize()

    # El AgentManager recibido ya trae los 4 agentes nativos por default
    # (mismo comportamiento que el `AgentManager()` real de `api.py`, ver
    # `tests/integration/test_api_message.py` para la prueba de que en
    # producción es literalmente el mismo objeto) — el plugin se suma a esa
    # misma lista, no vive en un registro aparte.
    assert set(kernel.agent_manager.list_agents()) == {
        "filesystem",
        "process",
        "git",
        "database",
        "greeter",
    }

    result = await kernel.agent_manager.dispatch("greeter", "greet", who="Aries")

    assert result.status == ActionStatus.SUCCESS
    assert result.output == "hola, Aries desde greeter"


@pytest.mark.asyncio
async def test_plugin_capability_stops_being_dispatchable_after_kernel_shutdown(
    tmp_path: Path,
) -> None:
    plugins_dir = tmp_path / "installed_plugins"
    plugins_dir.mkdir()
    log_path = tmp_path / "plugin_log.txt"
    _write_plugin(plugins_dir, "greeter", log_path, valid=True)

    settings = Settings(plugins_dir=str(plugins_dir))
    kernel = Kernel(settings, InMemoryStore(), FakeLLMProvider(), FakeEventBus(), AgentManager())

    await kernel.initialize()
    await kernel.shutdown()

    assert "greeter" not in kernel.agent_manager.list_agents()
    result = await kernel.agent_manager.dispatch("greeter", "greet", who="Aries")
    assert result.status == ActionStatus.FAILED
