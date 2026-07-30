"""Plugin de ejemplo mínimo, usado solo por tests de integración de
PluginRegistry (`tests/unit/test_plugin_registry.py`). Implementa `IPlugin`
completo.
"""

from __future__ import annotations

from typing import Any, Callable

from aries.contracts.agent import ActionResult, ActionStatus
from aries.contracts.plugin import IPlugin, PluginMetadata


class ExamplePlugin(IPlugin):
    def __init__(self) -> None:
        self.initialized = False
        self.shutdown_called = False
        self.received_context: dict[str, Any] | None = None
        self.received_events: list[Any] = []

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="example-plugin",
            version="1.0.0",
            author="Aries OS tests",
            description="Plugin minimo de ejemplo para tests.",
            requires=[],
            entry_point="plugin:ExamplePlugin",
        )

    async def initialize(self, context: dict[str, Any]) -> bool:
        self.received_context = context
        self.initialized = True
        return True

    async def shutdown(self) -> bool:
        self.shutdown_called = True
        return True

    def register_hooks(self) -> dict[str, Callable[..., Any]]:
        return {
            "KERNEL_READY": self._on_kernel_ready,
            # "MEMORY_SEARCHED" todavía no existe como BaseEvent real (ver
            # plugins/registry.py::CONTRACT_EVENTS) — se declara a
            # propósito para que los tests confirmen que PluginRegistry lo
            # deja en `unavailable_hooks` en vez de fallar o mentir que
            # está conectado.
            "MEMORY_SEARCHED": self._on_memory_searched,
        }

    def get_capabilities(self) -> list[str]:
        return ["example_capability"]

    async def execute(self, action: str, **params: Any) -> ActionResult:
        """Capability real y funcional: `"example_capability"` hace un eco
        del parámetro `text`, mayúsculas — suficiente para que un consumidor
        (ej. `AgentManager.dispatch()`) pueda verificar un resultado
        concreto, no solo que "no explotó"."""
        if action != "example_capability":
            return ActionResult(
                status=ActionStatus.FAILED,
                error=f"'{action}' no es una acción soportada por este plugin",
            )

        text = params.get("text", "")
        return ActionResult(status=ActionStatus.SUCCESS, output=text.upper())

    def is_compatible(self, kernel_version: str) -> bool:
        return True

    async def _on_kernel_ready(self, event: Any) -> None:
        self.received_events.append(event)

    async def _on_memory_searched(self, event: Any) -> None:  # pragma: no cover
        self.received_events.append(event)
