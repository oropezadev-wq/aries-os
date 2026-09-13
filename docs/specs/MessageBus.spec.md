# MessageBus — Spec

> **BORRADOR — requiere aprobación.** Se desprende de `docs/specs/Routines.spec.md`
> sección 4 (cómo `RoutineManager`, en el proceso de la API, le avisa a
> `VoicePipeline`, proceso separado, que tiene que hablar algo). El
> usuario confirmó Redis Streams sobre pub/sub puro, y confirmó — vía
> `AskUserQuestion` — que esto es un contrato **nuevo y distinto** de
> `IEventBus` (no una generalización del existente). Cero código todavía.

## 1. Por qué no pub/sub puro (`PUBLISH`/`SUBSCRIBE`)

Redis pub/sub clásico no tiene persistencia: si `VoicePipeline` está
caído o reiniciando justo cuando `RoutineManager` publica, el mensaje se
pierde para siempre, sin que nadie se entere. Para una rutina tipo
"despertame" eso es exactamente el fallo silencioso que no queremos —
mejor unos segundos de demora (el consumidor lee el mensaje pendiente
apenas vuelve a levantar) que una pérdida sin aviso.

**Decisión: Redis Streams** (`XADD`/`XREADGROUP`/`XACK`) — un mensaje
publicado queda en el stream hasta que un consumidor de ese grupo lo
confirma (`XACK`); si el consumidor no estaba corriendo, lo lee apenas
vuelve. Es la pieza de Redis diseñada específicamente para este problema
(cola de mensajes con at-least-once delivery), no un uso improvisado de
pub/sub para simular algo que no es.

## 2. Por qué un contrato nuevo (`IMessageBus`), no generalizar `IEventBus`

Se le preguntó explícitamente al usuario (fork real, no ambigüedad
menor) si el bus de Redis Streams debía ser una nueva implementación del
`IEventBus` que ya existe (`contracts/event_bus.py`, in-process, tipado
sobre `BaseEvent`, usado hoy por `Kernel`/`Planner`/`PluginRegistry`), o
un contrato separado. **Se eligió contrato separado** (`IMessageBus`,
`docs/contracts/IMessageBus.md`). Motivos:
- Son dos problemas con forma distinta: `IEventBus.publish(event:
  BaseEvent)` es en memoria, dentro de un proceso, sin posibilidad real
  de "fallar por red" — nunca necesitó ack ni reintento. `IMessageBus`
  cruza un proceso real, con todo lo que eso implica (serialización,
  timeouts, reconexión, at-least-once).
- Unificarlos hubiera significado generalizar `publish()` a
  `topic`/`payload` genérico y adaptar `AsyncEventBus` (la implementación
  in-process real, usada en decenas de tests) a ese mismo lenguaje — un
  cambio disruptivo real a algo que ya funciona, solo para ahorrar un
  nombre de clase. No hay necesidad real hoy que lo justifique (mismo
  criterio que ya usa el proyecto para no fusionar cosas "parecidas" sin
  un caso concreto — ver `Voice.spec.md` sobre no crear un contrato de
  captura de audio).
- Quedan como dos conceptos explícitamente distintos y documentados como
  tales (ver la tabla comparativa en `docs/contracts/IMessageBus.md`) —
  no hay confusión de cuál usar para qué: eventos de dominio tipados
  dentro de un proceso siguen siendo `IEventBus`; mensajería confiable
  entre procesos es `IMessageBus`.

## 3. Qué pasa si Redis no está disponible al publicar

**Decisión: `publish()` nunca reintenta internamente — falla rápido con
`MessageBusError`, se loguea, y listo para esa llamada.** El reintento
es responsabilidad de quien llama, no del bus.

**Corrección respecto a la primera versión de este documento:** acá
decía "el tick de `Kernel.run()` ya es un mecanismo de reintento
natural" sin especificar qué hace que eso sea cierto — quedó como una
afirmación de prosa, no un diseño verificable, y es **falsa** si el
ancla que usa `croniter` para calcular la próxima ejecución se actualiza
apenas la rutina se evalúa como vencida (en vez de solo cuando se
confirma ejecutada con éxito): en ese caso un fallo a las 7:00 haría que
la próxima ejecución calculada fuera mañana a las 7:00, y el "reintento"
nunca pasaría — la falla silenciosa exacta que este documento existe
para evitar.

**El diseño real que hace cierto el argumento vive en
`docs/specs/Routines.spec.md` sección 1.1** (`RoutineRuntimeState`,
campos `last_fired_occurrence`/`pending_occurrence`) — no se repite acá
para no tener dos copias que puedan desincronizarse; en resumen:
`RoutineManager` separa "cuándo le toca a la rutina" (calculado por
`croniter`) de "si esa ocurrencia puntual ya se confirmó publicada"
(`pending_occurrence`, que no se limpia hasta que `publish()`/`dispatch()`
success). Mientras haya una ocurrencia pendiente, **todos** los ticks
reintentan esa misma ocurrencia — recién ahí "el tick es el reintento"
es una garantía real, no una esperanza sobre el cálculo de cron.

