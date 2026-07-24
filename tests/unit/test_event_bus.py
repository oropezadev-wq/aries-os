from __future__ import annotations

from dataclasses import dataclass, field
import asyncio
import threading
import time

import pytest

from aries.events import AsyncEventBus, BaseEvent


class TestEventBus:
    @pytest.mark.asyncio
    async def test_subscribe_and_publish_calls_handler(self) -> None:
        bus = AsyncEventBus()
        received: list[str] = []

        async def handler(event: BaseEvent) -> None:
            received.append(event.event_type)

        await bus.subscribe(BaseEvent, handler)
        await bus.publish(BaseEvent())

        assert received == ["BaseEvent"]

    @pytest.mark.asyncio
    async def test_subscribe_to_base_event_does_not_receive_other_event_types(self) -> None:
        bus = AsyncEventBus()
        received: list[str] = []

        @dataclass(frozen=True)
        class SampleEvent(BaseEvent):
            payload: dict[str, str] = field(default_factory=dict)

        async def handler(event: BaseEvent) -> None:
            received.append(event.event_type)

        await bus.subscribe(BaseEvent, handler)
        await bus.publish(SampleEvent())

        assert received == []

    @pytest.mark.asyncio
    async def test_publish_continues_when_handler_raises(self) -> None:
        bus = AsyncEventBus()
        received: list[str] = []

        async def failing_handler(event: BaseEvent) -> None:
            raise RuntimeError("failure")

        async def succeeding_handler(event: BaseEvent) -> None:
            received.append("ok")

        await bus.subscribe(BaseEvent, failing_handler)
        await bus.subscribe(BaseEvent, succeeding_handler)
        await bus.publish(BaseEvent())

        assert received == ["ok"]

    @pytest.mark.asyncio
    async def test_unsubscribe_stops_handler_from_receiving_events(self) -> None:
        bus = AsyncEventBus()
        received: list[str] = []

        async def handler(event: BaseEvent) -> None:
            received.append("called")

        await bus.subscribe(BaseEvent, handler)
        await bus.unsubscribe(BaseEvent, handler)
        await bus.publish(BaseEvent())

        assert received == []

    def test_base_event_has_stable_event_id(self) -> None:
        event = BaseEvent()

        assert event.event_id.endswith(".BaseEvent")
        assert "." in event.event_id

    @pytest.mark.asyncio
    async def test_supports_sync_handlers(self) -> None:
        bus = AsyncEventBus()
        received: list[str] = []

        def handler(event: BaseEvent) -> None:
            received.append(event.event_type)

        await bus.subscribe(BaseEvent, handler)
        await bus.publish(BaseEvent())

        assert received == ["BaseEvent"]

    @pytest.mark.asyncio
    async def test_subscribe_by_short_event_type_string_remains_compatible(self) -> None:
        bus = AsyncEventBus()
        received: list[str] = []

        def handler(event: BaseEvent) -> None:
            received.append(event.event_type)

        await bus.subscribe("BaseEvent", handler)
        await bus.publish(BaseEvent())

        assert received == ["BaseEvent"]

    @pytest.mark.asyncio
    async def test_publish_cancelled_waits_sync_handler_thread(self) -> None:
        bus = AsyncEventBus()
        started = threading.Event()
        finished = threading.Event()

        def handler(event: BaseEvent) -> None:
            started.set()
            time.sleep(0.05)
            finished.set()

        await bus.subscribe(BaseEvent, handler)

        task = asyncio.create_task(bus.publish(BaseEvent()))
        await asyncio.sleep(0.05)
        assert started.wait(timeout=1.0), "El handler sincrónico no inició antes de cancelar"
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert finished.wait(timeout=1.0)

    @pytest.mark.asyncio
    async def test_multiple_handlers_receive_same_event(self) -> None:
        bus = AsyncEventBus()
        received: list[str] = []

        async def handler_one(event: BaseEvent) -> None:
            received.append("one")

        async def handler_two(event: BaseEvent) -> None:
            received.append("two")

        await bus.subscribe(BaseEvent, handler_one)
        await bus.subscribe(BaseEvent, handler_two)
        await bus.publish(BaseEvent())

        assert set(received) == {"one", "two"}
