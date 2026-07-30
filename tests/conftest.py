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

from collections.abc import AsyncGenerator

import pytest

from aries.agents.manager import AgentManager
from aries.config.settings import Settings
from aries.core.kernel import Kernel
from aries.events import AsyncEventBus
from aries.memory.in_memory import InMemoryStore
from aries.contracts.llm import ILLMProvider
from aries.contracts.llm import LLMResponse


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
async def fixture_kernel(app_config: Settings, llm_provider: ILLMProvider) -> AsyncGenerator[Kernel, None]:
    """Inicializa un kernel para uso en pruebas asincrónicas."""
    kernel = Kernel(app_config, InMemoryStore(), llm_provider, AsyncEventBus(), AgentManager())
    await kernel.initialize()
    yield kernel
    await kernel.shutdown()