Agregar retry-with-backoff *dentro* de `publish()` seguiría siendo
innecesario con el diseño corregido — duplicaría un mecanismo de
reintento que ya existe un nivel más arriba. Consistente con el criterio
que ya usa el resto del proyecto (`IAgent.execute()`,
`PluginRegistry.load()`, `Planner.handle()`): nunca reintentar por su
cuenta dentro de una operación, loguear y dejar que la capa de arriba
decida.

**Política de "rutina vencida hace demasiado":** `routines_max_staleness_seconds`
(default sugerido 1800s/30 min, en `Settings`) — documentada con el
detalle completo en `Routines.spec.md` sección 1.1, incluido el límite
conocido de que este estado de reintento no sobrevive un reinicio del
proceso de la API (declarado a propósito, no silencioso).

## 4. Entrega al menos una vez — un `publish()` fallido puede haber escrito igual

**Riesgo concreto, no hipotético:** si `publish()` falla por timeout de
red (el cliente no recibe la confirmación de Redis a tiempo) pero el
`XADD` en realidad sí se ejecutó del lado del servidor, `RoutineManager`
ve una excepción y reintenta en el próximo tick (sección 3) — ese
reintento hace un **segundo** `XADD`, con la misma `SpeakAction` dos
veces en el stream. `VoicePipeline` la consume, la habla, hace `ack()`
dos veces — Aries diciendo "buenos días" dos veces seguidas.

**Decisión explícita para v1: se acepta.** No se implementa
deduplicación (ej. una idempotency key tipo
`f"{routine_id}:{occurrence.isoformat()}"` que el consumidor chequee
contra los últimos N mensajes vistos antes de actuar). Motivo: para
`SpeakAction`, la consecuencia de un duplicado (una frase corta repetida
una vez, en un escenario de timeout de red que además es poco frecuente)
es mucho menos grave que la pérdida silenciosa que todo este diseño
existe para evitar — priorizar "nunca perder" sobre "nunca duplicar" es
la decisión correcta para este caso de uso específico. **Esto no es
gratis en general** — si en el futuro `IMessageBus` transporta algo
donde un duplicado sí importa (ej. una acción que modifica estado, hoy
fuera de alcance de este bus — ver `Routines.spec.md` sección 9), hace
falta agregar la idempotency key antes de usarlo para eso. Anotado acá
para que quede como decisión tomada, no como algo que se descubre en
producción.

## 5. Política de retención del stream

**Nota importante, no obvia:** `XACK` **no borra el mensaje del stream**
— solo lo saca de la *Pending Entries List* del grupo de consumo. Sin
una política de retención aparte, el stream crece para siempre aunque
todo esté confirmado. Esto es un detalle real de Redis Streams, no una
decisión de diseño de este proyecto — si no se trunca, se acumula.

**Decisión: `MAXLEN ~ N` aproximado en cada `XADD`** (el `~` le pide a
Redis que trunque de forma eficiente, sin garantizar el límite exacto al
sample — es el uso recomendado por la documentación de Redis para no
pagar el costo de un trim exacto en cada escritura). `N` default
sugerido: **10000** — con el volumen esperado de mensajes de rutinas
(unos pocos por día), eso equivale a años de historial antes de
truncarse; generoso a propósito, configurable en el constructor de
`RedisStreamsMessageBus`, no hardcodeado.

## 6. Plan de archivos

- `src/aries/contracts/message_bus.py` — `IMessageBus`, `BusMessage`,
  `MessageBusError` (nueva excepción, o reusar `VoiceError`/agregar una
  genérica — a definir al implementar, no bloquea el diseño).
- `src/aries/messaging/redis_streams_bus.py` (paquete nuevo `messaging/`,
  mismo nivel que `memory/`/`llm/`/`voice/`) — `RedisStreamsMessageBus(IMessageBus)`,
  usa el `redis_url` que ya existe en `Settings` (declarado desde hace
  tiempo, sin consumidor real hasta ahora — este es el primero).
- `pyproject.toml` — dependencia nueva `redis` (cliente async oficial,
  `redis.asyncio`), en un extra propio (`messaging`) o en `voice`/base —
  a decidir junto con la implementación.
- `docs/contracts/IMessageBus.md` — ya escrito (este documento lo
  acompaña).

## Referencias
- `docs/specs/Routines.spec.md` sección 4 (de dónde sale la necesidad),
  sección 1.1 (`RoutineRuntimeState` — el diseño real detrás de "el tick
  es el reintento", sección 3 de este documento)
- `docs/contracts/IMessageBus.md` (contrato completo)
- `src/aries/contracts/event_bus.py` (`IEventBus` existente, contrato
  hermano pero deliberadamente separado — ver sección 2)
- `src/aries/config/settings.py` (`redis_url`, declarado sin consumidor
  hasta este documento)
