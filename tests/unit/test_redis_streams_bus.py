"""Tests de `RedisStreamsMessageBus` contra un Redis real (Streams no se
puede simular fielmente con un mock sin reimplementar su semántica de
consumer groups/PEL, que es justo lo que estos tests verifican) — mismo
criterio del proyecto de "tests reales donde se pueda".

Requieren un Redis alcanzable en `redis://localhost:6379/15` (DB 15,
para no pisar nada más) — si no hay uno corriendo, se skippean con un
mensaje claro en vez de fallar (entorno de CI/otra máquina sin Redis
instalado no debe romper la suite completa por esto)."""

from __future__ import annotations

import asyncio
import uuid

import pytest
import redis.asyncio as redis_asyncio
from redis.exceptions import RedisError

from aries.exceptions import MessageBusError
from aries.messaging.redis_streams_bus import RedisStreamsMessageBus

REDIS_URL = "redis://localhost:6379/15"


async def _redis_available() -> bool:
    try:
        client = redis_asyncio.Redis.from_url(REDIS_URL, socket_connect_timeout=2)
        await client.ping()
        await client.aclose()
        return True
    except RedisError:
        return False


@pytest.fixture
async def bus():
    if not await _redis_available():
        pytest.skip(f"Redis no alcanzable en {REDIS_URL} — se skippea la suite de RedisStreamsMessageBus")
    instance = RedisStreamsMessageBus(REDIS_URL)
    yield instance
    await instance.aclose()


@pytest.fixture
async def topic():
    """Un topic único por test para que no se pisen entre sí (comparten
    la misma DB de Redis)."""
    return f"test.{uuid.uuid4().hex}"


async def _next_message(gen, timeout: float = 5.0):
    return await asyncio.wait_for(anext(gen), timeout=timeout)


class TestPublishAckRoundTrip:
    @pytest.mark.asyncio
    async def test_publish_then_subscribe_receives_payload(self, bus: RedisStreamsMessageBus, topic: str) -> None:
        message_id = await bus.publish(topic, {"routine_id": "buenos-dias", "text": "Buenos días"})
        assert isinstance(message_id, str) and message_id

        gen = bus.subscribe(topic, group="g1", consumer="c1")
        message = await _next_message(gen)
        assert message.topic == topic
        assert message.payload == {"routine_id": "buenos-dias", "text": "Buenos días"}
        await bus.ack(topic, "g1", message.id)
        await gen.aclose()


class TestConsumerGroupFromOffsetZero:
    @pytest.mark.asyncio
    async def test_messages_published_before_group_exists_are_still_delivered(
        self, bus: RedisStreamsMessageBus, topic: str
    ) -> None:
        """MessageBus.spec.md sección 6.3 — el bug que se evita: crear el
        grupo desde `$` dejaría esto invisible para siempre."""
        await bus.publish(topic, {"n": 1})
        await bus.publish(topic, {"n": 2})

        gen = bus.subscribe(topic, group="g-late", consumer="c1")
        first = await _next_message(gen)
        second = await _next_message(gen)
        await gen.aclose()

        assert {first.payload["n"], second.payload["n"]} == {1, 2}


class TestOwnPendingEntriesReplay:
    @pytest.mark.asyncio
    async def test_unacked_message_is_redelivered_to_same_consumer_on_new_subscribe(
        self, bus: RedisStreamsMessageBus, topic: str
    ) -> None:
        """MessageBus.spec.md sección 6.4 — el escenario real: el
        consumidor lee, crashea antes de hacer ack(), y al reconectar con
        el MISMO nombre de consumidor tiene que recibir ese mensaje de
        nuevo, no perderlo."""
        await bus.publish(topic, {"n": 1})

        gen1 = bus.subscribe(topic, group="g1", consumer="stable-consumer")
        message = await _next_message(gen1)
        assert message.payload == {"n": 1}
        await gen1.aclose()  # simula un crash: nunca se llamó ack()

        gen2 = bus.subscribe(topic, group="g1", consumer="stable-consumer")
        redelivered = await _next_message(gen2)
        assert redelivered.payload == {"n": 1}
        assert redelivered.id == message.id  # mismo mensaje, no uno nuevo
        await bus.ack(topic, "g1", redelivered.id)
        await gen2.aclose()

    @pytest.mark.asyncio
    async def test_different_consumer_name_does_not_see_orphaned_pel(
        self, bus: RedisStreamsMessageBus, topic: str
    ) -> None:
        """Confirma la otra cara del mismo hallazgo: un nombre de
        consumidor distinto (equivalente a hostname+pid cambiando en
        cada reinicio) NO ve lo que quedó pendiente del anterior."""
        await bus.publish(topic, {"n": 1})

        gen1 = bus.subscribe(topic, group="g1", consumer="consumer-a")
        await _next_message(gen1)
        await gen1.aclose()  # sin ack

        gen2 = bus.subscribe(topic, group="g1", consumer="consumer-b")
        with pytest.raises(asyncio.TimeoutError):
            await _next_message(gen2, timeout=2.0)
        await gen2.aclose()


class TestPublishFailure:
    @pytest.mark.asyncio
    async def test_publish_raises_message_bus_error_when_redis_unreachable(self) -> None:
        unreachable_bus = RedisStreamsMessageBus("redis://localhost:1/0", reconnect_delay_seconds=0.1)
        with pytest.raises(MessageBusError):
            await unreachable_bus.publish("t", {"a": 1})
        await unreachable_bus.aclose()
