"""API mínima para Aries OS usando FastAPI."""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncIterator, Awaitable, Iterable
from contextlib import asynccontextmanager
from typing import Literal

import redis.asyncio as redis_asyncio
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
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

# Topes duros de `GET /health`: un health que se bloquea es peor que uno que
# miente. Cada probe tiene su propio tope, y el conjunto tiene uno global
# como red final por si algún probe ignora la cancelación. Se leen en
# runtime (no se copian a otras constantes) para que los tests los puedan
# reducir con `monkeypatch`.
_HEALTH_CHECK_TIMEOUT_SECONDS = 2.0
_HEALTH_TOTAL_TIMEOUT_SECONDS = 3.0

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
_agent_manager = AgentManager(filesystem_allowed_root=settings.filesystem_allowed_root)
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
# Cliente de Redis dedicado a las acciones pendientes de confirmación
# (`Planner.confirm()`, auditoría de seguridad 2026-09-23, hallazgo
# CRÍTICO #1) — mismo criterio que `health_redis`: propio, no comparte
# conexión con `RedisStreamsMessageBus`, se cierra en el `finally` de
# `lifespan()`, nunca se reusa entre ciclos de arranque.
_confirmation_redis: redis_asyncio.Redis | None = None


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
    global _llm_provider, _kernel, _kernel_run_task, _confirmation_redis

    logger.info("API Aries arrancando", environment=settings.environment)

    llm_provider: ILLMProvider = OllamaProvider(settings)
    kernel = Kernel(settings, _memory, llm_provider, _event_bus, _agent_manager, _message_bus)
    # Cliente de Redis dedicado a `/health`, reusado entre llamadas (ninguna
    # abre una conexión nueva). Se crea acá y se cierra abajo, por el mismo
    # motivo que `llm_provider`: un cliente de módulo cerrado en un shutdown
    # rompería el startup siguiente. No pasa por `RedisStreamsMessageBus`: es
    # solo lectura de estado, no una operación del contrato de mensajería.
    health_redis = redis_asyncio.Redis.from_url(
        settings.redis_url,
        socket_timeout=_HEALTH_CHECK_TIMEOUT_SECONDS,
        socket_connect_timeout=_HEALTH_CHECK_TIMEOUT_SECONDS,
    )
    # Cliente de Redis dedicado a las acciones pendientes de confirmación
    # (`Planner.confirm()`, auditoría de seguridad 2026-09-23, hallazgo
    # CRÍTICO #1) — mismo criterio que `health_redis` arriba: propio, no
    # comparte conexión con `RedisStreamsMessageBus` ni con `health_redis`.
    confirmation_redis = redis_asyncio.Redis.from_url(settings.redis_url)

    app.state.llm_provider = llm_provider
    app.state.kernel = kernel
    app.state.health_redis = health_redis
    app.state.confirmation_redis = confirmation_redis

    await kernel.initialize()
    kernel_run_task = asyncio.create_task(kernel.run())
    app.state.kernel_run_task = kernel_run_task

    # Puente de compatibilidad, no diseño final: `get_planner()` y los tests
    # de integración leen estos globals directo (`api._kernel_run_task`,
    # etc.). Con una sola instancia de `app` por proceso esto es correcto,
    # pero es deuda conocida — con dos instancias de `app` corriendo en el
    # mismo proceso, estos globals apuntarían a la última que arrancó, no a
    # la que los llamó (ver PROGRESS.md).
    _llm_provider, _kernel, _kernel_run_task = llm_provider, kernel, kernel_run_task
    _confirmation_redis = confirmation_redis

    try:
        yield
    finally:
        await kernel.shutdown()
        await kernel_run_task
        await llm_provider.close()
        await health_redis.aclose()
        await confirmation_redis.aclose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)


