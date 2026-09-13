# Contrato: IMessageBus

## Responsabilidad
Entrega de mensajes **confiable, entre procesos distintos** (ej. el
proceso de la API/`Kernel` y el proceso de `VoicePipeline`) — deliberadamente
**no** es el mismo contrato que `IEventBus` (`src/aries/contracts/event_bus.py`).
Son dos problemas distintos, no dos implementaciones del mismo problema:

| | `IEventBus` (ya existe) | `IMessageBus` (este contrato) |
|---|---|---|
| Alcance | Un solo proceso | Entre procesos distintos |
| Payload | `BaseEvent` tipado (dataclass) | `dict` serializable (JSON) |
| Entrega | Síncrona, en memoria, garantizada mientras el proceso viva | Puede fallar/demorarse — el consumidor puede estar caído |
| Semántica de fallo | No aplica (no hay red de por medio) | Necesita ack explícito — si el consumidor se cae a mitad de procesar, el mensaje no se pierde |
| Consumido por | Kernel, Planner, PluginRegistry (eventos de dominio ya tipados) | `RoutineManager` → `VoicePipeline` (mensajes cross-proceso) |

Ver `docs/specs/MessageBus.spec.md` para el razonamiento completo de por
qué son contratos separados y no una generalización de `IEventBus`.

**Diseñado para que la implementación sea reemplazable** — mismo espíritu
que `ILLMProvider`/`ITTSProvider`: la primera implementación real usa
Redis Streams (`RedisStreamsMessageBus`), pero nada en el contrato asume
Redis específicamente (nombres de métodos genéricos, no `xadd`/`xack`).

## Modelo de datos

```python
@dataclass(frozen=True)
class BusMessage:
    id: str                    # id único asignado por el bus al publicar
    topic: str
    payload: dict[str, Any]
```

## Métodos Requeridos

### async publish(topic, payload) → str
Publica un mensaje en `topic`. Devuelve el `id` asignado por el bus
(en la implementación Redis, el ID de entrada del stream).

**Parámetros:**
- `topic` (str): nombre del canal/stream. Convención: `"dominio.evento"`
  (ej. `"routines.due"`), en minúsculas con puntos — mismo estilo que ya
  usan los nombres de clase de `BaseEvent` pero en formato string plano.
- `payload` (dict): debe ser JSON-serializable. El contrato no valida
  estructura — quien publica y quien consume acuerdan el shape del
  payload por convención (documentado donde se usa, ej.
  `docs/specs/Routines.spec.md`), igual que `ActionResult.data` no está
  tipado por acción.

**Excepciones:**
- `MessageBusError`: el bus no está disponible (ej. Redis caído/no
  alcanzable). **Nunca se reintenta dentro de `publish()`** — ver
  `docs/specs/MessageBus.spec.md` para la política de reintento, que es
  responsabilidad de quien llama (`RoutineManager`), no del bus.

### subscribe(topic, group, consumer) → AsyncIterator[BusMessage]
Devuelve un iterador asíncrono de mensajes nuevos en `topic` para el
grupo de consumo `group`. **No hace ack automático** — el llamador debe
llamar `ack()` explícitamente después de procesar cada mensaje con
éxito. Si el proceso consumidor se cae antes de acked, el mensaje queda
pendiente y se vuelve a entregar cuando el consumidor (u otro del mismo
grupo) vuelve a `subscribe()` — es la garantía central de este contrato,
la razón por la que existe en vez de reusar `IEventBus`.

**Parámetros:**
- `topic` (str): igual que en `publish()`.
- `group` (str): nombre del grupo de consumo — permite que, si en el
  futuro hay más de un consumidor del mismo topic, cada mensaje se
  procese una sola vez por grupo (no una vez por consumidor individual).
- `consumer` (str): identidad de este consumidor dentro del grupo.
  **Debe ser estable entre reinicios del proceso — nunca `hostname+pid`
  ni nada que cambie en cada arranque.** Si cambia, cualquier mensaje que
  haya quedado sin `ack()` en el consumidor anterior (crasheó a mitad de
  procesar) queda huérfano — nadie con ese nombre vuelve a pedirlo. Para
  v1 (un consumidor por grupo) un string fijo alcanza (ver
  `docs/specs/MessageBus.spec.md` sección 6.4 para el detalle completo,
  incluida la recuperación del propio PEL al arrancar).

**Uso esperado:**
```python
async for message in bus.subscribe("routines.due", group="voice-pipeline", consumer="main"):
    await handle(message.payload)
    await bus.ack("routines.due", "voice-pipeline", message.id)
```

