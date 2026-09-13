# Aries OS — Progreso

> Fuente de verdad del estado del proyecto. Se actualiza al TERMINAR cada tarea, no al empezarla.
> Antes de cualquier tarea nueva, leer este archivo primero.

## Investigación de los 2 commits inesperados (Tarea 0, 2026-07-24) — archivado

Cerrado: el contenido de ambos commits coincidía 100% con trabajo ya documentado; el mecanismo de cómo se comitearon quedó sin confirmar (sospecha: checkpoint del entorno/extensión, no `git commit` propio). Detalle completo movido a [`docs/archive/2026-09-12-historial-implementacion.md`](../docs/archive/2026-09-12-historial-implementacion.md).

## Hallazgo sin resolver: regresión en `events/event_bus.py` (tercera noche, no causada por esta tarea)

Al leer `events/event_bus.py` como referencia de estilo para conectar `plugins/` al Event Bus real, encontré que **volvió a definir una clase `EventBus(ABC)` local** (con `AsyncEventBus(EventBus)` heredando de ella), revirtiendo el fix del ciclo de import de hace dos noches (que hacía `AsyncEventBus` heredar de `contracts.event_bus.IEventBus`, sin clase local duplicada). Verificado con `git diff HEAD -- src/aries/events/event_bus.py`: es el **único** archivo del cluster de eventos con diferencia contra el último commit — `subscriber.py`, `events/__init__.py` y `contracts/event_bus.py` siguen exactamente como quedaron comiteados (con mi fix intacto). Yo no toqué este archivo en ninguna tarea de esta sesión ni de la anterior.

**Impacto verificado, no asumido:** `import aries` sigue funcionando (`python -c "import aries"` ok), pero `isinstance(AsyncEventBus(), IEventBus)` ahora da `False` — `AsyncEventBus` sigue siendo compatible por duck-typing (mismos métodos `publish`/`subscribe`/`unsubscribe`) pero dejó de ser formalmente un `IEventBus` del contrato. No rompe nada de lo que hasta ahora se probó (los 289 tests de la suite completa siguen pasando), pero es una inconsistencia real de tipos.

**No lo corregí** — no es parte de esta tarea (que pidió `plugins/`, no tocar `events/`) y no está bloqueando nada. Para `plugins/`, seguí tipando contra `aries.contracts.event_bus.IEventBus` (la convención ya establecida en `core/kernel.py` y `events/publisher.py`, ambos intactos), no contra la clase local duplicada de `event_bus.py`. Revisar mañana junto con el hallazgo de los commits de la noche anterior.

