"""Configuración de pruebas para Aries OS."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# `aries.api` construye `_memory = SQLiteMemoryStore(settings.memory_db_path)`
# como singleton de módulo, a nivel de import (ver `src/aries/api.py`) — sin
# esto, cualquier test que importe `aries.api` (directa o indirectamente)
# crearía/reusaría un `aries_memory.db` real en la raíz del repo, con datos
# que persistirían entre corridas de `pytest` (justo lo que el store está
# diseñado para hacer). Se fuerza acá, ANTES de cualquier import que pueda
# disparar la construcción de `aries.api`, un directorio temporal nuevo por
# sesión de test (no reusado entre corridas, a diferencia de
# `tests/.cache/` para modelos de voz) — el objetivo ahí es no pagar el
# costo de re-descargar modelos, acá es exactamente lo contrario: no
# arrastrar datos de una corrida de tests a la siguiente.
os.environ.setdefault(
    "MEMORY_DB_PATH", str(Path(tempfile.mkdtemp(prefix="aries-test-memory-")) / "memory.db")
)

# Auditoría de seguridad 2026-09-23 (hallazgo CRÍTICO #1): POST /message y
# POST /message/confirm rechazan todo pedido si Settings.api_key está vacía
# (falla cerrado) — sin esto, cualquier test que llame a esos endpoints via
# TestClient recibiría 401 en vez de lo que esté probando. Mismo criterio
# que MEMORY_DB_PATH arriba: seteado antes de cualquier import que dispare
# la construcción de `aries.api.settings`. No es un secreto real, vive acá
# a la vista para que los tests que llaman a esos endpoints lo importen.
TEST_API_KEY = "test-api-key-not-a-secret"
os.environ.setdefault("API_KEY", TEST_API_KEY)

from collections.abc import AsyncGenerator

import pytest
import redis as redis_sync
import redis.asyncio as redis_asyncio
from redis.exceptions import RedisError

from aries.agents.manager import AgentManager
from aries.config.settings import Settings
from aries.contracts.llm import ILLMProvider, LLMResponse
from aries.contracts.message_bus import IMessageBus
from aries.core.kernel import Kernel
from aries.events import AsyncEventBus
from aries.memory.in_memory import InMemoryStore

# Auditoría de seguridad 2026-09-23 (hallazgo CRÍTICO #1): DB 14 — distinta
# de la 15 que ya usa `tests/unit/test_redis_streams_bus.py`, para no pisar
# datos entre suites que puedan correr en paralelo. Mismo criterio de esa
# suite: Redis real (las acciones pendientes de confirmación viven en
# Redis de verdad, no tiene sentido mockearlo), skip con mensaje claro si
# no hay uno alcanzable en vez de romper toda la corrida.
TEST_CONFIRMATION_REDIS_URL = "redis://localhost:6379/14"


async def _redis_available(url: str) -> bool:
    try:
        client = redis_asyncio.Redis.from_url(url, socket_connect_timeout=5)
        await client.ping()
        await client.aclose()
        return True
    except RedisError:
        return False


@pytest.fixture(name="confirmation_redis")
async def fixture_confirmation_redis() -> AsyncGenerator[redis_asyncio.Redis]:
    """Cliente Redis real para tests de `Planner.confirm()` — DB 14,
    limpiada al terminar cada test que la use. Para tests `async def`
    (`pytest.mark.asyncio`) que corren en el mismo loop que este fixture,
    ej. `test_planner.py`, `test_voice_pipeline.py` (usa
    `httpx.AsyncClient`+`ASGITransport`, mismo loop). NO usar con
    `fastapi.testclient.TestClient` (sync) — ver `confirmation_redis_factory`."""
    if not await _redis_available(TEST_CONFIRMATION_REDIS_URL):
        pytest.skip(f"Redis no alcanzable en {TEST_CONFIRMATION_REDIS_URL} — se skippea el test de confirmación")
    client = redis_asyncio.Redis.from_url(TEST_CONFIRMATION_REDIS_URL)
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture(name="confirmation_redis_factory")
def fixture_confirmation_redis_factory():
    """Fábrica de clientes Redis SIN conectar, para tests que usan
    `fastapi.testclient.TestClient` (sync) — `TestClient` corre cada
    request en su propio loop interno (un "portal" de `anyio`), distinto
    del loop de pytest-asyncio en el que correría un cliente ya conectado
    acá (`confirmation_redis` de arriba) — eso da 'RuntimeError: Event
    loop is closed' en la segunda request. `redis.asyncio.Redis.from_url`
    no necesita loop para construirse (solo arma configuración; la
    conexión real es perezosa, recién al primer comando) — cada llamada a
    la fábrica da un cliente nuevo que se conecta solo cuando `TestClient`
    lo usa de verdad, dentro de SU loop.

    La comprobación de disponibilidad usa el cliente SÍNCRONO de `redis`
    (sin asyncio, sin afinidad a ningún loop) — evita el mismo problema
    para el chequeo en sí."""
    try:
        client = redis_sync.Redis.from_url(TEST_CONFIRMATION_REDIS_URL, socket_connect_timeout=5)
        client.ping()
        client.close()
    except redis_sync.exceptions.RedisError:
        pytest.skip(f"Redis no alcanzable en {TEST_CONFIRMATION_REDIS_URL} — se skippea el test de confirmación")

    def _factory() -> redis_asyncio.Redis:
        return redis_asyncio.Redis.from_url(TEST_CONFIRMATION_REDIS_URL)

    # Sin limpieza explícita acá: los clientes que da la fábrica quedan
    # atados al loop interno de `TestClient` (cerrado para cuando termina
    # el test) — no hay loop válido en el que hacer `await client.aclose()`
    # desde este fixture sync. Las claves que dejan tienen TTL
    # (`pending_confirmation_ttl_seconds`, default 120s) y expiran solas.
    yield _factory


class FakeMessageBus(IMessageBus):
    """`IMessageBus` fake compartido por la fixture `kernel` — mismo
    criterio que `tests/unit/test_kernel.py`: estos tests no ejercitan
    Routines de verdad, solo necesitan satisfacer el contrato."""

    async def publish(self, topic: str, payload: dict) -> str:
        return "0-1"

    async def subscribe(self, topic: str, group: str, consumer: str):
        if False:  # pragma: no cover - nunca se llama en estos tests
            yield
        return

    async def ack(self, topic: str, group: str, message_id: str) -> None:
        return None


class FakeLLMProvider(ILLMProvider):
    """Proveedor LLM de prueba configurable para tests."""

    def __init__(self, available: bool = True) -> None:
        self.available = available

    async def complete(self, prompt: str, temperature: float = 0.7, max_tokens: int | None = None, **kwargs) -> LLMResponse:
        return LLMResponse(content="", model="fake", tokens_used=0)

    async def embed(self, text: str) -> list[float]:
        return []

    async def is_available(self) -> bool:
        return self.available

    def get_model_name(self) -> str:
        return "fake"


@pytest.fixture(name="app_config")
def fixture_app_config() -> Settings:
    """Retorna la configuración base para los tests."""
    return Settings()


@pytest.fixture(name="llm_provider")
def fixture_llm_provider() -> ILLMProvider:
    """Retorna un proveedor LLM fake configurado para tests."""
    return FakeLLMProvider()


@pytest.fixture(name="kernel")
async def fixture_kernel(app_config: Settings, llm_provider: ILLMProvider) -> AsyncGenerator[Kernel]:
    """Inicializa un kernel para uso en pruebas asincrónicas."""
    kernel = Kernel(app_config, InMemoryStore(), llm_provider, AsyncEventBus(), AgentManager(), FakeMessageBus())
    await kernel.initialize()
    yield kernel
    await kernel.shutdown()
