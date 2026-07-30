"""Pruebas unitarias para el kernel de Aries OS."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

from aries.agents.manager import AgentManager
from aries.config.settings import Settings
from aries.core.events import KernelInitializedEvent, KernelShutdownEvent, KernelStartingEvent
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
    kernel = Kernel(config, InMemoryStore(), FakeLLMProvider(), FakeEventBus(), AgentManager())

    await kernel.initialize()

    assert kernel._initialized is True


@pytest.mark.asyncio
async def test_kernel_already_initialized() -> None:
    config = Settings()
    kernel = Kernel(config, InMemoryStore(), FakeLLMProvider(), FakeEventBus(), AgentManager())

    await kernel.initialize()
    await kernel.initialize()

    assert kernel._initialized is True


@pytest.mark.asyncio
async def test_kernel_shutdown() -> None:
    config = Settings()
    event_bus = FakeEventBus()
    kernel = Kernel(config, InMemoryStore(), FakeLLMProvider(), event_bus, AgentManager())

    await kernel.initialize()
    await kernel.shutdown()

    assert kernel._initialized is False


@pytest.mark.asyncio
async def test_kernel_init_with_unavailable_llm_provider() -> None:
    config = Settings()
    fake_provider = FakeLLMProvider(available=False)
    memory = InMemoryStore()
    kernel = Kernel(config, memory, fake_provider, FakeEventBus(), AgentManager())

    await kernel.initialize()

    assert kernel._initialized is True
    assert kernel.memory is memory
    assert kernel.llm_provider is fake_provider


@pytest.mark.asyncio
async def test_kernel_publishes_initialized_event() -> None:
    config = Settings()
    event_bus = FakeEventBus()
    kernel = Kernel(config, InMemoryStore(), FakeLLMProvider(), event_bus, AgentManager())

    await kernel.initialize()

    # Comparación por tipo, no por igualdad completa del objeto: comparar
    # instancias de `BaseEvent` con `==` incluye `timestamp`
    # (`datetime.now(UTC)` generado en cada instancia), que casi nunca
    # coincide al microsegundo entre la instancia real publicada y una
    # nueva creada acá — ver PROGRESS.md, ya documentado como flaky de
    # baseline en varias tareas anteriores. Mismo criterio ya usado en
    # `test_kernel_run_publishes_starting_event` más abajo.
    assert len(event_bus.published) == 1
    assert isinstance(event_bus.published[0], KernelInitializedEvent)


@pytest.mark.asyncio
async def test_kernel_publishes_shutdown_event() -> None:
    config = Settings()
    event_bus = FakeEventBus()
    kernel = Kernel(config, InMemoryStore(), FakeLLMProvider(), event_bus, AgentManager())

    await kernel.initialize()
    await kernel.shutdown()

    # Comparación por tipo, no por igualdad completa — ver comentario en
    # `test_kernel_publishes_initialized_event` arriba.
    assert isinstance(event_bus.published[-1], KernelShutdownEvent)


@pytest.mark.asyncio
async def test_kernel_initialize_stores_context_memory_item() -> None:
    config = Settings()
    memory = InMemoryStore()
    kernel = Kernel(config, memory, FakeLLMProvider(), FakeEventBus(), AgentManager())

    await kernel.initialize()

    context_items = await memory.get_by_type("context")
    assert len(context_items) == 1
    assert context_items[0].content == "Kernel inicializado"


@pytest.mark.asyncio
async def test_kernel_run_stops_cleanly_on_shutdown() -> None:
    """Arranque y shutdown ordenado del Kernel real: `run()` corre en segundo
    plano hasta que `shutdown()` lo señala, sin necesitar cancelación."""
    config = Settings(kernel_housekeeping_interval_seconds=0.05)
    kernel = Kernel(config, InMemoryStore(), FakeLLMProvider(), FakeEventBus(), AgentManager())

    await kernel.initialize()
    run_task = asyncio.create_task(kernel.run())
    await asyncio.sleep(0.1)
    assert kernel._running is True

    await kernel.shutdown()
    await asyncio.wait_for(run_task, timeout=1)

    assert kernel._running is False
    assert kernel._initialized is False


@pytest.mark.asyncio
async def test_kernel_run_publishes_starting_event() -> None:
    config = Settings(kernel_housekeeping_interval_seconds=0.05)
    event_bus = FakeEventBus()
    kernel = Kernel(config, InMemoryStore(), FakeLLMProvider(), event_bus, AgentManager())

    await kernel.initialize()
    run_task = asyncio.create_task(kernel.run())
    await asyncio.sleep(0.02)
    await kernel.shutdown()
    await asyncio.wait_for(run_task, timeout=1)

    assert any(isinstance(event, KernelStartingEvent) for event in event_bus.published)
    assert isinstance(event_bus.published[-1], KernelShutdownEvent)


@pytest.mark.asyncio
async def test_kernel_run_clears_expired_memory_periodically() -> None:
    """Housekeeping real: un item vencido en la Memory real (no mock) debe
    desaparecer solo, sin llamar a `clear_expired()` manualmente."""
    config = Settings(kernel_housekeeping_interval_seconds=0.05)
    memory = InMemoryStore()
    kernel = Kernel(config, memory, FakeLLMProvider(), FakeEventBus(), AgentManager())

    await kernel.initialize()
    expired_item = await memory.store(
        "dato viejo", "context", expires_at=datetime.now() - timedelta(seconds=1)
    )

    run_task = asyncio.create_task(kernel.run())
    await asyncio.sleep(0.15)
    await kernel.shutdown()
    await asyncio.wait_for(run_task, timeout=1)

    assert await memory.retrieve(expired_item.id) is None