## Estado actual (fecha de hoy)
| Fase | Estado |
| --- | --- |
| v0.1 Blueprint | completa |
| v0.2 Foundation | completa |
| v0.3 Kernel | **completo, y ahora totalmente cableado dentro del proceso de la API, incluido `run()`** — `initialize()`/`run()`/`shutdown()` reales: `run()` es un bucle de housekeeping de fondo (`memory.clear_expired()` en intervalo configurable); `initialize()` descubre y carga los plugins válidos de `settings.plugins_dir` (aislados entre sí) y los registra en el **único** `AgentManager` del proceso; `shutdown()` los descarga (y desregistra) en orden inverso antes de publicar `KernelShutdownEvent`. Publica 3 eventos propios. **Construido en `api.py`**: `initialize()`/`shutdown()` en sus eventos de startup/shutdown, y ahora **`run()` se lanza como tarea de fondo real (`asyncio.create_task`) en el startup y se espera limpio (`await`, sin cancelar) en el shutdown** — el housekeeping de la `_memory` compartida corre de verdad mientras el proceso está arriba. `python -m aries` es un lanzador de uvicorn sobre `aries.api:app`, ya no un proceso Kernel-only separado |
| v0.4 Planner | **implementado, conectado end-to-end, y ahora con memoria de conversación** — `src/aries/planner/` (interpreta texto vía LLM+Pydantic, recupera contexto reciente de `IMemory` por sesión, arma plan, ejecuta vía `AgentManager` real, publica 8 eventos) + `src/aries/brain/` (genera `response_text`) + `POST /message` en `api.py`. Las 9 decisiones de `docs/specs/Planner.spec.md` (ya no "BORRADOR", ahora "APROBADO") están implementadas, incluida la conexión a Memory que faltaba. **El `AgentManager` que usa el Planner es ahora el mismo que carga los plugins del Kernel** — ver v0.5, limitación anterior cerrada |
| v0.5 Plugins | **decisión de invocación cerrada Y conectada de punta a punta** — `IPlugin` requiere `execute(action, **params) -> ActionResult` (mismo contrato que `IAgent`); `PluginRegistry.load()`/`unload()` registran/desregistran cada plugin en `AgentManager` vía `PluginAgentAdapter`. **`AgentManager` unificado:** uno solo por proceso, construido en `api.py` (`_agent_manager`, mismo patrón de singleton de módulo que `_memory`) y pasado tanto al Planner (`get_planner()`) como al `Kernel` (`_kernel`, también construido en `api.py`) — un plugin cargado por `Kernel.initialize()` (disparado por el startup event de la app) queda dispatchable de verdad vía `POST /message`, confirmado con un test HTTP real de punta a punta. `CONTRACT_EVENTS` en 13/15. Instalación real de dependencias sigue deliberadamente fuera de alcance (`install_requirements()` es un stub de seguridad) |
| v0.6 Memory | **completa para su alcance actual — ahora persistente de verdad.** `SQLiteMemoryStore` (SQLAlchemy Core sobre SQLite, `src/aries/memory/sqlite_store.py`) implementa el mismo contrato `IMemory` que `InMemoryStore` y es **el default real en `api.py`** (`settings.memory_db_path`) — sobrevive a reinicios del proceso, confirmado con un ciclo real de `python -m aries` (apagar, prender, los datos siguen ahí). `InMemoryStore` sigue existiendo (más liviana para tests que no necesitan persistir nada) pero ya no es el default de producción. Conectada al Planner desde la tarea anterior (contexto de conversación por sesión). `InMemoryStore` en sí sigue sin publicar eventos directamente — es el Planner quien publica `MemoryStoredEvent` en su nombre |
| Agents | parcial — 4 `IAgent` concretos (`FileSystemAgent`, `ProcessAgent`, `GitAgent`, `DatabaseAgent`) + `AgentManager` que los registra y rutea (ahora también acepta `IAgent`s respaldados por plugins, vía `PluginAgentAdapter`, sin ningún cambio de comportamiento para los 4 nativos); invocados en runtime real por el Planner vía `AgentManager.dispatch()`. `FileSystemAgent.requires_confirmation()` ahora tiene `**kwargs` catch-all, consistente con los otros 3 |
| v0.7 Voice | **implementada de punta a punta — spec "APROBADO", las 8 decisiones tomadas y con código real.** `docs/specs/Voice.spec.md` + 3 contratos nuevos (`docs/contracts/IWakeWordProvider.md`/`ISTTProvider.md`/`ITTSProvider.md`, código en `src/aries/contracts/wake_word.py`/`stt.py`/`tts.py`). Implementaciones default reales: `OpenWakeWordProvider`, `FasterWhisperProvider` (con Silero VAD embebido vía `vad_filter=True`), `PiperProvider` — todas en `src/aries/voice/`. `VoicePipeline` orquesta wake word → captura (`sounddevice`, corte por energía RMS) → STT → `POST /message` (cliente HTTP más, cero cambios en `api.py`/`Planner`/`Brain`/`Kernel`) → confirmación por voz con frase exacta (`"confirmo"`) → TTS → reproducción. 19 tests nuevos, reales salvo el hardware de audio (único mock autorizado del proyecto, documentado); **3 hallazgos reales encontrados por esos tests** (ver sección dedicada abajo) |
| v1.0 MVP | no iniciada, pero el flujo end-to-end ya existe, está probado con HTTP real, y ahora tiene memoria entre turnos, plugins reales, housekeeping de fondo real, y un pipeline de voz real de punta a punta: `POST /message` → Planner (con contexto de la sesión) → `AgentManager` único (4 nativos + plugins que el Kernel haya cargado) → Agente/plugin real → Brain → respuesta → se guarda en Memory para el próximo turno; en paralelo, `kernel.run()` corre como tarea de fondo del mismo proceso limpiando memoria expirada, y `VoicePipeline` puede consumir el mismo `POST /message` como cliente de voz. Sigue faltando: catálogo de eventos en 13 de 15, y una wake word "Aries" propia (hoy usa `hey_jarvis` pre-entrenado) |

