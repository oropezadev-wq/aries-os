"""Pruebas unitarias para el kernel de Aries OS."""

from __future__ import annotations

import pytest

from aries.config.settings import Settings
from aries.core.kernel import Kernel
from aries.memory.in_memory import InMemoryStore
from aries.contracts.llm import ILLMProvider, LLMResponse


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


@pytest.mark.asyncio
async def test_kernel_initialization() -> None:
    config = Settings()
    kernel = Kernel(config, InMemoryStore(), FakeLLMProvider())

    await kernel.initialize()

    assert kernel._initialized is True


@pytest.mark.asyncio
async def test_kernel_already_initialized() -> None:
    config = Settings()
    kernel = Kernel(config, InMemoryStore(), FakeLLMProvider())

    await kernel.initialize()
    await kernel.initialize()

    assert kernel._initialized is True


@pytest.mark.asyncio
async def test_kernel_shutdown() -> None:
    config = Settings()
    kernel = Kernel(config, InMemoryStore(), FakeLLMProvider())

    await kernel.initialize()
    await kernel.shutdown()

    assert kernel._initialized is False


@pytest.mark.asyncio
async def test_kernel_init_with_unavailable_llm_provider() -> None:
    config = Settings()
    fake_provider = FakeLLMProvider(available=False)
    memory = InMemoryStore()
    kernel = Kernel(config, memory, fake_provider)

    await kernel.initialize()

    assert kernel._initialized is True
    assert kernel.memory is memory
    assert kernel.llm_provider is fake_provider
