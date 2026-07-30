"""Punto de entrada principal para ejecutar Aries OS: sirve la API HTTP
(`aries.api:app`) vía uvicorn.

El Kernel ya no se construye ni se corre acá por separado. Desde la
unificación de `AgentManager` (ver PROGRESS.md — antes `__main__.py`
construía su propio `Kernel` con su propia `InMemoryStore`/`AgentManager`,
totalmente aislado del proceso de la API), el ciclo de vida del Kernel
(`initialize()`/`shutdown()`) vive en los eventos de arranque/apagado de
`aries.api` (`_kernel`, compartiendo `_agent_manager`/`_memory`/
`_event_bus` con el Planner) — es lo único que permite que un plugin
cargado por el Kernel quede dispatchable de verdad vía `POST /message`.
Correr `python -m aries` y correr `uvicorn aries.api:app` directamente son,
a partir de ahora, equivalentes en la práctica; este módulo es solo un
atajo que además respeta `settings.api_host`/`settings.api_port`.

`kernel.run()` (el bucle de housekeeping de fondo) ya no se invoca desde
ningún lado por defecto — antes solo lo hacía este módulo en su modo
standalone, que dejó de existir. Ver PROGRESS.md para el detalle de este
gap conocido, no resuelto acá a propósito (no se pidió).
"""

from __future__ import annotations

import uvicorn

from .config.settings import Settings
from .logging import get_logger

LOGGER = get_logger("aries.__main__")


def run() -> None:
    """Levanta `aries.api:app` con uvicorn. El arranque/apagado ordenado
    del Kernel compartido (incluida la carga/descarga de plugins) ocurre
    dentro de los eventos de startup/shutdown de `aries.api`, no acá."""
    settings = Settings()
    uvicorn.run(
        "aries.api:app",
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
