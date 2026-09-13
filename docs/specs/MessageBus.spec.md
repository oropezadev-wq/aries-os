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
fuera de alcance de este bus — ver `Routines.spec.md` sección 10), hace
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

## 6. Comportamiento del consumidor — la durabilidad de Streams es solo nominal si esto queda sin especificar

Toda la robustez diseñada hasta acá (secciones 3-5) es del lado de quien
publica. **Encontrado en revisión, hueco real, no cosmético:** si el
consumidor (`VoicePipeline`) no tiene estas cuatro cosas bien definidas,
la garantía de "at-least-once, nunca se pierde" que motivó elegir
Streams sobre pub/sub (sección 1) se rompe en la práctica, silenciosamente,
exactamente en el escenario que la motivó.

### 6.1 El staleness también tiene que viajar con el mensaje, no solo evaluarse al publicar

`routines_max_staleness_seconds` (sección 3) se evalúa en
`RoutineManager.check_due()` — es decir, **antes** de publicar. Pero el
escenario que justificó elegir Streams es exactamente el opuesto: Redis
arriba, `VoicePipeline` caído. Ahí `publish()` tiene éxito a las 7:00, el
mensaje queda persistido en el stream (que es lo que se buscaba),
`pending_occurrence` se limpia del lado del Kernel — todo correcto. Si
`VoicePipeline` recién levanta a las 13:00, `XREADGROUP` le entrega ese
mensaje igual, y lo habla a las 13:00. Es el resultado exacto que
`routines_max_staleness_seconds` existe para evitar, alcanzado por el
camino que Streams hace *más* probable (mensajes que sobreviven mucho
tiempo esperando), no menos.

**Decisión: el payload de `"routines.due"` lleva `valid_until` calculado
por el publisher al momento de publicar** (no un valor que el consumidor
tenga que recalcular con su propia copia de `routines_max_staleness_seconds`
— evita que las dos configuraciones, en dos procesos distintos, puedan
desincronizarse):

```json
{
  "routine_id": "buenos-dias",
  "occurrence": "2026-09-13T07:00:00+00:00",
  "valid_until": "2026-09-13T07:30:00+00:00",
  "text": "Buenos días"
}
```

`VoicePipeline`, en su loop de `subscribe()` (`docs/specs/Routines.spec.md`
sección 4), compara `now > valid_until` **antes** de sintetizar/hablar —
si ya venció, descarta sin hablar, loguea, y **igual hace `ack()`**
(sección 6.2: un mensaje vencido ya se decidió no honrar, dejarlo sin
ack lo dejaría reintentándose para siempre en el PEL sin motivo). Este
payload y este chequeo viven documentados acá porque tocan la forma del
mensaje — cambiarlo después de implementado sería un cambio de contrato
entre `RoutineManager` y `VoicePipeline`, no un detalle interno de
ninguno de los dos por separado.

### 6.2 Cuándo se hace `XACK`

**Decisión: después de terminar de hablar, nunca al leer.** Si el
`ack()` pasara apenas se lee el mensaje (antes de sintetizar/reproducir)
y `VoicePipeline` crashea a mitad de la síntesis, el mensaje ya estaría
confirmado — perdido para siempre, y toda la elección de Streams sobre
pub/sub no habría servido de nada. Con `ack()` después de terminar: si
crashea a mitad, el mensaje queda en el *Pending Entries List* del
grupo, sin confirmar, y se vuelve a entregar cuando el consumidor
levanta de nuevo (sección 6.4) — un "buenos días" repetido en el peor
caso, consistente con la decisión ya tomada en la sección 4 (preferir
duplicar antes que perder). Tiene que quedar escrito así explícitamente
porque el orden inverso (ack-then-speak) es la forma más natural de
escribir el loop y produce el resultado exactamente opuesto al que se
diseñó todo esto para lograr.

### 6.3 Quién crea el consumer group, y desde qué offset

**Decisión: el propio `subscribe()` de `RedisStreamsMessageBus` crea el
grupo de forma idempotente, la primera vez que se llama, con
`XGROUP CREATE <topic> <group> 0 MKSTREAM`** — no algo que dependa de
qué proceso arranca primero:
- **`MKSTREAM`**: crea el stream si todavía no existe, evitando una
  carrera real si `VoicePipeline` es el primer proceso en arrancar (sin
  esto, `XGROUP CREATE` fallaría porque el stream no existe todavía si
  `RoutineManager` nunca publicó nada).
- **Offset `0`, no `$`**: `$` (el default implícito si no se piensa en
  esto) solo hace visibles al grupo los mensajes publicados *después* de
  crear el grupo — cualquier cosa publicada antes queda invisible para
  siempre. Con `0`, el grupo ve todo el historial del stream desde el
  principio, incluido lo publicado antes de que `VoicePipeline` se
  conectara por primera vez.
- **Idempotente**: `XGROUP CREATE` sobre un grupo que ya existe devuelve
  el error `BUSYGROUP` — `RedisStreamsMessageBus` lo captura y lo ignora
  explícitamente (no es una condición de error real, es el caso normal
  en cualquier reconexión). `publish()` no necesita saber nada de grupos
  — `XADD` funciona sobre un stream sin consumer groups sin problema, así
  que no hace falta coordinar nada del lado de `RoutineManager`.

### 6.4 Nombre de consumidor estable + recuperar el PEL propio al arrancar

**Decisión: nombre de consumidor fijo/configurable, nunca `hostname+pid`
ni nada que cambie entre reinicios.** Si el nombre cambia en cada
arranque, cualquier mensaje que haya quedado en el PEL del consumidor
*anterior* (crasheó después de leer, antes de hacer `ack()`) queda
huérfano — nadie con ese nombre vuelve a pedirlo, y no se reclama solo.
Para v1 (un solo proceso `VoicePipeline` corriendo por vez, sección 6.3
implícitamente asume esto) alcanza con un nombre fijo, ej. `"voice-pipeline"`
(configurable en `Settings` si hace falta correr más de una instancia
algún día, no necesario ahora).

**Al arrancar, antes de pasar a leer mensajes nuevos, `subscribe()` hace
un `XREADGROUP` con id `"0"` (no `">"`) una vez** — con id `"0"`, Redis
devuelve los mensajes que ya estaban en el PEL *de ese mismo nombre de
consumidor* de una corrida anterior (los que quedaron sin `ack()` por un
crash), no mensajes nuevos. Se procesan (con el mismo criterio de
staleness de 6.1) y se hace `ack()` como a cualquier otro, y recién
después el loop pasa a pedir mensajes nuevos con `">"`. Esto alcanza
para v1 porque hay un solo consumidor con nombre fijo; si en el futuro
hay más de una instancia consumiendo el mismo grupo a la vez, la
herramienta correcta para reclamar el PEL de un consumidor *distinto*
que murió es `XAUTOCLAIM` — anotado como extensión futura, no
implementado ahora porque no hay un segundo consumidor real todavía
(mismo criterio que el resto de este documento: no construir para un
caso que no existe).

## 7. Plan de archivos

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
