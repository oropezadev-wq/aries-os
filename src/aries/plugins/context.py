"""plugins/context.py — arma el `context` que `IPlugin.initialize(context)`
recibe, según `docs/contracts/IPlugin.md`: `logger`, `event_bus`,
`di_container`, `settings`.
"""

from __future__ import annotations

from typing import Any

from ..contracts.event_bus import IEventBus
from ..logging import get_logger


def build_plugin_context(
    event_bus: IEventBus, plugin_name: str, settings: Any = None
) -> dict[str, Any]:
    """Arma el dict de contexto real para `IPlugin.initialize()`.

    - `logger`: logger real con nombre por plugin (`plugin.<nombre>`), no
      un logger genérico compartido — así los logs de un plugin se pueden
      filtrar/atribuir.
    - `event_bus`: la instancia real de `IEventBus` que `PluginRegistry`
      recibió por constructor — nunca un mock ni un bus separado del que
      usa el resto del sistema.
    - `di_container`: **`None`, documentado a propósito, no un gap
      silencioso.** No existe ningún contenedor de inyección de
      dependencias real en el proyecto (`src/aries/container/` fue
      eliminado explícitamente — ver `PROGRESS.md` — y no hay ningún
      `DIContainer` ni equivalente en ningún otro lado). Construir uno
      nuevo es un problema de diseño en sí mismo, no parte de "sistema de
      plugins" — no se inventó uno para esta tarea.
    - `settings`: lo que quien construya `PluginRegistry` le haya pasado
      (típicamente `aries.config.settings.Settings`, pero este módulo no lo
      importa directamente para no acoplar `plugins/` a `config/` — se
      recibe y se reenvía tal cual, tipado como `Any`).
    """
    return {
        "logger": get_logger(f"plugin.{plugin_name}"),
        "event_bus": event_bus,
        "di_container": None,
        "settings": settings,
    }