## Baseline conocido
- Ninguno. El par flaky que vivió acá varias tareas (`test_kernel_publishes_initialized_event`/`::test_kernel_publishes_shutdown_event`) se cerró — ver sección dedicada más abajo. `pytest` corre en verde real (345 passed, confirmado en corridas repetidas).

## Qué existe implementado — archivado (2026-09-12)

Historial completo de cada pieza construida (Kernel, Planner+Brain, los 4 `IAgent`, Plugins, Memory persistente, Voice de punta a punta, y las 2 sesiones nocturnas de 2026-07-24) movido a [`docs/archive/2026-09-12-historial-implementacion.md`](docs/archive/2026-09-12-historial-implementacion.md) — todo cerrado y shippeado, nada pendiente ahí (lo pendiente real sigue en la sección siguiente). Ver también la tabla "Estado actual" más arriba para el resumen vivo por módulo.

## Qué NO existe todavía (pendiente real)
- Existen cuatro `IAgent` concretos (`FileSystemAgent`, `ProcessAgent`, `GitAgent`, `DatabaseAgent`) y ahora `AgentManager` los conecta (registro + ruteo por nombre, más `unregister()` para des-registrar). El resto de los agentes documentados en `docs/contracts/IAgent.md` (WindowsAgent, DockerAgent, EmailAgent, BrowserAgent, HomeAssistantAgent) sigue sin implementar. `agents/base.py` sigue vacío.
- `src/aries/plugins/` está implementado, **conectado a `core/kernel.py`** (carga/descarga reales) **y conectado de punta a punta al `AgentManager` único del proceso** (`IPlugin.execute()` + `PluginAgentAdapter`, unificación con `api.py` — ver secciones dedicadas arriba) pero **ningún plugin real de terceros existe todavía** — solo los plugins de ejemplo de tests. **Deliberadamente sin implementar:** `install_requirements()` (instalación real de paquetes pip declarados por un plugin) es un stub que siempre lanza `NotImplementedError` — decisión de seguridad explícita, no pendiente por pereza. Tampoco hay descubrimiento automático de *dónde* buscar plugins más allá de un único directorio plano configurado en `settings.plugins_dir`.
- No hay ninguna clase concreta que implemente `ITool`, ni ningún `ToolRegistry` — el punto de extensión para la prioridad Tool-sobre-Agent (decisión 3 de `Planner.spec.md`) está comentado en `planner/planner.py` pero no implementado, sin caso real que lo justifique todavía.
- `src/aries/core/kernel.py` ya no usa sleeps como stub (`run()` hace housekeeping real) y ahora vive dentro del proceso de `api.py` (construido y manejado en sus eventos de startup/shutdown, compartiendo `AgentManager`/`Memory`/`EventBus` con el Planner — ver secciones dedicadas arriba), incluido `run()` corriendo como tarea de fondo real desde el startup. `python -m aries` dejó de ser un proceso Kernel-only separado; ahora es equivalente a `uvicorn aries.api:app`.
- `requires_confirmation()` de un plugin (vía `PluginAgentAdapter`) siempre devuelve `False` — `docs/contracts/IPlugin.md` no define un mecanismo de confirmación por acción como sí lo hace `IAgent`. Límite conocido del contrato, no un olvido: si un plugin necesitara marcar una acción como destructiva, el contrato tendría que extenderse primero (mismo criterio que ya se usó para `IAgent.requires_confirmation(action, **kwargs)`).
- `SQLiteMemoryStore` (persistente, default real en `api.py`) y `InMemoryStore` (no persistente, sigue existiendo) implementan `IMemory` — ver sección dedicada arriba. **Lo que sigue sin existir:** backends Postgres/Redis/Vector (`database_url`/`redis_url` de `settings.py` siguen sin ningún consumidor real), búsqueda semántica vía embeddings (el `TODO` de `search()` en ambos backends), e índices/columnas dedicadas para filtrar por `session_id` eficientemente (sigue siendo scan lineal filtrado del lado del Planner, ver decisión 1 de `Planner.spec.md` — aceptable hoy, `SQLiteMemoryStore` no cambia esa decisión).
- `src/aries/voice/` está implementado de punta a punta (ver sección dedicada arriba) pero **no existe una wake word "Aries" propia** — usa `hey_jarvis` pre-entrenado de openWakeWord (entrenar una custom requiere recolectar datos y el proceso de entrenamiento dedicado de la librería, fuera de alcance). Tampoco hay integración con `desktop/` (PySide6) — `VoicePipeline` corre hoy como proceso standalone puro (`python -m aries.voice` / `aries-voice`), sin UI. `IWakeWordProvider`/`ISTTProvider`/`ITTSProvider` solo tienen su implementación default local — ningún proveedor de pago/nube (`PorcupineProvider`, `ElevenLabsProvider`) implementado, a propósito (los contratos ya están diseñados para aceptarlos cuando haga falta).
- `src/aries/events/`: existe implementación de Event Bus con tests (motor sólido, ya revisado en `docs/audits/2026-07-24-diagnostico.md`, con la regresión de `event_bus.py` documentada arriba), y ahora define **13 de los 15** eventos de dominio que `docs/contracts/IPlugin.md` da por hechos: los 4 que ya existían (`KernelInitializedEvent`, `KernelShutdownEvent`, `PluginLoadedEvent`, `PluginUnloadedEvent`), los 7 del Planner (`IntentDetectedEvent`, `PlanCreatedEvent`, `PlanExecutedEvent`, `ActionStartedEvent`, `ActionCompletedEvent`, `ActionFailedEvent`, `ErrorOccurredEvent`), `MemoryStoredEvent`, y ahora `KernelStartingEvent` (nuevo, ver sección dedicada arriba). Quedan sin implementar solo **`MEMORY_DELETED` y `MEMORY_SEARCHED`**. `plugins/registry.py::CONTRACT_EVENTS` ya refleja los 13 reales (corregido en la tarea que conectó Plugins a Kernel, ver sección dedicada arriba) — el gap que quedaba documentado acá ya no existe.
- `src/aries/container/`: eliminado, no forma parte del path de ejecución actual.