def get_planner() -> Planner:
    """Dependencia de FastAPI para obtener el `Planner`.

    Sobreescribible en tests vía `app.dependency_overrides[get_planner]`
    (ver `tests/integration/test_api_message.py`) para inyectar un
    `ILLMProvider` fake sin depender de un servidor Ollama real corriendo.
    """
    assert _llm_provider is not None  # narrowing: siempre seteado por `lifespan()` al arrancar la app
    return Planner(
        llm_provider=_llm_provider,
        agent_manager=_agent_manager,
        event_bus=_event_bus,
        memory=_memory,
        redis_client=_confirmation_redis,
        pending_confirmation_ttl_seconds=settings.pending_confirmation_ttl_seconds,
    )


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Dependencia de auth para `POST /message`/`POST /message/confirm` —
    NUNCA para `GET /health` (deliberado: `start-aries.ps1` depende de
    poder consultarlo sin credenciales para saber si el proceso está
    arriba, ver Decisión 5 de `docs/audits/2026-09-23-security-audit.md`).

    Falla cerrado: si `Settings.api_key` está vacía (sin configurar), TODO
    pedido se rechaza — no hay un default inseguro tipo
    `secret_key="change-me-in-production"` que nadie cambie nunca.
    `secrets.compare_digest` en vez de `==` para no filtrar por timing
    cuánto del prefijo de la key coincide.
    """
    configured = settings.api_key.get_secret_value()
    if not configured or not x_api_key or not secrets.compare_digest(x_api_key, configured):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key inválida o no configurada")


class MessageRequest(BaseModel):
    """Body de `POST /message`.

    Ya no tiene `confirmed: bool` (auditoría de seguridad 2026-09-23,
    hallazgo CRÍTICO #1) — una acción que necesita confirmación se
    confirma vía `POST /message/confirm`, con `confirmation_id` +
    `confirmation_text`, no reafirmando este mismo pedido con un flag que
    el cliente controlaba sin que mediara ninguna verificación real."""

    user_input: str
    session_id: str | None = None


class ConfirmRequest(BaseModel):
    """Body de `POST /message/confirm`. `confirmation_text` es lo que el
    usuario dijo/escribió como confirmación — el servidor lo compara
    contra la frase exacta esperada, nunca confía en un booleano."""

    confirmation_id: str
    confirmation_text: str
    session_id: str | None = None


class MessageResponse(BaseModel):
    """Respuesta de `POST /message` y `POST /message/confirm`."""

    plan_id: str
    success: bool
    response_text: str | None = None
    needs_confirmation: bool = False
    confirmation_id: str | None = None
    error: str | None = None


class HealthCheck(BaseModel):
    """Resultado de un chequeo individual de `GET /health`.

    `critical` dice qué significa que ESTE check falle, no si falló: un
    check crítico caído es una falla grave del criterio de éxito de Fase 1
    (`docs/VISION.md`); uno no crítico solo degrada.
    """

    status: Literal["ok", "error"]
    critical: bool
    detail: str | None = None


class HealthChecks(BaseModel):
    """Detalle por chequeo de `GET /health`."""

    kernel: HealthCheck
    redis: HealthCheck
    ollama: HealthCheck


class HealthResponse(BaseModel):
    """Respuesta de `GET /health`. `status` se deriva de `checks`: `ok` si
    todos pasan, `degraded` si falla alguno no crítico, `critical` si falla
    alguno crítico."""

    status: Literal["ok", "degraded", "critical"]
    environment: str
    checks: HealthChecks


def _derive_status(checks: Iterable[HealthCheck]) -> Literal["ok", "degraded", "critical"]:
    failed = [check for check in checks if check.status != "ok"]
    if any(check.critical for check in failed):
        return "critical"
    return "degraded" if failed else "ok"


def _check_kernel(kernel_run_task: asyncio.Task[None] | None) -> HealthCheck:
    """Crítico: si el loop de `Kernel.run()` murió, las rutinas no disparan
    nunca y nada más lo avisa — la falla grave del criterio de Fase 1. Es
    lectura de estado en memoria (sin I/O), por eso no lleva timeout. Cuando
    murió, el detalle incluye la causa (`Task.exception()`)."""
    if kernel_run_task is None:
        return HealthCheck(status="error", critical=True, detail="Kernel no inicializado")
    if not kernel_run_task.done():
        return HealthCheck(status="ok", critical=True)
    if kernel_run_task.cancelled():
        detail = "el loop de run() fue cancelado"
    else:
        error = kernel_run_task.exception()
        detail = f"el loop de run() terminó con {error!r}" if error else "el loop de run() terminó"
    return HealthCheck(status="error", critical=True, detail=detail)


async def _probe_redis(client: redis_asyncio.Redis | None) -> None:
    if client is None:
        raise RuntimeError("cliente de Redis del health no inicializado")
    await client.ping()


async def _probe_ollama(provider: ILLMProvider | None) -> None:
    if provider is None:
        raise RuntimeError("proveedor LLM no inicializado")
    if not await provider.is_available():
        raise RuntimeError("Ollama no disponible")


async def _run_probe(probe: Awaitable[None], *, critical: bool) -> HealthCheck:
    """Ejecuta un probe con tope duro. Nunca propaga: cualquier falla, o
    exceder el tope, queda como un `HealthCheck` en `error` — el endpoint no
    puede quedar bloqueado ni caerse por una dependencia."""
    try:
        await asyncio.wait_for(probe, timeout=_HEALTH_CHECK_TIMEOUT_SECONDS)
    except TimeoutError:
        return HealthCheck(status="error", critical=critical, detail=f"timeout ({_HEALTH_CHECK_TIMEOUT_SECONDS}s)")
    except Exception as error:
        return HealthCheck(status="error", critical=critical, detail=str(error) or type(error).__name__)
    return HealthCheck(status="ok", critical=critical)


@app.get("/health", summary="Estado de la aplicación", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """Estado real de Aries: `kernel` (loop de `run()` vivo, crítico),
    `redis` (PING) y `ollama` (`is_available()`), estos dos no críticos.

    Siempre devuelve HTTP 200, a propósito: el código HTTP es solo
    liveness ("el proceso sirve y el Kernel terminó de inicializar", ya que
    uvicorn ejecuta el startup del lifespan antes de abrir el puerto) — es
    lo único que mira `scripts/start-aries.ps1`. Ninguna dependencia es
    dura hoy (Redis conecta perezoso y reintenta; Ollama solo degrada), así
    que un 503 no tendría un disparador legítimo. La salud real vive en
    `status`/`checks` del body.

    Redis y Ollama se sondean en paralelo (peor caso: el tope de un probe,
    no la suma), con clientes reusados de `app.state` — sin conexiones
    nuevas por llamada y sin caché, a propósito: no hay ningún poller que
    lo justifique todavía."""
    state = request.app.state
    probes = {
        "redis": asyncio.create_task(_run_probe(_probe_redis(getattr(state, "health_redis", None)), critical=False)),
        "ollama": asyncio.create_task(_run_probe(_probe_ollama(getattr(state, "llm_provider", None)), critical=False)),
    }
    _, pending = await asyncio.wait(probes.values(), timeout=_HEALTH_TOTAL_TIMEOUT_SECONDS)
    for task in pending:
        task.cancel()

    results = {
        name: task.result()
        if task not in pending
        else HealthCheck(status="error", critical=False, detail=f"timeout global ({_HEALTH_TOTAL_TIMEOUT_SECONDS}s)")
        for name, task in probes.items()
    }
    checks = HealthChecks(
        kernel=_check_kernel(getattr(state, "kernel_run_task", None)),
        redis=results["redis"],
        ollama=results["ollama"],
    )
    return HealthResponse(
        status=_derive_status([checks.kernel, checks.redis, checks.ollama]),
        environment=settings.environment,
        checks=checks,
    )


@app.post(
    "/message",
    summary="Envía un mensaje al Planner",
    response_model=MessageResponse,
    dependencies=[Depends(require_api_key)],
)
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
    result = await planner.handle(request.user_input, session_id=request.session_id)
    return MessageResponse(
        plan_id=result.plan_id,
        success=result.success,
        response_text=result.response_text,
        needs_confirmation=result.needs_confirmation,
        confirmation_id=result.confirmation_id,
        error=result.error,
    )


@app.post(
    "/message/confirm",
    summary="Confirma (o rechaza) una acción pendiente de POST /message",
    response_model=MessageResponse,
    dependencies=[Depends(require_api_key)],
)
async def post_message_confirm(
    request: ConfirmRequest, planner: Planner = Depends(get_planner)
) -> MessageResponse:
    """Segunda mitad del flujo de confirmación (auditoría de seguridad
    2026-09-23, hallazgo CRÍTICO #1): `confirmation_id` referencia una
    acción concreta que `POST /message` dejó pendiente — no re-envía el
    pedido original, y no hay ningún campo `confirmed: bool` que el
    cliente pueda simplemente afirmar. `Planner.confirm()` verifica
    `confirmation_text` contra la frase de confirmación exacta del lado
    del servidor. Nunca propaga excepciones, mismo criterio que
    `POST /message`."""
    result = await planner.confirm(
        request.confirmation_id, request.confirmation_text, session_id=request.session_id
    )
    return MessageResponse(
        plan_id=result.plan_id,
        success=result.success,
        response_text=result.response_text,
        needs_confirmation=result.needs_confirmation,
        confirmation_id=result.confirmation_id,
        error=result.error,
    )
