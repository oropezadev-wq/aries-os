"""Plugin de ejemplo mínimo, usado solo por tests de integración de
PluginRegistry (`tests/unit/test_plugin_registry.py`). Implementa `IPlugin`
completo.
"""

from __future__ import annotations

from typing import Any, Callable

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
            # "INTENT_DETECTED" todavía no existe como BaseEvent real (ver
            # docs/audits/2026-07-24-diagnostico.md) — se declara a
            # propósito para que los tests confirmen que PluginRegistry lo
            # deja en `unavailable_hooks` en vez de fallar o mentir que
            # está conectado.
            "INTENT_DETECTED": self._on_intent_detected,
        }

    def get_capabilities(self) -> list[str]:
        return ["example_capability"]

    def is_compatible(self, kernel_version: str) -> bool:
        return True

    async def _on_kernel_ready(self, event: Any) -> None:
        self.received_events.append(event)

    async def _on_intent_detected(self, event: Any) -> None:  # pragma: no cover
        self.received_events.append(event)