## Próximo paso recomendado
Terminar de armar el dataset y entrenar el modelo custom de wake word "Hola Aries" en español (`docs/specs/WakeWordTraining.spec.md`, plan aprobado 2026-09-11/12) — la validación con hardware real de abajo ya diagnosticó la causa raíz de `hey_jarvis` (pronunciación en inglés que no matchea el training data, no un bug de audio/threshold) y esa parte quedó resuelta. Falta: grabar el resto de las tomas reales de "Hola Aries" (en curso), armar el dataset de negativos, entrenar, y luego integrar el `.onnx` resultante en `OpenWakeWordProvider` reemplazando `hey_jarvis`.

## Reglas para mantener este archivo
- Actualizar la tabla y "Qué existe implementado" al cerrar cada tarea, una línea por módulo
- Nunca borrar fases completadas, solo agregar filas nuevas
- "Próximo paso recomendado" siempre debe tener una sola tarea, nunca varias opciones
- Cuando una sección quede resuelta y cerrada (sin nada pendiente), archivarla en `docs/archive/<fecha>-<slug>.md` (contenido tal cual, sin editar) y dejar acá solo un resumen de 1-2 líneas con link — nunca archivar algo con trabajo activo/pendiente todavía (convención adoptada 2026-09-12)

---

## Sesiones nocturnas autónomas de 2026-07-24 — archivadas

Las dos sesiones nocturnas del 2026-07-24 (GitAgent+investigación de commits / DatabaseAgent+salud general) movidas a [`docs/archive/2026-09-12-historial-implementacion.md`](docs/archive/2026-09-12-historial-implementacion.md) — ambas cerradas, sin acciones pendientes.

---

## Validación de VoicePipeline con hardware real (2026-08-24) — RESUELTO (2026-09-13)

Se probó el pipeline completo (wake word → STT → POST /message → TTS) con
micrófono y parlante reales por primera vez. Estado: 3 de 4 componentes
confirmados funcionando; wake word con detección inconsistente, sin resolver.

### Entorno de la prueba
- Windows, venv `.venv-313`, Python 3.13
- openwakeword==0.6.0
- onnxruntime==1.17.3 (bajado desde 1.28.0, ver hallazgo más abajo)
- Modelo LLM: Ollama con `neural-chat:latest` (no estaba instalado, se instaló)
- Modelo wake word: `hey_jarvis` (pre-entrenado, no hay modelo "Aries" propio)

