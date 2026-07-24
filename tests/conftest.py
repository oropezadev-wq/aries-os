"""Configuración de pruebas para Aries OS."""

from __future__ import annotations

import pytest

from aries.config.settings import Settings
from aries.core.kernel import Kernel
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
async def fixture_kernel(app_config: Settings, llm_provider: ILLMProvider) -> Kernel:
    """Inicializa un kernel para uso en pruebas asincrónicas."""
    kernel = Kernel(app_config, InMemoryStore(), llm_provider)
    await kernel.initialize()
    yield kernel
    await kernel.shutdown()
