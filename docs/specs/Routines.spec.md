# Routines (comportamiento proactivo) — Spec

> **BORRADOR — decisiones 1-3 y 4 (mecanismo) confirmadas por el usuario
> el 2026-09-13; sección 4 detallada en un documento aparte.** Escrito a
> partir del código real existente (`core/kernel.py`,
> `contracts/event_bus.py`, `agents/manager.py`, `voice/pipeline.py`,
> `contracts/tts.py`) y del mismo patrón de `docs/specs/Voice.spec.md`/
> `docs/specs/Planner.spec.md`. **Cero código todavía** — instrucción
> explícita: revisar el diseño antes de escribir una sola línea de
> `routines/`.
>
> Criterio general dado por el usuario para este proyecto: priorizar
> robustez/escalabilidad y evitar retrabajo futuro, aunque cueste más
> esfuerzo ahora — condicionó las decisiones 1 y 4 (cron completo desde
> el día uno en vez de un formato simple a migrar después; Redis Streams
> con garantía de entrega en vez de pub/sub puro).

## Objetivo

Que Aries pueda iniciar una interacción sin que el usuario hable primero
— "despertarlo" por horario o por condición del sistema, no solo
reaccionar a la wake word. Ejemplos concretos que este diseño debe cubrir:
- "Todos los días a las 7am, decime buenos días y el clima" (hablar)
- "Cuando arranca el sistema, corré `git status` en tal repo y avisame si
  hay cambios sin commitear" (ejecutar agente + hablar el resultado)
- "Cada 30 minutos, corré un backup" (agente solo, sin voz)

## Contexto: qué ya existe y qué no

- **`Kernel.run()` ya tiene un bucle de fondo real** (`core/kernel.py`):
  `while not stop_event.is_set(): housekeeping(); wait(interval)`. Hoy
  solo llama `memory.clear_expired()`. Es el patrón exacto de "algo que
  se ejecuta solo, periódicamente, en el proceso de la API" — ya
  resuelto, no hay que reinventarlo.
- **`IEventBus`/`AsyncEventBus` ya existen** (`contracts/event_bus.py`,
  `events/`), en memoria, **dentro de un solo proceso**. No hay ningún
  transporte de eventos entre procesos (`redis_url` está declarado en
  `Settings` pero sin un solo consumidor real todavía — ver PROGRESS.md).
  Esto importa mucho para la sección 4.
- **`AgentManager` ya existe y corre en el proceso de la API** (`_agent_manager`
  en `api.py`, el mismo que usa el Planner y el que carga plugins vía
  `Kernel.initialize()`). `dispatch(agent_name, action, **kwargs) ->
  ActionResult` es el punto de entrada — no necesita pasar por el Planner
  ni por un LLM.
- **`ITTSProvider`/`PiperProvider` solo existen dentro del proceso de
  `VoicePipeline`** (`python -m aries.voice`), un **proceso separado** del
  de la API — decisión 2 de `Voice.spec.md`, a propósito: micrófono/parlante
  son hardware de la máquina del usuario, y `api.py`/`Kernel` corren hoy
  perfectamente en un servidor headless sin ningún dispositivo de audio.
  **El proceso de la API no tiene forma de "hablar" hoy.** Esta es la
  tensión arquitectónica central de este documento — ver sección 4.
- **`VoicePipeline` es 100% reactivo hoy**: `run_forever()` bloquea
  esperando la wake word, nunca inicia nada por su cuenta. No tiene
  ningún timer ni loop concurrente.
- **No existe nada parecido a un scheduler/cron en el proyecto.** No hay
  dependencia de ese tipo declarada en `pyproject.toml`.

## 1. Alcance de v1 — qué tipo de "cuándo" se soporta