### Problemas encontrados y resueltos
1. **Captura de audio inicial no funcionaba**: `nivel` (RMS) constante en
   ~0.5 en cientos de frames seguidos pese a hablar — indicaba que
   `sounddevice` no estaba recibiendo señal real del micrófono. Se resolvió
   sin cambiar código (causa exacta en el lado de Windows no confirmada del
   todo — se tocaron permisos de micrófono y dispositivo default de
   Windows; después de eso `nivel` empezó a variar con la voz real).
2. **Ollama no estaba instalado** → causaba que el Kernel arrancara con
   `WARNING: Proveedor LLM no disponible al iniciar`. Se instaló Ollama
   (vía winget) y se descargó el modelo `neural-chat` que ya estaba
   configurado en `configs/development/settings.yaml` y `.env`. Confirmado
   con log `GET http://localhost:11434/api/tags "HTTP/1.1 200 OK"` al
   arrancar la API.
3. **Bug real de compatibilidad onnxruntime**: con `onnxruntime==1.28.0`
   (la versión que `pip install` trae por default hoy), `OpenWakeWordProvider`
   daba scores de wake word consistentemente cercanos a cero
   (0.000001–0.00002) **sin importar el volumen ni el contenido del audio**
   — incluso en frames con RMS de audio de 20000+ (muy fuerte, sin
   clipping verificado). Se confirmó con un script standalone
   (`sd.rec` + verificación de clipping) que la captura de audio en sí
   no tiene distorsión (0% clipping, RMS sano). Se reprodujo el mismo
   `test_mic.wav` en un entorno Linux con las mismas versiones
   (openwakeword==0.6.0, onnxruntime==1.28.0) y SÍ dio scores razonables
   (hasta 0.16) — descartando audio/hardware como causa y apuntando a
   algo específico del binario/runtime de onnxruntime 1.28.0 en Windows.
   **Se resolvió bajando a `onnxruntime==1.17.3`** (versión contemporánea
   al release de openwakeword 0.6.0, de feb. 2024) — los scores subieron
   a un rango real (0.01–0.26) inmediatamente después del downgrade.
   Se sospechó también de modelos `.onnx` corruptos/incompletos
   (openwakeword 0.6.0 dropeó los modelos pre-empaquetados y los descarga
   aparte vía `download_models()`, que solo chequea existencia de archivo,
   no integridad) — se borraron y redescargaron limpios, sin cambio en el
   resultado, así que esa NO era la causa real; el fix fue el downgrade
   de onnxruntime.

### Problema abierto: score de "hey jarvis" inconsistente
Con `onnxruntime==1.17.3` ya instalado, se hicieron 8 tomas distintas
diciendo "hey jarvis" (algunas 1 sola vez, otras repetido 3-4 veces
seguidas, algunas más lento/estirado). Scores máximos por toma:
0.257, 0.0047, 0.037, 0.0145, 0.0140, 0.0306 (aprox., ver voice_log.txt
de cada sesión si se conservaron). **Ninguna toma cruzó el threshold**,
ni con threshold en 0.50 (default), ni 0.30, ni 0.15, ni 0.05.

No se identificó una causa raíz concreta para la inconsistencia — se
descartó volumen (picos de audio de hasta 5800 RMS dieron scores bajos)
y se descartó "repetir varias veces seguidas" como única explicación
(una toma de una sola vez también dio score bajo, 0.014-0.03).

Hipótesis sin confirmar, en orden de sospecha:
- Acento/pronunciación del hablante no coincide bien con la distribución
  de entrenamiento del modelo `hey_jarvis` (entrenado mayormente con
  hablantes de inglés nativo)
- Podría seguir habiendo algún factor de captura de audio (timing de
  frames, gaps entre `read_frame()` calls) que no se identificó
- No se probó aún: grabar la wake word en un archivo `.wav` limpio
  (similar a `test_mic.wav`) exclusivamente diciendo "hey jarvis" una
  vez, sin ningún otro ruido, y correr `model.predict()` frame por
  frame offline para aislar el problema de la variable "en vivo por
  micrófono con jobs de PowerShell de por medio"

### Estado de `VOICE_WAKE_WORD_THRESHOLD`
Quedó en `0.05` en el `.env` local (no comiteado, es config local). Con
ese valor, en teoría cualquier score >0.05 debería disparar — pero
ninguna de las últimas tomas superó 0.03, así que ni con ese threshold
bajo se logró un `Wake word detectada` real en esta sesión.

