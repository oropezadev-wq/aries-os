"""messaging/redis_streams_bus.py — `RedisStreamsMessageBus(IMessageBus)`.

Implementación real de `IMessageBus` (`docs/contracts/IMessageBus.md`)
sobre Redis Streams — ver `docs/specs/MessageBus.spec.md` para el
razonamiento completo de cada decisión referenciada en los comentarios
de este archivo (por qué Streams y no pub/sub, política de reintento,
retención, comportamiento del consumidor).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, cast

import redis.asyncio as redis
from redis.exceptions import RedisError, ResponseError

from ..contracts.message_bus import BusMessage, IMessageBus
from ..exceptions import MessageBusError
from ..logging import get_logger

logger = get_logger("messaging.redis_streams_bus")

_PAYLOAD_FIELD = "payload"

# Forma real de la respuesta de `XREADGROUP` con `decode_responses=True`:
# una lista de (nombre_de_stream, [(id_de_entrada, {campo: valor}), ...]).
# Los stubs de redis-py la tipan como `Any`/`ResponseT` genérico — se
# castea acá, una sola vez, en vez de perder el tipado en cada uso.
_XReadGroupResponse = list[tuple[str, list[tuple[str, dict[str, str]]]]]


class RedisStreamsMessageBus(IMessageBus):
    """`publish` → `XADD` (con `MAXLEN ~` para retención, sección 5 de
    MessageBus.spec.md). `subscribe` → asegura el consumer group de
    forma idempotente desde el offset `0` (sección 6.3), repone el PEL
    propio del consumidor antes de leer mensajes nuevos (sección 6.4), y
    reintenta la conexión con backoff fijo ante una caída transitoria de
    Redis. `ack` → `XACK`.
    """

    def __init__(
        self,
        redis_url: str,
        *,
        maxlen: int = 10000,
        reconnect_delay_seconds: float = 2.0,
    ) -> None:
        self._redis_url = redis_url
        self._maxlen = maxlen
        self._reconnect_delay_seconds = reconnect_delay_seconds
        self._client: redis.Redis | None = None

    def _get_client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.Redis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def publish(self, topic: str, payload: dict[str, Any]) -> str:
        client = self._get_client()
        try:
            message_id = await client.xadd(
                topic,
                {_PAYLOAD_FIELD: json.dumps(payload)},
                maxlen=self._maxlen,
                approximate=True,
            )
        except RedisError as error:
            raise MessageBusError(f"No se pudo publicar en '{topic}': {error}") from error
        return str(message_id)

    async def _ensure_group(self, client: redis.Redis, topic: str, group: str) -> None:
        """`XGROUP CREATE` idempotente desde el offset `0` (no `$`) —
        MessageBus.spec.md sección 6.3: con `$` cualquier mensaje
        publicado antes de crear el grupo queda invisible para siempre;
        `MKSTREAM` evita una carrera si el topic todavía no existe."""
        try:
            await client.xgroup_create(topic, group, id="0", mkstream=True)
        except ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise

    async def subscribe(self, topic: str, group: str, consumer: str) -> AsyncIterator[BusMessage]:
        replayed_own_pel = False
        while True:
            try:
                client = self._get_client()
                await self._ensure_group(client, topic, group)

                if not replayed_own_pel:
                    # MessageBus.spec.md sección 6.4: antes de pedir mensajes
                    # nuevos, reclama lo que haya quedado en el PEL de ESTE
                    # MISMO `consumer` de una corrida anterior (crash entre
                    # leer y hacer ack()) — id "0" en vez de ">".
                    response = cast(
                        _XReadGroupResponse,
                        await client.xreadgroup(group, consumer, streams={topic: "0"}, count=100),
                    )
                    for _stream_name, entries in response or []:
                        for entry_id, fields in entries:
                            yield self._to_bus_message(topic, entry_id, fields)
                    replayed_own_pel = True

                while True:
                    response = cast(
                        _XReadGroupResponse,
                        await client.xreadgroup(group, consumer, streams={topic: ">"}, count=10, block=5000),
                    )
                    for _stream_name, entries in response or []:
                        for entry_id, fields in entries:
                            yield self._to_bus_message(topic, entry_id, fields)
            except RedisError as error:
                logger.warning(
                    "IMessageBus.subscribe: error de Redis, reintentando conexión",
                    topic=topic,
                    group=group,
                    error=str(error),
                )
                self._client = None
                replayed_own_pel = False
                await asyncio.sleep(self._reconnect_delay_seconds)

    def _to_bus_message(self, topic: str, entry_id: str, fields: dict[str, str]) -> BusMessage:
        payload = json.loads(fields[_PAYLOAD_FIELD])
        return BusMessage(id=entry_id, topic=topic, payload=payload)

    async def ack(self, topic: str, group: str, message_id: str) -> None:
        client = self._get_client()
        try:
            await client.xack(topic, group, message_id)
        except RedisError as error:
            raise MessageBusError(f"No se pudo confirmar '{message_id}' en '{topic}': {error}") from error
