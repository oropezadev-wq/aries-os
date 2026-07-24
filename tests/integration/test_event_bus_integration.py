from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from aries.events import AsyncEventBus, BaseEvent, EventPublisher, EventSubscriber


class TestEventBusIntegration:
    @pytest.mark.asyncio
    async def test_publisher_and_subscriber_integration(self) -> None:
        bus = AsyncEventBus()
        publisher = EventPublisher(bus)
        subscriber = EventSubscriber(bus)
        received: list[str] = []

        @dataclass(frozen=True)
        class SampleEvent(BaseEvent):
            payload: dict[str, str] = field(default_factory=dict)

        async def handler(event: BaseEvent) -> None:
            received.append(event.event_type)

        await subscriber.subscribe(SampleEvent, handler)
        await publisher.publish(SampleEvent())

        assert received == ["SampleEvent"]