### Siguiente paso sugerido (histórico, ver resolución abajo)
No se ha confirmado un ciclo completo end-to-end exitoso (wake word →
STT → API → TTS → parlante) con hardware real todavía. Antes de seguir
bajando el threshold indefinidamente, valdría la pena: (a) diagnosticar
offline con clips `.wav` grabados sin la complejidad de jobs de
PowerShell/streaming en vivo, o (b) evaluar entrenar un modelo de wake
word propio con muestras de la voz real del usuario (openwakeword
soporta esto, ver `docs/custom_verifier_models.md` de la librería).

### Resolución final (2026-09-13): causa raíz real era una mejora de audio de Windows, no código

Tras esta sesión se investigaron y descartaron, en orden, varias hipótesis
con evidencia real antes de llegar a la causa raíz — se deja el registro
completo porque cada descarte fue un hallazgo real, no un callejón sin
salida vacío:

1. **Backend MME de captura** (real, corregido y en producción): `_prefer_wasapi_input_device` +
   resampling desde el sample rate nativo del dispositivo en
   `audio_io.py`/`MicrophoneListener` — el mic capturaba casi silencio
   por MME, WASAPI lo resuelve. Sigue siendo necesario, no era la causa
   del problema de score bajo.
2. **`onnxruntime==1.28.0`** — descartado. Confirmado que había vuelto a
   resolverse a esa versión durante las instalaciones de la sesión de
   entrenamiento custom (nunca estuvo fijada en `pyproject.toml`); se
   fijó `onnxruntime>=1.20,<1.28` y se dejó `1.20.0` instalada. El score
   siguió bajo incluso con la versión "sana" confirmada activa — no era
   la causa.
3. **Artefacto de resampling frame-a-frame** (clicks en cada borde de
   80ms) — descartado con una prueba causal real: "declickear" los
   bordes no cambió el score de forma significativa (0.000445 vs 0.0004).
4. **Filtro de banda angosta en la captura misma** (no en el resampling)
   — confirmado con análisis espectral comparando un dump del audio
   crudo (rate nativo, antes de `_resample_frame`) contra el ya
   resampleado: ambos daban prácticamente los mismos porcentajes por
   banda (~76% de la energía en 0-300Hz en los dos), descartando que el
   resampling fuera la causa y apuntando a algo anterior en la cadena de
   captura.
5. **Pronunciación en inglés** — hipótesis que se sostuvo como líder
   durante gran parte de la sesión (y motivó todo el trabajo de
   `docs/specs/WakeWordTraining.spec.md`, wake word custom en español)
   — **descartada como causa de este bug puntual** por el hallazgo final.

**Causa raíz real, confirmada por el usuario:** las mejoras de audio de
Windows ("Voice Clarity"/"Foco de voz", Panel de Sonido → Grabación →
Razer → Propiedades → Mejoras de audio) aplicaban un filtro agresivo de
reducción de ruido que aplastaba todo el espectro por encima de ~300Hz —
exactamente el patrón que mostró el análisis espectral del punto 4, con
la causa un paso más atrás de lo que ese análisis podía ver (la mejora
se aplica en el motor de audio compartido de Windows, antes de que
`sounddevice`/PortAudio reciban una sola muestra — ningún cambio de
código podía haberlo arreglado). **Al desactivar esas mejoras, `hey_jarvis`
disparó por primera vez de verdad** (`score=0.0563`, cruzó el threshold
de `0.05`).

**Conclusión práctica:** el fix real es de configuración de Windows, no
de código — no hay nada que "arreglar" en `audio_io.py` para este bug
específico (el fix de WASAPI del punto 1 sigue siendo válido y necesario
por su propia razón, solo que no era la causa de *este* problema). Los 3
dumps TEMPORAL de diagnóstico (audio crudo, audio resampleado, logging
de score por frame) y el toggle `VOICE_DEBUG_WASAPI_EXCLUSIVE` se
removieron de `audio_io.py`/`pipeline.py`/`openwakeword_provider.py` una
vez cerrado el diagnóstico.

**Pendiente real para la próxima sesión:** decidir si seguir invirtiendo
en el wake word custom en español (`docs/specs/WakeWordTraining.spec.md`)
ahora que la causa de este bug puntual no era pronunciación — la razón
original para migrar a un modelo propio (UX: una frase en español en vez
de "hey jarvis" en inglés) sigue siendo válida por su cuenta, pero ya no
es "la solución a un bug", es una mejora de producto a evaluar aparte.
