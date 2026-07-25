"""Pruebas unitarias para el kernel de Aries OS."""

from __future__ import annotations

import pytest

from aries.config.settings import Settings
from aries.core.events import KernelInitializedEvent, KernelShutdownEvent
from aries.core.kernel import Kernel
from aries.events import BaseEvent
from aries.memory.in_memory import InMemoryStore
from aries.contracts.event_bus import IEventBus
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


class FakeEventBus(IEventBus):
    """Bus de eventos fake para pruebas del kernel."""

    def __init__(self) -> None:
        self.published: list[BaseEvent] = []

    async def publish(self, event: BaseEvent) -> None:
        self.published.append(event)

    async def subscribe(self, event_type: EventType, handler: Handler) -> None:
        return None

    async def unsubscribe(self, event_type: EventType, handler: Handler) -> None:
        return None


@pytest.mark.asyncio
async def test_kernel_initialization() -> None:
    config = Settings()
    kernel = Kernel(config, InMemoryStore(), FakeLLMProvider(), FakeEventBus())

    await kernel.initialize()

    assert kernel._initialized is True


@pytest.mark.asyncio
async def test_kernel_already_initialized() -> None:
    config = Settings()
    kernel = Kernel(config, InMemoryStore(), FakeLLMProvider(), FakeEventBus())

    await kernel.initialize()
    await kernel.initialize()

    assert kernel._initialized is True


@pytest.mark.asyncio
async def test_kernel_shutdown() -> None:
    config = Settings()
    event_bus = FakeEventBus()
    kernel = Kernel(config, InMemoryStore(), FakeLLMProvider(), event_bus)

    await kernel.initialize()
    await kernel.shutdown()

    assert kernel._initialized is False


@pytest.mark.asyncio
async def test_kernel_init_with_unavailable_llm_provider() -> None:
    config = Settings()
    fake_provider = FakeLLMProvider(available=False)
    memory = InMemoryStore()
    kernel = Kernel(config, memory, fake_provider, FakeEventBus())

    await kernel.initialize()

    assert kernel._initialized is True
    assert kernel.memory is memory
    assert kernel.llm_provider is fake_provider


@pytest.mark.asyncio
async def test_kernel_publishes_initialized_event() -> None:
    config = Settings()
    event_bus = FakeEventBus()
    kernel = Kernel(config, InMemoryStore(), FakeLLMProvider(), event_bus)

    await kernel.initialize()

    assert event_bus.published == [KernelInitializedEvent()]


@pytest.mark.asyncio
async def test_kernel_publishes_shutdown_event() -> None:
    config = Settings()
    event_bus = FakeEventBus()
    kernel = Kernel(config, InMemoryStore(), FakeLLMProvider(), event_bus)

    await kernel.initialize()
    await kernel.shutdown()

    assert event_bus.published[-1] == KernelShutdownEvent()


@pytest.mark.asyncio
async def test_kernel_initialize_stores_context_memory_item() -> None:
    config = Settings()
    memory = InMemoryStore()
    kernel = Kernel(config, memory, FakeLLMProvider(), FakeEventBus())

    await kernel.initialize()

    context_items = await memory.get_by_type("context")
    assert len(context_items) == 1
    assert context_items[0].content == "Kernel inicializado"
