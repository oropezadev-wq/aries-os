"""Pruebas de integración para PluginRegistry.

Nada mockeado: `AsyncEventBus` real, el plugin de ejemplo real cargado
desde `tests/fixtures/example_plugin/` vía `importlib` de verdad, eventos
reales publicados y capturados por el hook real del plugin.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aries.core.events import KernelInitializedEvent
from aries.events import AsyncEventBus
from aries.plugins.registry import CONTRACT_EVENTS, PluginRegistry

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "example_plugin"


def _write_plugin(tmp_path: Path, manifest: dict, module_code: str) -> Path:
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "plugin.py").write_text(module_code, encoding="utf-8")
    return tmp_path


def _broken_plugin_manifest(name: str, entry_point: str = "plugin:Clase", requires: list[str] | None = None) -> dict:
    return {
        "name": name,
        "version": "1.0.0",
        "author": "x",
        "description": "x",
        "requires": requires or [],
        "entry_point": entry_point,
    }


@pytest.fixture(name="event_bus")
def fixture_event_bus() -> AsyncEventBus:
    return AsyncEventBus()


@pytest.fixture(name="registry")
def fixture_registry(event_bus: AsyncEventBus) -> PluginRegistry:
    return PluginRegistry(event_bus)


class TestContractEventsMap:
    def test_all_15_contract_events_are_documented(self) -> None:
        # docs/contracts/IPlugin.md lista exactamente estos 15 nombres.
        expected = {
            "KERNEL_STARTING",
            "KERNEL_READY",
            "KERNEL_SHUTDOWN",
            "INTENT_DETECTED",
            "PLAN_CREATED",
            "PLAN_EXECUTED",
            "ACTION_STARTED",
            "ACTION_COMPLETED",
            "ACTION_FAILED",
            "MEMORY_STORED",
            "MEMORY_DELETED",
            "MEMORY_SEARCHED",
            "ERROR_OCCURRED",
            "PLUGIN_LOADED",
            "PLUGIN_UNLOADED",
        }
        assert set(CONTRACT_EVENTS) == expected

    def test_exactly_four_events_have_a_real_class_today(self) -> None:
        implemented = [name for name, cls in CONTRACT_EVENTS.items() if cls is not None]
        assert set(implemented) == {"KERNEL_READY", "KERNEL_SHUTDOWN", "PLUGIN_LOADED", "PLUGIN_UNLOADED"}


class TestLoadRealPlugin:
    @pytest.mark.asyncio
    async def test_load_initializes_the_plugin(self, registry: PluginRegistry) -> None:
        ok, error = await registry.load(FIXTURE_DIR)

        assert ok is True
        assert error is None
        plugin = registry.get_plugin("example-plugin")
        assert plugin is not None
        assert plugin.initialized is True

    @pytest.mark.asyncio
    async def test_load_passes_real_event_bus_in_context(
        self, registry: PluginRegistry, event_bus: AsyncEventBus
    ) -> None:
        await registry.load(FIXTURE_DIR)

        plugin = registry.get_plugin("example-plugin")
        assert plugin.received_context["event_bus"] is event_bus

    @pytest.mark.asyncio
    async def test_context_di_container_is_none_documented(self, registry: PluginRegistry) -> None:
        # No hay DIContainer real en el proyecto — ver plugins/context.py.
        await registry.load(FIXTURE_DIR)
        plugin = registry.get_plugin("example-plugin")
        assert plugin.received_context["di_container"] is None

    @pytest.mark.asyncio
    async def test_load_connects_available_hook_and_flags_unavailable_one(
        self, registry: PluginRegistry
    ) -> None:
        await registry.load(FIXTURE_DIR)

        entry = registry.get_loaded_entry("example-plugin")
        assert "KERNEL_READY" in entry.connected_hooks
        assert "INTENT_DETECTED" in entry.unavailable_hooks

    @pytest.mark.asyncio
    async def test_load_publishes_plugin_loaded_event(
        self, registry: PluginRegistry, event_bus: AsyncEventBus
    ) -> None:
        from aries.plugins.events import PluginLoadedEvent

        received: list[PluginLoadedEvent] = []

        async def handler(event: PluginLoadedEvent) -> None:
            received.append(event)

        await event_bus.subscribe(PluginLoadedEvent, handler)
        await registry.load(FIXTURE_DIR)

        assert len(received) == 1
        assert received[0].plugin_name == "example-plugin"
        assert received[0].version == "1.0.0"

    @pytest.mark.asyncio
    async def test_real_event_reaches_the_plugin_hook(
        self, registry: PluginRegistry, event_bus: AsyncEventBus
    ) -> None:
        await registry.load(FIXTURE_DIR)
        plugin = registry.get_plugin("example-plugin")

        await event_bus.publish(KernelInitializedEvent())

        assert len(plugin.received_events) == 1
        assert isinstance(plugin.received_events[0], KernelInitializedEvent)

    @pytest.mark.asyncio
    async def test_list_plugins_and_get_plugin(self, registry: PluginRegistry) -> None:
        await registry.load(FIXTURE_DIR)

        listing = registry.list_plugins()
        assert "example-plugin" in listing
        assert listing["example-plugin"].version == "1.0.0"
        assert registry.get_plugin("no-existe") is None

    @pytest.mark.asyncio
    async def test_load_duplicate_name_fails_gracefully(self, registry: PluginRegistry) -> None:
        first = await registry.load(FIXTURE_DIR)
        second = await registry.load(FIXTURE_DIR)

        assert first == (True, None)
        assert second[0] is False
        assert "example-plugin" in second[1]


class TestUnloadRealPlugin:
    @pytest.mark.asyncio
    async def test_unload_calls_shutdown(self, registry: PluginRegistry) -> None:
        await registry.load(FIXTURE_DIR)
        plugin = registry.get_plugin("example-plugin")

        ok, error = await registry.unload("example-plugin")

        assert ok is True
        assert error is None
        assert plugin.shutdown_called is True
        assert registry.get_plugin("example-plugin") is None

    @pytest.mark.asyncio
    async def test_unload_disconnects_hooks_real_event_no_longer_received(
        self, registry: PluginRegistry, event_bus: AsyncEventBus
    ) -> None:
        await registry.load(FIXTURE_DIR)
        plugin = registry.get_plugin("example-plugin")

        await registry.unload("example-plugin")
        await event_bus.publish(KernelInitializedEvent())

        assert plugin.received_events == []

    @pytest.mark.asyncio
    async def test_unload_publishes_plugin_unloaded_event(
        self, registry: PluginRegistry, event_bus: AsyncEventBus
    ) -> None:
        from aries.plugins.events import PluginUnloadedEvent

        received: list[PluginUnloadedEvent] = []

        async def handler(event: PluginUnloadedEvent) -> None:
            received.append(event)

        await event_bus.subscribe(PluginUnloadedEvent, handler)
        await registry.load(FIXTURE_DIR)

        await registry.unload("example-plugin")

        assert len(received) == 1
        assert received[0].plugin_name == "example-plugin"

    @pytest.mark.asyncio
    async def test_unload_unknown_plugin_fails_gracefully(self, registry: PluginRegistry) -> None:
        ok, error = await registry.unload("no-existe")

        assert ok is False
        assert "no-existe" in error

    @pytest.mark.asyncio
    async def test_reload_after_unload_succeeds(self, registry: PluginRegistry) -> None:
        await registry.load(FIXTURE_DIR)
        await registry.unload("example-plugin")

        ok, error = await registry.load(FIXTURE_DIR)

        assert ok is True
        assert error is None


class TestLoadFailureModes:
    @pytest.mark.asyncio
    async def test_nonexistent_path_fails_gracefully(
        self, registry: PluginRegistry, tmp_path: Path
    ) -> None:
        ok, error = await registry.load(tmp_path / "no_existe")

        assert ok is False
        assert error is not None

    @pytest.mark.asyncio
    async def test_missing_requirement_blocks_load(
        self, registry: PluginRegistry, tmp_path: Path
    ) -> None:
        code = (
            "from aries.contracts.plugin import IPlugin, PluginMetadata\n\n"
            "class Clase(IPlugin):\n"
            "    def get_metadata(self): ...\n"
            "    async def initialize(self, context): return True\n"
            "    async def shutdown(self): return True\n"
            "    def register_hooks(self): return {}\n"
            "    def get_capabilities(self): return []\n"
            "    def is_compatible(self, kernel_version): return True\n"
        )
        _write_plugin(
            tmp_path,
            _broken_plugin_manifest(
                "necesita-algo", requires=["paquete_que_no_existe_xyz123"]
            ),
            code,
        )

        ok, error = await registry.load(tmp_path)

        assert ok is False
        assert "paquete_que_no_existe_xyz123" in error
        assert registry.get_plugin("necesita-algo") is None

    @pytest.mark.asyncio
    async def test_initialize_returning_false_fails_load(
        self, registry: PluginRegistry, tmp_path: Path
    ) -> None:
        code = (
            "from aries.contracts.plugin import IPlugin\n\n"
            "class Clase(IPlugin):\n"
            "    def get_metadata(self): ...\n"
            "    async def initialize(self, context): return False\n"
            "    async def shutdown(self): return True\n"
            "    def register_hooks(self): return {}\n"
            "    def get_capabilities(self): return []\n"
            "    def is_compatible(self, kernel_version): return True\n"
        )
        _write_plugin(tmp_path, _broken_plugin_manifest("init-falla"), code)

        ok, error = await registry.load(tmp_path)

        assert ok is False
        assert registry.get_plugin("init-falla") is None

    @pytest.mark.asyncio
    async def test_initialize_raising_fails_load(
        self, registry: PluginRegistry, tmp_path: Path
    ) -> None:
        code = (
            "from aries.contracts.plugin import IPlugin\n\n"
            "class Clase(IPlugin):\n"
            "    def get_metadata(self): ...\n"
            "    async def initialize(self, context): raise RuntimeError('boom')\n"
            "    async def shutdown(self): return True\n"
            "    def register_hooks(self): return {}\n"
            "    def get_capabilities(self): return []\n"
            "    def is_compatible(self, kernel_version): return True\n"
        )
        _write_plugin(tmp_path, _broken_plugin_manifest("init-explota"), code)

        ok, error = await registry.load(tmp_path)

        assert ok is False
        assert "boom" in error

    @pytest.mark.asyncio
    async def test_register_hooks_raising_rolls_back_with_shutdown(
        self, registry: PluginRegistry, tmp_path: Path
    ) -> None:
        code = (
            "from aries.contracts.plugin import IPlugin\n\n"
            "class Clase(IPlugin):\n"
            "    shutdown_called = False\n"
            "    def get_metadata(self): ...\n"
            "    async def initialize(self, context): return True\n"
            "    async def shutdown(self):\n"
            "        Clase.shutdown_called = True\n"
            "        return True\n"
            "    def register_hooks(self): raise RuntimeError('hooks rotos')\n"
            "    def get_capabilities(self): return []\n"
            "    def is_compatible(self, kernel_version): return True\n"
        )
        _write_plugin(tmp_path, _broken_plugin_manifest("hooks-rotos"), code)

        ok, error = await registry.load(tmp_path)

        assert ok is False
        assert "hooks rotos" in error
        assert registry.get_plugin("hooks-rotos") is None

        # Confirmar el rollback: shutdown() sí se llamó pese a que el plugin
        # nunca quedó registrado.
        import sys

        clase = next(
            m.Clase
            for name, m in sys.modules.items()
            if name.startswith("aries_plugin__hooks_rotos") and hasattr(m, "Clase")
        )
        assert clase.shutdown_called is True
