# ADR-002

Decisión: Aries adopta explícitamente un plan de dos fases — Fase 1
(actual, en curso): asistente personal single-tenant. Fase 2 (futura, no
iniciada): generalización multi-tenant.

Estado: Aceptado

## Contexto

Aries nació (`docs/archive/vision-original-saas/`) como una plataforma
SaaS multi-tenant de agentes operativos verticales. El proyecto pivotó a
construir primero un asistente personal de escritorio (single-tenant, un
usuario, un proceso, hardware real) para validar el motor central
(Kernel, Planner, agentes, EventBus, Voice, Routines, Message Bus) antes
de generalizarlo. `docs/VISION.md` ya documenta esto como dos fases del
mismo proyecto, no como visiones en competencia. Este ADR eleva esa
decisión a un registro formal — hasta ahora no existía ningún ADR
vigente sobre tenancy (los 7 ADRs originales sobre el tema, incluido
`ADR-007-multi-tenancy-first`, quedaron archivados sin re-ratificarse ni
rechazarse formalmente en `docs/adr/`).

## Decisión

1. Fase 1 (actual) es explícitamente single-tenant. No se generaliza
   nada a multi-tenant hasta que el criterio de éxito de la Fase 1
   (`docs/VISION.md`) se cumpla.
2. Fase 2 (futura, no iniciada) generaliza el mismo motor a
   multi-tenant. No se planifica en detalle todavía.
3. Se registran acá, como **estado actual válido para la Fase 1** (no
   como deuda a resolver ya), las decisiones single-tenant que Fase 2
   eventualmente va a requerir revisar. Cada una se verificó contra el
   código real al escribir este documento (no se asumió):

### 3.1 — `IMemory` sin dimensión de tenant en su firma

Verificado en `src/aries/contracts/memory.py`: `store()`, `retrieve()`,
`search()`, `get_by_type()` y `clear_expired()` no reciben ningún
parámetro de tenant/organización — es un espacio de nombres plano, no
uno particionado con un filtro opcional. Agregar tenancy más adelante
implica cambiar la firma del contrato, no solo su implementación
(`SQLiteMemoryStore`).

### 3.2 — Singletons de módulo en `api.py`

Verificado en `src/aries/api.py` (líneas 44-50): `_agent_manager`,
`_event_bus`, `_memory` y `_message_bus` se construyen una única vez al
importar el módulo y son compartidos, sin ninguna dimensión de tenant,
por absolutamente todos los requests/consumidores del proceso durante
toda su vida. (Nota de precisión, no cambia la conclusión: `_kernel` y
`_llm_provider` ya no se construyen a nivel de módulo — desde el
refactor a `lifespan()`, se reconstruyen una vez por ciclo de arranque
de la app y se reasignan a esos globals por compatibilidad con
`get_planner()` y los tests de integración. Sigue habiendo una única
instancia activa compartida por todo el proceso en un momento dado,
nunca una por tenant.)

### 3.3 — `IEventBus` in-process

Verificado en `src/aries/contracts/event_bus.py` y
`src/aries/events/event_bus.py`: `AsyncEventBus` guarda los handlers en
un `dict` en memoria del propio proceso (`self._handlers`). No hay
transporte de eventos entre procesos ni ninguna dimensión de tenant en
la interfaz `publish()`/`subscribe()`/`unsubscribe()`.

### 3.4 — Nombre de consumidor y consumer group hardcodeados en Voice↔Routines

Verificado en `src/aries/voice/pipeline.py` (líneas 35-36):
`ROUTINES_CONSUMER_GROUP = "voice-pipeline"` y
`ROUTINES_CONSUMER_NAME = "main"`, usados tal cual en
`_consume_routines()`. Esto ya está implementado, no es solo una
decisión de spec: `src/aries/messaging/redis_streams_bus.py` (la
implementación real de `IMessageBus` sobre Redis Streams) existe y está
en uso. El contrato `IMessageBus` en sí es genérico (no asume un único
consumidor), pero este uso concreto sí asume un solo proceso
`VoicePipeline` corriendo a la vez — documentado también en
`docs/specs/MessageBus.spec.md` sección 6.4.

## Consecuencias

- Ninguno de los cuatro puntos de la sección 3 se toca ahora. Son
  single-tenant por decisión válida para la Fase 1, no por descuido, y
  quedan así hasta que la Fase 2 se planifique en serio.
- Cuando llegue ese momento, los cuatro son los puntos de partida
  concretos a revisar (en distinto grado: 3.1 y 3.3 requieren cambiar la
  firma de un contrato; 3.2 requiere una estrategia de aislamiento por
  tenant a nivel de proceso/instancia; 3.4 requiere generalizar nombre de
  consumidor/grupo si se corre más de una instancia de `VoicePipeline`).
- Este ADR no autoriza ni bloquea ningún trabajo de Fase 2 — solo deja
  registrado el estado actual para que la futura planificación no
  empiece de cero.