**Comportamiento si el bus no está disponible al momento de iterar:**
implementación-dependiente (ver `docs/specs/MessageBus.spec.md`) — para
`RedisStreamsMessageBus`, el iterador reintenta la conexión con backoff
en vez de terminar, porque un consumidor de larga vida (`VoicePipeline`)
no debe caerse por una caída transitoria de Redis.

**Al empezar a iterar, antes de entregar cualquier mensaje `subscribe()`
debe:** (1) asegurar que el `group` existe de forma idempotente, viendo
todo el historial del topic desde el principio (no solo lo publicado a
partir de ahora); (2) reclamar y entregar primero cualquier mensaje que
haya quedado pendiente de una corrida anterior de este mismo `consumer`
(un crash entre leer y hacer `ack()`), antes de pasar a mensajes nuevos.
Sin esto, "at-least-once" es una promesa solo nominal — el detalle
mecánico completo (comandos Redis exactos, por qué cada uno) está en
`docs/specs/MessageBus.spec.md` sección 6.3/6.4, no repetido acá.

### async ack(topic, group, message_id) → None
Confirma que `message_id` se procesó — lo remueve de la lista de
mensajes pendientes del grupo. **No borra el mensaje del topic/stream**
(ver nota de retención en `docs/specs/MessageBus.spec.md`) — ack y
retención son mecanismos independientes.

**Se llama después de terminar de procesar el mensaje, nunca al
leerlo** — ver `docs/specs/MessageBus.spec.md` sección 6.2 para el
motivo (acked-antes-de-procesar pierde el mensaje si el consumidor
crashea a mitad de camino; ese es exactamente el escenario que este
contrato existe para no perder).

## Implementaciones Conocidas
- **`RedisStreamsMessageBus`** (`src/aries/messaging/redis_streams_bus.py`,
  no implementada todavía — ver `docs/specs/MessageBus.spec.md`) —
  `publish` → `XADD` (con `MAXLEN ~` para retención), `subscribe` →
  `XGROUP CREATE ... 0 MKSTREAM` idempotente + replay del PEL propio con
  `XREADGROUP ... "0"` + loop de `XREADGROUP ... ">"` para mensajes
  nuevos (sección 6.3/6.4 de `MessageBus.spec.md`), `ack` → `XACK`.
- Ninguna otra implementación planeada por ahora — a diferencia de
  `ITTSProvider`/`ILLMProvider` (donde ya hay un candidato de pago
  concreto, ej. ElevenLabs/OpenAI), acá no hay un segundo backend real
  en el horizonte; el contrato existe para no acoplar `RoutineManager`/
  `VoicePipeline` a la librería `redis` directamente, no porque haya un
  swap concreto planeado.

## Casos de Uso

**Publicar una rutina vencida (`RoutineManager`, proceso de la API) —
`occurrence`/`valid_until` son parte del payload por convención de
`"routines.due"`, ver `docs/specs/MessageBus.spec.md` sección 6.1:**
```python
await bus.publish("routines.due", {
    "routine_id": "buenos-dias",
    "occurrence": occurrence.isoformat(),
    "valid_until": (occurrence + timedelta(seconds=settings.routines_max_staleness_seconds)).isoformat(),
    "text": "Buenos días",
})
```

**Consumir y hablar (`VoicePipeline`, proceso separado) — descarta si
venció, sólo si no ack de todas formas (sección 6.1/6.2):**
```python
async for message in bus.subscribe("routines.due", group="voice-pipeline", consumer="main"):
    if datetime.now(UTC) > datetime.fromisoformat(message.payload["valid_until"]):
        self.logger.warning("Rutina vencida, se descarta sin hablar", routine_id=message.payload["routine_id"])
    else:
        await self._speak(message.payload["text"])
    await bus.ack("routines.due", "voice-pipeline", message.id)
```

## Restricciones
- El payload debe ser JSON-serializable — nada de objetos Python
  arbitrarios (a diferencia de `IEventBus`, que mueve instancias de
  `BaseEvent` tal cual dentro del mismo proceso).
- `subscribe()` es de larga duración (un loop, no una llamada que
  vuelve) — quien lo consume debe correrlo como una task de fondo
  (`asyncio.create_task`), nunca bloquear el loop principal esperándolo.
- Ningún consumidor debe asumir que un mensaje se entrega una sola vez
  en total — la garantía es **al menos una vez** (si un handler falla
  después de hacer efecto pero antes del `ack()`, al reconectar se
  vuelve a entregar). Los handlers deben ser idempotentes o tolerar
  reprocesamiento — para `SpeakAction`, decir la misma frase dos veces
  ante una reconexión rara es aceptable; no lo sería para una acción que
  modifique estado (fuera de alcance de este bus en v1, que solo
  transporta `SpeakAction`s — ver `docs/specs/Routines.spec.md`).
