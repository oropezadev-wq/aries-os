"""API mínima para Aries OS usando FastAPI."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from .agents.manager import AgentManager
from .config.settings import Settings
from .contracts.event_bus import IEventBus
from .contracts.llm import ILLMProvider
from .contracts.memory import IMemory
from .contracts.message_bus import IMessageBus
from .core import Kernel
from .events import AsyncEventBus
from .llm.ollama_provider import OllamaProvider
from .logging import get_logger
from .memory.sqlite_store import SQLiteMemoryStore
from .messaging.redis_streams_bus import RedisStreamsMessageBus
from .planner import Planner

settings = Settings()
logger = get_logger("aries.api", settings.log_level)

# Instancias compartidas del proceso — singletons a nivel de módulo.
# `POST /message` es el "front door" elegido en docs/specs/Planner.spec.md
# (decisión 7): Kernel.run() sigue sin invocar a Planner directamente,
# deliberadamente — ver esa decisión para el porqué. `_memory` y
# `_agent_manager` en particular TIENEN que ser singletons (no una
# instancia nueva por request/consumidor) — `_memory` para que el contexto
# de conversación sobreviva entre llamadas a `POST /message` de una misma
# sesión, y `_agent_manager` para que sea el MISMO objeto que usa el
# Planner y el que `Kernel.initialize()` usa para registrar los plugins
# que carga — así una capability de plugin queda dispatchable de verdad
# vía `POST /message`, no solo dentro de una copia aislada del Kernel (ver
# PROGRESS.md). `_memory` usa `SQLiteMemoryStore` (backend persistente,
# `settings.memory_db_path`) en vez de `InMemoryStore` — sobrevive a
# reinicios del proceso; sigue siendo el mismo `IMemory`, mismo contrato,
# mismo singleton de módulo.
_agent_manager = AgentManager()
_event_bus: IEventBus = AsyncEventBus()
_memory: IMemory = SQLiteMemoryStore(settings.memory_db_path)
# `IMessageBus` real sobre Redis Streams (docs/specs/MessageBus.spec.md) —
# el mismo `settings.redis_url` que consume `VoicePipeline` como proceso
# aparte, así ambos hablan por el mismo stream "routines.due".
_message_bus: IMessageBus = RedisStreamsMessageBus(settings.redis_url)

# `_llm_provider`, `_kernel` y `_kernel_run_task` YA NO se construyen acá:
# cada uno se crea de cero dentro de `lifespan()` en cada ciclo de arranque
# de la app, para que un `OllamaProvider` ya cerrado en un shutdown nunca
# sea reutilizado por el siguiente startup (bug real: `TestClient(app)`
# levantado varias veces en la misma suite compartía un único
# `OllamaProvider` de módulo; cerrarlo en el primer shutdown rompía el
# segundo startup con "Cannot send a request, as the client has been
# closed" — ver PROGRESS.md). Quedan declarados acá como globals de
# módulo, reasignados en cada `lifespan()`, por compatibilidad con
# `get_planner()` y con los tests de integración que leen
# `api._kernel_run_task` directo.
_llm_provider: ILLMProvider | None = None
_kernel: Kernel | None = None
_kernel_run_task: asyncio.Task[None] | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Ciclo de vida de la app — reemplaza a los antiguos
    `@app.on_event("startup")`/`@app.on_event("shutdown")` (API deprecada
    de FastAPI/Starlette).

    Construye un `OllamaProvider` y un `Kernel` NUEVOS en cada arranque —
    guardados en `app.state` (forma idiomática para código nuevo) y
    también reasignados a los globals de módulo `_llm_provider`/`_kernel`/
    `_kernel_run_task`, para que `get_planner()` y los tests de integración
    que los referencian directo sigan funcionando sin cambios.
    `Kernel.initialize()` descubre y carga los plugins de
    `settings.plugins_dir`, registrándolos en el mismo `_agent_manager` que
    usa el Planner. Después, lanza `kernel.run()` (housekeeping de fondo)
    como tarea de vida larga — deliberadamente sin esperarla acá: no
    vuelve hasta que `kernel.shutdown()` señala su salida.

    Al cerrar: apaga el kernel (descarga plugins en orden inverso, señala
    el stop event de `run()`), espera esa tarea de fondo, y recién
    entonces cierra el `OllamaProvider` de ESTE ciclo — nunca uno
    compartido con un ciclo anterior o futuro.
    """
    global _llm_provider, _kernel, _kernel_run_task

    logger.info("API Aries arrancando", environment=settings.environment)

    llm_provider: ILLMProvider = OllamaProvider(settings)
    kernel = Kernel(settings, _memory, llm_provider, _event_bus, _agent_manager, _message_bus)

    app.state.llm_provider = llm_provider
    app.state.kernel = kernel

    await kernel.initialize()
    kernel_run_task = asyncio.create_task(kernel.run())
    app.state.kernel_run_task = kernel_run_task

    _llm_provider, _kernel, _kernel_run_task = llm_provider, kernel, kernel_run_task

    try:
        yield
    finally:
        await kernel.shutdown()
        await kernel_run_task
        await llm_provider.close()


app = FastAPI(title=settings.app_name, lifespan=lifespan)


def get_planner() -> Planner:
    """Dependencia de FastAPI para obtener el `Planner`.

    Sobreescribible en tests vía `app.dependency_overrides[get_planner]`
    (ver `tests/integration/test_api_message.py`) para inyectar un
    `ILLMProvider` fake sin depender de un servidor Ollama real corriendo.
    """
    assert _llm_provider is not None  # narrowing: siempre seteado por `lifespan()` al arrancar la app
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
