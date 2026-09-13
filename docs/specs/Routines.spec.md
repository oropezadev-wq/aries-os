# Routines (comportamiento proactivo) — Spec

> **BORRADOR — requiere aprobación.** Escrito a partir del código real
> existente (`core/kernel.py`, `contracts/event_bus.py`, `agents/manager.py`,
> `voice/pipeline.py`, `contracts/tts.py`) y del mismo patrón de
> `docs/specs/Voice.spec.md`/`docs/specs/Planner.spec.md` (contexto real
> primero, decisiones numeradas después, puntos `[REQUIERE DECISIÓN]`
> explícitos donde corresponde). **Cero código todavía** — instrucción
> explícita: revisar el diseño antes de escribir una sola línea de
> `routines/`.

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

**Recomendación: horario simple (hora del día + días de la semana) y
"al arrancar el sistema" — no cron completo.**

```
trigger: "daily" | "on_startup"
time_of_day: "07:00"        # solo si trigger == "daily"
days_of_week: [0,1,2,3,4]   # opcional, default todos los días; 0=lunes
```

Motivo: es lo que cubre los tres ejemplos del objetivo sin agregar una
dependencia nueva (`croniter`/`APScheduler`) para un caso de uso que hoy
es "una vez por día a tal hora" — mismo criterio ya aplicado en el
proyecto para no sumar herramientas sin necesidad real (ej. `ToolRegistry`
comentado pero no implementado en `planner.py` hasta que exista un
`ITool` real). Si en el futuro hace falta cron completo (ej. "cada 15
minutos entre las 9 y las 18"), se agrega `croniter` como dependencia
nueva en ese momento — el modelo de datos de la sección 3 deja lugar
para un `trigger: "cron"` adicional sin romper los otros dos.

**`[REQUIERE DECISIÓN]`** ¿Confirmás este alcance acotado para v1, o
querés cron completo desde el arranque?

## 2. ¿`RoutineManager` necesita un contrato (`IRoutineManager`)?

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

**`[REQUIERE DECISIÓN]`** ¿De acuerdo con no crear `IRoutineManager`, y
con este modelo de `RoutineAction` como union de dataclasses (no ABC)?

## 3. Modelo de datos y dónde se definen las rutinas

```python
@dataclass(frozen=True)
class RoutineDefinition:
    id: str                     # único, ej. "buenos-dias"
    trigger: Literal["daily", "on_startup"]
    action: RoutineAction
    time_of_day: str | None = None      # "HH:MM", solo si trigger == "daily"
    days_of_week: tuple[int, ...] | None = None  # None = todos los días
    enabled: bool = True
```

**Recomendación de carga: un directorio `routines_dir` con un archivo
por rutina (JSON, mismo criterio que `manifest.json` de plugins — leer
la definición de una rutina no debe requerir ejecutar código), cargado
una vez al iniciar el Kernel** (`Kernel.initialize()`, junto a
`_load_plugins()`) — no una tabla en base de datos. Motivos:
- Mismo patrón ya establecido y probado (`settings.plugins_dir` +
  `PluginRegistry`) — un usuario/dev edita un archivo, reinicia, listo.
  No hay que aprender un patrón nuevo de persistencia para esto.
- Las rutinas de v1 son pocas y las define una persona a mano, no un
  flujo de creación dinámica por UI/voz (eso queda fuera de alcance,
  sección 6) — no hay necesidad real de un store con escritura en
  caliente todavía.

**`[REQUIERE DECISIÓN]`** ¿Archivo por rutina en `routines_dir` (nuevo
campo en `Settings`, default algo como `"routines"`), o preferís que las
rutinas vivan en `configs/development/settings.yaml` como una lista
dentro del YAML que ya existe? Cualquiera de las dos es simple; la
diferencia es si querés un directorio de archivos independientes
(más fácil de versionar/editar de a uno) o una sola lista centralizada.

## 4. El problema difícil: ¿quién ejecuta la acción "hablar"?

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

### Opción A — Nuevo endpoint HTTP que `VoicePipeline` consulta (recomendada)

`RoutineManager` (en el proceso de la API) evalúa qué rutina está vencida
y, si su acción incluye hablar, la deja en estado "pendiente de anunciar".
Se agregan dos endpoints nuevos a `api.py`:
- `GET /routines/due` — devuelve las rutinas con acción de voz vencidas
  y no anunciadas todavía.
- `POST /routines/{id}/ack` — `VoicePipeline` confirma que ya la habló.

`VoicePipeline.run_forever()` gana un **segundo loop concurrente**
(`asyncio.create_task`, corriendo junto al loop de wake word ya
existente — factible sin reescribir nada: `_listen_for_activation_sync`
ya corre en un hilo aparte vía `asyncio.to_thread`, así que el loop del
event loop principal queda libre para este segundo task) que hace poll a
`GET /routines/due` cada N segundos, y si hay algo, lo sintetiza con su
`ITTSProvider` y lo reproduce con su `SpeakerPlayer` — los mismos objetos
que ya tiene, sin ningún componente nuevo del lado de voz — y confirma
con el `ack`.

**A favor:** mismo patrón ya establecido (`VoicePipeline` como cliente
HTTP de la API, cero cambios en `Planner`/`Brain`/`Kernel` más allá de lo
que ya se decide acá); no agrega infraestructura nueva (ni Redis, ni
colas); `RoutineManager` sigue sin saber nada de audio.
**En contra:** hay un delay de hasta N segundos entre "la rutina está
vencida" y "se anuncia" (el intervalo de polling) — aceptable para
"despertame a las 7am" (no hace falta al segundo), no para algo con
requisito de latencia real.

### Opción B — El scheduler corre dentro de `VoicePipeline`, no en la API

Se importa la lógica de evaluación de horarios como librería dentro del
proceso de `VoicePipeline` en vez de tener un `RoutineManager` separado
en la API. Para `AgentAction`, `VoicePipeline` pegaría contra `POST
/message` (ya existe) o necesitaría un endpoint de despacho directo
nuevo igual.

**A favor:** cero latencia de polling, un solo proceso evalúa todo.
**En contra:** rompe la separación ya establecida ("Kernel/API corren
headless, sin nada de audio de por medio" — acá el proceso de audio
pasaría a ser dueño de la lógica de scheduling, que conceptualmente no
tiene nada que ver con audio); si `VoicePipeline` no está corriendo (el
usuario no lo tiene levantado), **ninguna** rutina se ejecuta, ni
siquiera las que solo corren un agente sin hablar — perdés justo el caso
"backup cada 30 minutos" que no necesita voz para nada.

### Opción C — Transporte de eventos real entre procesos (Redis pub/sub)

Usar el `redis_url` ya declarado (sin consumidor hoy) para que
`RoutineManager` publique y `VoicePipeline` se suscriba en tiempo real.

**A favor:** la opción "correcta" a largo plazo, cero polling, cero delay.
**En contra:** primer consumidor real de Redis en todo el proyecto —
dependencia de infraestructura nueva (hay que tener Redis corriendo) para
resolver algo que hoy es "avisame una vez por día a una hora fija". Fuera
de proporción para el alcance de v1 de la sección 1.

**Recomendación: Opción A.** Motivo de una línea: reusa exactamente el
patrón ya validado (`VoicePipeline` como cliente HTTP delgado), no
condiciona "cualquier rutina" a que el proceso de audio esté corriendo, y
no suma infraestructura nueva para un caso de uso que tolera algunos
segundos de latencia.

**`[REQUIERE DECISIÓN]`** ¿Opción A, o alguna de las otras dos?

## 5. Dónde vive `RoutineManager` en el proceso de la API

Mismo lugar que `PluginRegistry`: **`Kernel` lo construye y lo dirige**,
usando el bucle de `run()` que ya existe en vez de crear uno nuevo en
paralelo — se agrega `await self._check_due_routines()` a cada iteración
del `while` de `Kernel.run()`, junto al `memory.clear_expired()` que ya
está. Reusa `settings.kernel_housekeeping_interval_seconds` o un
intervalo propio más fino (`routines_check_interval_seconds`, ej. 30s,
para que "las 7:00" no se dispare recién a las 7:01 si el intervalo de
housekeeping general es más largo) — a definir en la sección 3 del config.

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

## 9. Qué NO se hace en v1 (fuera de alcance, a propósito)

- Cron completo (`trigger: "cron"` con expresión arbitraria) — ver
  sección 1.
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

## 10. Plan de archivos (para cuando se apruebe el diseño)

- `src/aries/routines/models.py` — `RoutineDefinition`, `RoutineAction`
  (`SpeakAction`/`AgentAction`/`ChainedAction`).
- `src/aries/routines/events.py` — los 3 eventos de la sección 7.
- `src/aries/routines/loader.py` — lee `routines_dir`, valida, devuelve
  `list[RoutineDefinition]` (mismo criterio que `plugins/manifest.py`:
  nunca deja escapar `OSError`/`JSONDecodeError` crudos).
- `src/aries/routines/manager.py` — `RoutineManager`: guarda las
  definiciones cargadas, `check_due(now: datetime) -> list[RoutineDefinition]`,
  `execute(routine) -> None` (publica `RoutineTriggeredEvent`, despacha
  vía `AgentManager` y/o marca pendiente de voz según la sección 4,
  publica `RoutineCompletedEvent`/`RoutineFailedEvent`).
- `src/aries/core/kernel.py` — construye `self.routine_manager`, lo carga
  en `initialize()`, lo chequea en cada tick de `run()` (sección 5).
- `src/aries/config/settings.py` — campos nuevos: `routines_dir`,
  `routines_check_interval_seconds`.
- `src/aries/api.py` — `GET /routines/due`, `POST /routines/{id}/ack`
  (solo si se confirma la Opción A de la sección 4).
- `src/aries/voice/pipeline.py` — segundo loop concurrente en
  `run_forever()` que hace poll a `GET /routines/due` (solo si Opción A).
- `docs/contracts/` — **sin archivo nuevo**, dado que no hay contrato
  ABC (sección 2) — si eso cambia, se documentaría acá con el mismo
  formato que `IAgent.md`/`IPlugin.md`.

## Referencias
- `docs/specs/Voice.spec.md` (decisión 2: por qué `VoicePipeline` es un
  proceso separado sin acceso desde la API; patrón de cliente HTTP a
  reusar en la sección 4, Opción A)
- `docs/specs/Planner.spec.md` (por qué `Planner` no tiene contrato propio
  — mismo razonamiento aplicado acá a `RoutineManager`)
- `src/aries/core/kernel.py` (bucle de `run()` a extender, sección 5)
- `src/aries/agents/manager.py` (`AgentManager.dispatch()`, reusado tal
  cual para `AgentAction`)
- `src/aries/contracts/tts.py`, `src/aries/voice/piper_provider.py`
  (`ITTSProvider`, reusado tal cual del lado de `VoicePipeline`)
- `src/aries/plugins/manifest.py`, `src/aries/plugins/registry.py`
  (patrón de carga desde directorio, reusado para `routines_dir`)
