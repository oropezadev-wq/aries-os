"""API mínima para Aries OS usando FastAPI."""

from __future__ import annotations

import asyncio

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from .agents.manager import AgentManager
from .config.settings import Settings
from .contracts.event_bus import IEventBus
from .contracts.llm import ILLMProvider
from .contracts.memory import IMemory
from .core import Kernel
from .events import AsyncEventBus
from .llm.ollama_provider import OllamaProvider
from .logging import get_logger
from .memory.sqlite_store import SQLiteMemoryStore
from .planner import Planner

settings = Settings()
logger = get_logger("aries.api", settings.log_level)
app = FastAPI(title=settings.app_name)

# Instancias compartidas del proceso — mismo patrón que `settings`/`app` de
# arriba (singletons a nivel de módulo). `POST /message` es el "front door"
# elegido en docs/specs/Planner.spec.md (decisión 7): Kernel.run() sigue sin
# invocar a Planner directamente, deliberadamente — ver esa decisión para
# el porqué. `_memory` y `_agent_manager` en particular TIENEN que ser
# singletons (no una instancia nueva por request/consumidor) — `_memory`
# para que el contexto de conversación sobreviva entre llamadas a
# `POST /message` de una misma sesión, y `_agent_manager` (desde esta
# tarea) para que sea el MISMO objeto que usa el Planner y el que
# `Kernel.initialize()` usa para registrar los plugins que carga — así
# una capability de plugin queda dispatchable de verdad vía `POST /message`,
# no solo dentro de una copia aislada del Kernel (ver PROGRESS.md).
# `_memory` usa `SQLiteMemoryStore` (backend persistente, `settings.memory_db_path`)
# en vez de `InMemoryStore` — sobrevive a reinicios del proceso; sigue
# siendo el mismo `IMemory`, mismo contrato, mismo singleton de módulo.
_agent_manager = AgentManager()
_event_bus: IEventBus = AsyncEventBus()
_llm_provider: ILLMProvider = OllamaProvider(settings)
_memory: IMemory = SQLiteMemoryStore(settings.memory_db_path)
_kernel = Kernel(settings, _memory, _llm_provider, _event_bus, _agent_manager)
# Referencia a la tarea de fondo de `_kernel.run()` (bucle de housekeeping
# de vida larga) — se crea en `startup_event()` y se espera en
# `shutdown_event()`. Ver ambos hooks más abajo.
_kernel_run_task: asyncio.Task[None] | None = None


def get_planner() -> Planner:
    """Dependencia de FastAPI para obtener el `Planner`.

    Sobreescribible en tests vía `app.dependency_overrides[get_planner]`
    (ver `tests/integration/test_api_message.py`) para inyectar un
    `ILLMProvider` fake sin depender de un servidor Ollama real corriendo.
    """
    return Planner(
        llm_provider=_llm_provider, agent_manager=_agent_manager, event_bus=_event_bus, memory=_memory
    )


class MessageRequest(BaseModel):
    """Body de `POST /message`."""

    user_input: str
    session_id: str | None = None
    confirmed: bool = False


class MessageResponse(BaseModel):
    """Respuesta de `POST /message`."""

    plan_id: str
    success: bool
    response_text: str | None = None
    needs_confirmation: bool = False
    error: str | None = None


@app.on_event("startup")
async def startup_event() -> None:
    """Evento de inicio de la aplicación.

    Inicializa el `Kernel` compartido (`_kernel`) — esto es lo que
    descubre y carga los plugins de `settings.plugins_dir`, registrándolos
    en el mismo `_agent_manager` que usa el Planner (ver `PluginRegistry`/
    `PluginAgentAdapter`). Sin este paso, `Kernel.initialize()` nunca
    correría dentro del proceso que sirve `POST /message`, y ningún plugin
    sería alcanzable desde ahí.

    Después, lanza `_kernel.run()` (el bucle de housekeeping de
    `memory.clear_expired()`, ver `core/kernel.py`) como tarea de fondo de
    vida larga — deliberadamente sin `await` acá: `run()` no vuelve hasta
    que `shutdown()` señala su salida, y esperarlo acá dejaría el startup
    de la app colgado para siempre.
    """
    global _kernel_run_task
    logger.info("API Aries arrancando", environment=settings.environment)
    await _kernel.initialize()
    _kernel_run_task = asyncio.create_task(_kernel.run())


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Apaga el `Kernel` compartido de forma ordenada al cerrar la app.

    `_kernel.shutdown()` descarga los plugins cargados (en orden inverso) y
    señala el `asyncio.Event` que hace salir a `_kernel.run()` de su bucle
    de housekeeping (ver `core/kernel.py`). Después se espera (`await`, sin
    cancelar) a `_kernel_run_task` para confirmar que ese bucle terminó
    limpio antes de que el proceso cierre — no se cancela a la fuerza
    porque ya está diseñado para salir solo apenas se le señala.
    """
    await _kernel.shutdown()
    if _kernel_run_task is not None:
        await _kernel_run_task


@app.get("/health", summary="Estado de la aplicación")
async def health_check() -> dict[str, str]:
    """Comprueba que la API está disponible."""
    return {"status": "ok", "environment": settings.environment}


@app.post("/message", summary="Envía un mensaje al Planner", response_model=MessageResponse)
async def post_message(
    request: MessageRequest, planner: Planner = Depends(get_planner)
) -> MessageResponse:
    """Punto de entrada del usuario al sistema: texto -> Planner ->
    AgentManager -> Brain -> respuesta (`docs/specs/Planner.spec.md`).

    `Planner.handle()` nunca propaga excepciones, así que este endpoint no
    necesita su propio manejo de errores más allá de mapear el resultado a
    `MessageResponse` — cualquier fallo ya viene como `success=False` con
    `error` explicando qué pasó.
    """
    result = await planner.handle(
        request.user_input, session_id=request.session_id, confirmed=request.confirmed
    )
    return MessageResponse(
        plan_id=result.plan_id,
        success=result.success,
        response_text=result.response_text,
        needs_confirmation=result.needs_confirmation,
        error=result.error,
    )