**`[CONFIRMADO]` Cron completo desde el día uno, vía `croniter`
(parseo + cálculo de próxima ejecución) — no un formato simple a migrar
después.** Motivo del usuario: evitar reescribir el esquema de rutinas
el día que haga falta algo más que horario fijo (intervalos, días
sueltos no recurrentes, múltiples horarios) — el costo de croniter desde
ahora es bajo (una dependencia chica, sin motor de scheduling propio:
`RoutineManager` sigue siendo quien decide cuándo chequear y qué hacer,
`croniter` solo calcula "¿cuál es la próxima vez que esta expresión
dispara?"). Se descarta `APScheduler` explícitamente — trae su propio
motor de scheduling (threads/jobstores propios), que duplicaría el bucle
que `Kernel.run()` ya tiene (sección 5); `croniter` es solo una función
de cálculo, no un framework.

**`on_startup` queda separado de cron, no dentro de la expresión** —
cron (incluso con extensiones tipo `@reboot` de algunos dialectos) no
tiene un concepto de "next fire time" calculable con `croniter` para
"cuando arranca el sistema": es un disparo único al iniciar el Kernel,
no algo recurrente en el tiempo.

```python
@dataclass(frozen=True)
class RoutineDefinition:
    id: str
    action: RoutineAction
    cron: str | None = None       # expresión cron de 5 campos, ej. "0 7 * * 1-5"
    on_startup: bool = False      # dispara una vez al iniciar el Kernel
    enabled: bool = True
    # Exactamente uno de `cron`/`on_startup` debe estar seteado — se
    # valida en loader.py, no en el dataclass (mismo criterio que
    # `parse_manifest()` valida `PluginMetadata` después de construirla).
```

**Atajos para no escribir cron a mano** (lo que el usuario pidió
explícitamente): el **archivo** de una rutina (sección 3) puede declarar
`schedule` de forma amigable en vez de `cron` directo — `loader.py`
lo traduce a la expresión cron equivalente al cargar, antes de construir
`RoutineDefinition`:

```json
{
  "id": "buenos-dias",
  "schedule": {"time": "07:00", "days_of_week": [0, 1, 2, 3, 4]},
  "action": {"type": "speak", "text": "Buenos días"}
}
```

`days_of_week` en el atajo usa **convención ISO/Python (0=lunes...6=domingo)**,
no la convención de cron (0=domingo...6=sábado, con 7 también válido
como domingo) — `loader.py` es responsable de traducir correctamente
entre las dos (`cron_dow = (iso_dow + 1) % 7`), documentado ahí mismo con
una tabla, para no dejarlo como una conversión implícita que alguien
tiene que redescubrir leyendo el código. Un usuario avanzado puede
saltear el atajo y escribir `"cron": "*/15 9-18 * * *"` directo en el
archivo — ambos caminos terminan en el mismo campo `cron` de
`RoutineDefinition`.

### 1.1 Estado de reintento — explícito, no implícito en cómo se calcula `croniter.get_next()`

**Esto quedó mal explicado en la primera vuelta de este documento** (la
sección 3 de `MessageBus.spec.md` decía "el tick ya es un reintento
natural" sin especificar qué ancla usa `croniter` para calcular la
próxima ejecución) — si el ancla que le pasás a
`croniter(cron, ancla).get_next()` se actualiza apenas la rutina se
evalúa como "vencida" (sin importar si `publish()`/`dispatch()` tuvo
éxito), el argumento es falso: la próxima ejecución calculada ya sería
mañana a la misma hora, y un fallo a las 7:00 no se reintenta nunca en
el mismo día — exactamente la falla silenciosa que este documento existe
para evitar. Corregido acá con un estado explícito por rutina:

```python
@dataclass
class RoutineRuntimeState:
    """Estado mutable en memoria, por rutina — vive en RoutineManager,
    separado de RoutineDefinition (inmutable, cargada de disco).
    NO se persiste entre reinicios del proceso en v1 — ver nota al final."""

    last_fired_occurrence: datetime | None = None
    # La ocurrencia de cron que se ejecutó CON ÉXITO por última vez — el
    # ancla real que usa croniter.get_next(). Se actualiza ÚNICAMENTE
    # cuando la acción se confirma completada: AgentAction -> dispatch()
    # volvió sin excepción; SpeakAction -> IMessageBus.publish() devolvió
    # un id. NUNCA se actualiza solo por evaluar la rutina como vencida.

    pending_occurrence: datetime | None = None
    # Si no es None: hay una ocurrencia vencida que ya se intentó
    # ejecutar y todavía no se confirmó con éxito. Mientras este campo
    # no sea None, el tick reintenta ESA MISMA ocurrencia (no recalcula
    # una nueva) — ver check_due() abajo.
```

```python
def check_due(self, now: datetime) -> None:
    for routine in self._routines.values():
        if not routine.enabled:
            continue
        state = self._state[routine.id]  # una RoutineRuntimeState por rutina

        if state.pending_occurrence is not None:
            occurrence = state.pending_occurrence  # reintento: misma ocurrencia
        else:
            anchor = state.last_fired_occurrence or routine.loaded_at
            occurrence = self._next_occurrence(routine, anchor)  # on_startup: una sola vez
            if occurrence is None or occurrence > now:
                continue  # todavía no le toca
            state.pending_occurrence = occurrence

        if (now - occurrence).total_seconds() > self.settings.routines_max_staleness_seconds:
            self._publish_event(RoutineFailedEvent(routine_id=routine.id, error="stale, descartada"))
            state.last_fired_occurrence = occurrence  # no reintentar algo ya declarado perdido
            state.pending_occurrence = None
            continue

        if self._try_execute(routine):  # dispatch()/publish() sin excepción
            state.last_fired_occurrence = occurrence
            state.pending_occurrence = None
        # si falla: pending_occurrence queda seteado -> el próximo tick
        # (routines_check_interval_seconds) reintenta la MISMA ocurrencia
```

Con esto, "el tick es el reintento" es una afirmación verificable en el
código, no una esperanza sobre cómo se calcula el próximo horario:
mientras `pending_occurrence` no sea `None`, todos los ticks reintentan
esa ocurrencia puntual hasta éxito o hasta
`routines_max_staleness_seconds` — el cálculo de "cuándo es la próxima
vez" ni se toca mientras haya un pendiente.

**Límite conocido, declarado a propósito (no silencioso):**
`RoutineRuntimeState` vive en memoria del proceso de la API, **no se
persiste**. Si el `Kernel` se reinicia con una ocurrencia `pending`
(ej. Redis estuvo caído, el reintento seguía en curso), ese estado se
pierde — al volver a levantar, el ancla vuelve a ser `routine.loaded_at`
(el momento del reinicio) y `croniter` calcula la próxima ejecución
futura desde ahí, sin recordar que había algo pendiente de antes del
reinicio. Robustece contra "Redis caído" y "VoicePipeline caído"
(ambos sobreviven gracias a Streams + este estado de reintento); **no**
robustece contra "el proceso de la API se reinicia mientras hay un
pendiente" — ese caso puntual sigue siendo una pérdida silenciosa en v1.
Si se vuelve un problema real, la mitigación es persistir
`RoutineRuntimeState` (SQLite, mismo patrón que `SQLiteMemoryStore`) —
no implementado ahora porque no hay evidencia de que el proceso de la
API se reinicie con la frecuencia suficiente para que valga la pena
hoy.

## 2. ¿`RoutineManager` necesita un contrato (`IRoutineManager`)? `[CONFIRMADO]`

**Recomendación: no.** Mismo razonamiento que ya se usó para no crear un
contrato de captura de audio en `Voice.spec.md` ("forzarlo a un contrato
tipo `ILLMProvider` sería abstracción prematura sin un segundo caso real
que lo justifique") y el que ya sostiene que `Planner` es una clase
concreta, no una interfaz: **no hay una segunda implementación plausible
de "qué es un scheduler" que haya que poder intercambiar** — a diferencia
de `ITTSProvider`/`IWakeWordProvider`, donde sí existen motores
alternativos reales de mercado (Piper vs. ElevenLabs, openWakeWord vs.
Porcupine). `RoutineManager` es un orquestador concreto, como `Planner`.

Lo que **sí** amerita un modelo tipado (no una interfaz con métodos
abstractos, un dataclass como `PlannedStep`/`ActionResult`) es **la
acción que dispara una rutina**, porque ahí sí hay variantes reales desde
el día 1 (hablar / ejecutar agente / encadenar ambas):

```python
@dataclass(frozen=True)
class SpeakAction:
    text: str

@dataclass(frozen=True)
class AgentAction:
    agent_name: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ChainedAction:
    actions: tuple[SpeakAction | AgentAction, ...]

RoutineAction = SpeakAction | AgentAction | ChainedAction
```

**`[CONFIRMADO]`** sin `IRoutineManager`; `RoutineAction` como union de
dataclasses.

## 3. Modelo de datos y dónde se definen las rutinas `[CONFIRMADO]`

`RoutineDefinition`/`RoutineAction` quedaron definidos en las secciones
1 y 2 (cron + `on_startup`, acción tipada). Esta sección es sobre
**dónde vive la definición**, no su forma.

**Un directorio `routines_dir` con un archivo
por rutina (JSON, mismo criterio que `manifest.json` de plugins — leer
la definición de una rutina no debe requerir ejecutar código), cargado
una vez al iniciar el Kernel** (`Kernel.initialize()`, junto a
`_load_plugins()`) — no una tabla en base de datos. Motivos:
- Mismo patrón ya establecido y probado (`settings.plugins_dir` +
  `PluginRegistry`) — un usuario/dev edita un archivo, reinicia, listo.
  No hay que aprender un patrón nuevo de persistencia para esto.
- Las rutinas de v1 son pocas y las define una persona a mano, no un
  flujo de creación dinámica por UI/voz (eso queda fuera de alcance,
  sección 10) — no hay necesidad real de un store con escritura en
  caliente todavía.

**`[CONFIRMADO]`** archivo por rutina en `routines_dir` (nuevo campo en
`Settings`, default `"routines"`).

## 4. El problema difícil: ¿quién ejecuta la acción "hablar"? `[CONFIRMADO: Redis Streams]`

Esta es la decisión de arquitectura central del documento — igual que la
sección 5 de `Voice.spec.md` ("Cómo entra esto al Kernel/API"), se
presentan las opciones reales, no se elige en silencio.

`RoutineManager` corre en el proceso de la API (mismo que `Kernel`,
`AgentManager`, `EventBus` — sección 5). Ejecutar `AgentAction` ahí es
trivial: `agent_manager.dispatch(...)`, mismo proceso, sin nada nuevo que
inventar. **El problema es `SpeakAction`**: el TTS y el parlante viven
únicamente en el proceso de `VoicePipeline`, que es un proceso HTTP
cliente separado (decisión 2 de `Voice.spec.md`) — el proceso de la API
no tiene ni puede tener acceso a hardware de audio por diseño.

Se evaluaron tres caminos (endpoint HTTP con polling desde `VoicePipeline`;
mover el scheduler entero adentro de `VoicePipeline`; transporte real
entre procesos vía Redis). **Se descartó el polling HTTP**: además de la
latencia de hasta N segundos, un `PUBLISH`/`SUBSCRIBE` o un polling
simple no garantizan la entrega — si `VoicePipeline` está caído
justo cuando la rutina se dispara, el aviso se pierde sin dejar rastro,
algo inaceptable para un caso de uso literalmente llamado "despertame".
**Se descartó mover el scheduler a `VoicePipeline`**: dejaría *todas*
las rutinas (incluidas las que no hablan, como un backup) dependiendo de
que el proceso de audio esté corriendo, acoplando dos responsabilidades
que hoy están separadas a propósito.

**`[CONFIRMADO]` Redis Streams, detrás de un contrato nuevo `IMessageBus`
— diseño completo en `docs/specs/MessageBus.spec.md` +
`docs/contracts/IMessageBus.md`, no repetido acá.** Resumen de una línea:
`RoutineManager` publica en el topic `"routines.due"` cuando una
`SpeakAction` está vencida; `VoicePipeline` la consume con garantía de
entrega (si estaba caído, la lee al reconectar) y confirma con `ack()`
una vez que terminó de hablar. `IMessageBus` es un contrato **separado**
de `IEventBus` (confirmado explícitamente por el usuario, no una
generalización de lo que ya existe) — ver `MessageBus.spec.md` sección 2
para el porqué.

`VoicePipeline.run_forever()` gana un **segundo loop concurrente**
(`asyncio.create_task`, corriendo junto al loop de wake word ya
existente — factible sin reescribir nada: `_listen_for_activation_sync`
ya corre en un hilo aparte vía `asyncio.to_thread`, así que el loop del
event loop principal queda libre para este segundo task) que consume
`bus.subscribe("routines.due", group="voice-pipeline", consumer=...)`,
sintetiza con su `ITTSProvider` y reproduce con su `SpeakerPlayer` — los
mismos objetos que ya tiene — y hace `ack()` al terminar.

## 5. Dónde vive `RoutineManager` en el proceso de la API

Mismo lugar que `PluginRegistry`: **`Kernel` lo construye y lo dirige**,
usando el bucle de `run()` que ya existe en vez de crear uno nuevo en
paralelo — se agrega `await self._check_due_routines()` a cada iteración
del `while` de `Kernel.run()`, junto al `memory.clear_expired()` que ya
está. Reusa `settings.kernel_housekeeping_interval_seconds` o un
intervalo propio más fino (`routines_check_interval_seconds`, ej. 30s,
para que "las 7:00" no se dispare recién a las 7:01 si el intervalo de
housekeeping general es más largo) — nuevo campo en `Settings`.

`Kernel.initialize()` carga las rutinas desde `routines_dir` (igual que
`_load_plugins()` carga plugins), guarda la lista en memoria.

## 6. Seguridad: rutinas nunca ejecutan acciones destructivas sin confirmar

**Decisión, no negociable salvo que digas lo contrario:** antes de
despachar una `AgentAction`, `RoutineManager` llama
`agent.requires_confirmation(action, **params)` — si da `True`, la
rutina **no se ejecuta**, se loguea como fallo (`RoutineFailedEvent`,
sección 7) con el motivo explícito. No existe humano en el loop a las
7am para confirmar un `git reset --hard` disparado solo — mismo espíritu
que ya tiene el Planner (`needs_confirmation` sin `confirmed=True` corta
la ejecución) y `VoicePipeline` (exige la frase exacta `"confirmo"`,
nunca la asume). Una rutina que necesite una acción confirmable queda
mal definida por diseño, no es un caso a soportar en v1.

## 7. Eventos nuevos

Viven en `routines/events.py` (mismo criterio que `planner/events.py`/
`plugins/events.py`: junto a quien los publica, no en `core/events.py`):

```python
@dataclass(frozen=True)
class RoutineTriggeredEvent(BaseEvent):
    routine_id: str = ""

@dataclass(frozen=True)
class RoutineCompletedEvent(BaseEvent):
    routine_id: str = ""

@dataclass(frozen=True)
class RoutineFailedEvent(BaseEvent):
    routine_id: str = ""
    error: str = ""
```

Nota de alcance: estos 3 eventos **no** forman parte del catálogo fijo
de 15 eventos de `docs/contracts/IPlugin.md` (ese catálogo no se toca en
este documento) — son eventos de dominio nuevos, publicables/suscribibles
por cualquier handler del `EventBus` real igual que los demás, solo que
no están en esa lista específica de nombres fijos.

## 8. Consideración conocida, no resuelta en v1: micrófono abierto + hablar proactivamente

Si `VoicePipeline` está en medio de su loop de wake word (stream de
micrófono abierto, `read_frame()` bloqueante) y llega el momento de
anunciar una rutina por voz, el `SpeakerPlayer` reproduce por el parlante
mientras el micrófono sigue escuchando — riesgo de que el propio audio
reproducido sea captado por el micrófono. En la práctica es poco probable
que dispare una falsa detección de wake word (la frase que se anuncia no
es "hey jarvis"), pero no está mitigado ni testeado. **Documentado como
limitación conocida, no bloqueante para v1** — si se vuelve un problema
real, la mitigación natural es pausar brevemente el stream de captura
mientras se reproduce el anuncio (mismo patrón que ya usa
`_listen_for_activation_sync`, que no reabre el stream entre wake word y
captura de la orden).

## 9. Watchpoints anotados en la revisión (no bloquean, quedan registrados)

Señalados en la revisión del diseño, con criterio explícito de "no hace
falta resolverlos antes de implementar" — se documentan para no
perderlos, no porque cambien el diseño de este documento.

**9.1 — Downtime largo + rutina frecuente = muchas iteraciones de
descarte.** Tal como está diseñado `check_due()` (sección 1.1), tras un
downtime largo el ancla (`last_fired_occurrence` o `routine.loaded_at`)
puede estar muy atrás en el tiempo — `croniter.get_next()` devuelve la
ocurrencia **inmediatamente siguiente** al ancla, no la más reciente
respecto a `now`. Con una rutina diaria eso es irrelevante (como mucho
un par de ocurrencias viejas para descartar). Con una rutina horaria y
una semana de downtime, son ~168 ocurrencias, una por tick, cada una
evaluada como stale y descartada antes de alcanzar la ocurrencia real de
hoy — no rompe nada, pero genera ~168 líneas de `RoutineFailedEvent` en
el log a lo largo de varios minutos/horas según
`routines_check_interval_seconds`. Mejora barata posible a futuro (no
implementada ahora): si la ocurrencia calculada ya nace stale, saltar
directo a `croniter.get_next(after=now)` y loguear una sola línea
"se saltearon N ocurrencias vencidas" en vez de una por una.

**9.2 — `_try_execute()` secuencial dentro del tick: verificado contra
el código real, resultado mixto.** La preocupación (¿un `AgentAction`
lento retrasa la evaluación de las demás rutinas del mismo tick, o peor,
bloquea todo el proceso?) se chequeó contra los 4 `IAgent` nativos, no
se asumió:

| Agente | ¿Envuelve su I/O bloqueante en `asyncio.to_thread`? |
|---|---|
| `GitAgent` | Sí (`subprocess.run` vía `to_thread`) |
| `ProcessAgent` | Sí (`subprocess.run`/`os.kill` vía `to_thread`) |
| `DatabaseAgent` | Sí (`engine.begin()` vía `to_thread`) |
| `FileSystemAgent` | **No** — `execute()` llama `Path.read_text()`/`write_text()` de forma síncrona, directo dentro del método `async def`, sin `to_thread` |

Para `GitAgent`/`ProcessAgent`/`DatabaseAgent`, una `AgentAction` lenta
en el tick de rutinas **no** bloquea el event loop — otras tareas
concurrentes del proceso (otras rutinas del mismo tick, requests HTTP
entrantes) siguen corriendo mientras esa espera está en curso. Para
`FileSystemAgent`, un archivo grande o un filesystem lento **sí**
bloquea el event loop completo mientras dura la operación — no es un
problema nuevo de Routines (ya existe hoy para cualquier llamada vía
`POST /message`), pero se vuelve alcanzable desde el tick de
`Kernel.run()` además de desde HTTP. **No se corrige acá** — es un gap
preexistente de `FileSystemAgent`, fuera de alcance de este documento;
queda anotado como motivo real (no hipotético) para eventualmente
alinearlo con el resto de los agentes.

## 10. Qué NO se hace en v1 (fuera de alcance, a propósito)

- Texto de `SpeakAction` generado dinámicamente vía LLM/Brain (ej. "dame
  un resumen de mis pendientes") — v1 es texto literal fijo en la
  definición de la rutina. Extensión futura real, no implementada ahora.
- Rutinas creadas/editadas en caliente por voz, UI o una API de escritura
  — v1 es un archivo que edita el usuario a mano y se carga al iniciar.
- Condiciones más allá de horario/arranque (ej. "cuando el CPU supera
  90%", "cuando llega un email") — ningún agente hoy expone ese tipo de
  señal como para engancharla.
- Reintentos automáticos si una rutina falla — se loguea
  `RoutineFailedEvent` y se sigue, sin política de retry en v1.

## 11. Plan de archivos (para cuando se apruebe el diseño)

- `src/aries/routines/models.py` — `RoutineDefinition`, `RoutineAction`
  (`SpeakAction`/`AgentAction`/`ChainedAction`).
- `src/aries/routines/events.py` — los 3 eventos de la sección 7.
- `src/aries/routines/loader.py` — lee `routines_dir`, valida, devuelve
  `list[RoutineDefinition]` (mismo criterio que `plugins/manifest.py`:
  nunca deja escapar `OSError`/`JSONDecodeError` crudos).
- `src/aries/routines/manager.py` — `RoutineManager`: guarda las
  definiciones cargadas, `check_due(now: datetime) -> list[RoutineDefinition]`
  (vía `croniter`, sección 1), `execute(routine) -> None` (publica
  `RoutineTriggeredEvent`, despacha `AgentAction` vía `AgentManager` y/o
  publica `SpeakAction`s en `IMessageBus` — sección 4 —, publica
  `RoutineCompletedEvent`/`RoutineFailedEvent`; aplica la política de
  `routines_max_staleness_seconds` de `MessageBus.spec.md` sección 3).
- `src/aries/routines/cron.py` — traduce el `schedule` amigable del
  archivo de rutina (sección 1) a expresión cron; sin esto, `loader.py`
  tendría que saber de cron directamente, mezclando parseo de archivo
  con lógica de calendario.
- `src/aries/core/kernel.py` — construye `self.routine_manager`
  (recibe un `IMessageBus` ya construido, mismo patrón que recibe
  `agent_manager`/`event_bus` — no lo construye él mismo), lo carga en
  `initialize()`, lo chequea en cada tick de `run()` (sección 5).
- `src/aries/config/settings.py` — campos nuevos: `routines_dir`,
  `routines_check_interval_seconds`, `routines_max_staleness_seconds`.
- `src/aries/voice/pipeline.py` — segundo loop concurrente en
  `run_forever()` que consume `IMessageBus.subscribe("routines.due", ...)`
  (sección 4) — recibe un `IMessageBus` en el constructor de
  `VoicePipeline`, mismo patrón que `wake_word`/`stt`/`tts`.
- `docs/contracts/` — sin archivo nuevo para `RoutineManager` (sección 2,
  no tiene contrato ABC); **sí** `docs/contracts/IMessageBus.md`, ya
  escrito — ver `docs/specs/MessageBus.spec.md`.
- Ver `docs/specs/MessageBus.spec.md` sección 6 para el plan de archivos
  del lado del bus (`contracts/message_bus.py`, `messaging/redis_streams_bus.py`).
- `pyproject.toml` — dependencias nuevas: `croniter` (sección 1) y
  `redis` (ver `MessageBus.spec.md`).

## Referencias
- `docs/specs/Voice.spec.md` (decisión 2: por qué `VoicePipeline` es un
  proceso separado sin acceso desde la API)
- `docs/specs/Planner.spec.md` (por qué `Planner` no tiene contrato propio
  — mismo razonamiento aplicado acá a `RoutineManager`)
- `docs/specs/MessageBus.spec.md` + `docs/contracts/IMessageBus.md`
  (diseño completo de la sección 4 — Redis Streams, política de Redis
  caído, retención del stream)
- `src/aries/core/kernel.py` (bucle de `run()` a extender, sección 5)
- `src/aries/agents/manager.py` (`AgentManager.dispatch()`, reusado tal
  cual para `AgentAction`)
- `src/aries/contracts/tts.py`, `src/aries/voice/piper_provider.py`
  (`ITTSProvider`, reusado tal cual del lado de `VoicePipeline`)
- `src/aries/plugins/manifest.py`, `src/aries/plugins/registry.py`
  (patrón de carga desde directorio, reusado para `routines_dir`)
