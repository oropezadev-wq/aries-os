# Voice — Spec

> **APROBADO.** Escrito originalmente como borrador a partir de
> `docs/01_ARCHITECTURE.md`, `docs/02_TECH_STACK.md`, `docs/VISION.md`,
> `docs/contracts/ILLMProvider.md` (patrón de contrato + proveedor
> intercambiable a replicar), `docs/specs/Planner.spec.md` (ya "APROBADO" e
> implementado — el front door de texto que Voice reusa, no duplica) y el
> código real ya existente. Los 8 puntos que quedaron marcados
> `[REQUIERE DECISIÓN]` se resolvieron y ya están implementados en
> `src/aries/voice/` y `src/aries/contracts/` — ver la sección 8 (ahora
> "Resumen de las 8 decisiones finales") para el detalle de cada una, y
> `PROGRESS.md` para el detalle de archivos/tests.

## Contexto: qué ya existe y qué no

- `docs/01_ARCHITECTURE.md` describe el flujo `Usuario -> Wake Word -> STT
  -> Planner -> Brain -> Skill -> Agent -> Resultado`. Hoy existen
  `Planner`, `Brain`, `AgentManager` (con 4 `IAgent`), `Kernel`, `Plugins` —
  **todo el tramo desde "Planner" en adelante ya está implementado y
  probado end-to-end vía HTTP** (`POST /message`, ver `PROGRESS.md`). Lo
  que falta es exactamente lo que este documento diseña: **Wake Word y
  STT** (antes del Planner) y **TTS** (después de Brain).
- `docs/02_TECH_STACK.md` ya fija Faster-Whisper (STT) y Piper (TTS) como
  las piezas del stack — no hay que elegir motor STT/TTS, ya está decidido
  a nivel de proyecto. Lo que sí queda por diseñar es el contrato que los
  envuelve (para poder cambiarlos después) y cómo se conectan al resto.
- `pyproject.toml` declaraba el extra `voice` con `pydub`, `SpeechRecognition`,
  `piper-tts`, `faster-whisper` — **declaradas, sin una sola línea de
  código que las usara**. Tras la decisión 3 (sección 4), `pydub`/
  `SpeechRecognition` se removieron y se agregaron `sounddevice` y
  `openwakeword`.
- `src/aries/voice/__init__.py` existe y está vacío. `src/aries/exceptions/__init__.py`
  ya define `VoiceError(AriesException)`, **sin ningún consumidor
  todavía** — este documento lo convierte en la excepción real de
  `ISTTProvider`/`ITTSProvider`.
- `config/settings.py` ya tiene `voice_enabled: bool = True`, sin que nada
  lo lea todavía.

---

## 1. Flujo completo, extremo a extremo

```
[Micrófono]
    │  audio continuo, streaming
    ▼
[Wake Word] ── detecta la palabra de activación en el stream continuo
    │  (solo cuando se detecta, se pasa al siguiente paso)
    ▼
[Captura de utterance] ── graba desde la detección hasta que el usuario
    │                      deja de hablar (corte por silencio)
    ▼
[ISTTProvider.transcribe(audio)] ── FasterWhisperProvider, local
    │  → texto plano
    ▼
[POST /message]  (YA EXISTE, sin cambios — ver sección 5)
    │  user_input=texto, session_id=<id del dispositivo/sesión de voz>
    │  → { response_text, needs_confirmation, success, error, ... }
    ▼
[ITTSProvider.synthesize(response_text)] ── PiperProvider, local
    │  → audio
    ▼
[Parlante] ── reproduce el audio
```

Puntos clave de diseño que ya se pueden fijar sin ambigüedad, porque ya
están resueltos por trabajo previo:

- **El Planner no cambia en absoluto.** Decisión 1 de `Planner.spec.md` ya
  dice explícitamente: *"el Planner no debería saber ni le debería
  importar si el texto vino de voz o de teclado"*. Voice es, desde el
  punto de vista del servidor, un cliente HTTP más de `POST /message` —
  exactamente como esa misma spec anticipó (decisión 7: *"es la superficie
  que un futuro cliente de voz/UI terminaría llamando de todos modos"*).
- **`Brain` no cambia en absoluto.** Ya genera `response_text` en lenguaje
  natural, listo para pasarle a TTS tal cual — no hace falta un modo
  "para hablar" distinto de un modo "para mostrar en pantalla" (si algún
  día hiciera falta esa distinción — ej. abreviar URLs largas al hablar —,
  es una decisión futura de `brain/`, no de Voice; no se inventa acá sin
  caso real).
- **La confirmación de acciones destructivas reusa el mecanismo que ya
  existe** (`needs_confirmation`/`confirmed`, decisión 5 de
  `Planner.spec.md`), con una consideración de seguridad nueva — ver
  sección 6.

---

## 2. Contratos nuevos: `ISTTProvider` / `ITTSProvider`

Documentados completos en archivos separados, mismo estilo que
`docs/contracts/ILLMProvider.md`:

- **`docs/contracts/ISTTProvider.md`** — `async transcribe(audio, language=None, **kwargs) -> STTResult`, `is_available()`, `get_model_name()`. Implementación default: `FasterWhisperProvider` (local, gratis, offline).
- **`docs/contracts/ITTSProvider.md`** — `async synthesize(text, voice=None, **kwargs) -> TTSResult`, `is_available()`, `get_voice_name()`. Implementación default: `PiperProvider` (local, gratis, offline).

Ambos contratos:

- Usan la excepción `VoiceError` ya existente en `exceptions/__init__.py`
  (sin usar hasta hoy) — no se inventa una jerarquía nueva de excepciones
  de voz cuando ya hay una definida y sin consumidor.
- Están **explícitamente diseñados para aceptar proveedores de pago/nube
  más adelante** (`ITTSProvider.md` lo dice en su propia sección de
  Responsabilidad, con `ElevenLabsProvider` como ejemplo concreto) sin que
  el pipeline de Voice, el Planner o `Brain` tengan que cambiar una sola
  línea — el mismo intercambio que `ILLMProvider` ya permite hoy entre
  `OllamaProvider` (local) y los proveedores cloud documentados pero no
  implementados (`OpenAIProvider`, `ClaudeProvider`, `GeminiProvider`).
- **No** se propone un contrato para el paso de captura de audio en sí
  (micrófono → bytes) ni para reproducción (bytes → parlante) — esos son
  detalles de infraestructura del pipeline, no proveedores de IA
  intercambiables; forzarlos a un contrato tipo `ILLMProvider` sería
  abstracción prematura sin un segundo caso real que lo justifique (nadie
  va a "cambiar de micrófono" en runtime con una interfaz swappeable).

### Formato de audio entre capas

**DECISIÓN 4 (final):** **PCM WAV, mono, 16kHz** — confirmado como
formato de intercambio en los dos bordes del pipeline: captura de
micrófono → `ISTTProvider.transcribe(audio)`, y `ITTSProvider.synthesize()`
→ reproductor. **Verificado empíricamente, no asumido:** `faster-whisper`
rechaza PCM crudo sin encabezado (`InvalidDataError`) cuando se le pasa
como `bytes`/`BinaryIO` — necesita un contenedor WAV real con header, por
eso el contrato dice "PCM WAV" y no "PCM crudo". `TTSResult.sample_rate`
sigue existiendo como campo obligatorio pese a fijar 16kHz como estándar
del pipeline: la voz default de Piper elegida (`es_ES-carlfm-x_low`)
resulta sintetizar exactamente a 16kHz (verificado empíricamente), pero
otras voces de Piper no lo hacen (`22050Hz` es común en otras) — el
reproductor de audio siempre debe leer `sample_rate` del resultado, nunca
asumir 16kHz a ciegas solo porque hoy coincide con la voz default.

**Nota de VAD (ver también decisión 6):** `FasterWhisperProvider` usa el
parámetro nativo `vad_filter=True` de `faster-whisper` en cada llamada a
`transcribe()` — este filtra/recorta silencio dentro del audio ya
capturado usando un modelo Silero VAD que la propia librería trae
embebido (ONNX, sin dependencia de `torch`), mejorando la calidad de la
transcripción. Esto es un mecanismo **interno y automático** de
`ISTTProvider`, no algo que el llamador deba configurar — ver
`docs/contracts/ISTTProvider.md` para el detalle.

---

## 3. Detección de wake word

No hay nada decidido en el stack sobre esto — `docs/02_TECH_STACK.md` fija
STT/TTS pero no wake word, y `pyproject.toml` no declara ninguna librería
de este tipo todavía. Investigación (no asumida de memoria):

| Opción | Costo | Offline | Notas |
| --- | --- | --- | --- |
| **openWakeWord** | Gratis, open-source (Apache 2.0) | Sí, 100% | Activamente mantenido; un solo núcleo de Raspberry Pi 3 corre 15-20 modelos en tiempo real; entrenar una wake word custom requiere conocimiento de ML pero ya trae modelos pre-entrenados listos para usar |
| **Porcupine (Picovoice)** | Pago para uso comercial (reportado $6K+/año); tiene tier gratuito con límites para uso personal/evaluación | Sí | Muy fácil crear wake words custom (sin ML, sin recolectar datos) vía su consola; SDKs para casi todas las plataformas; requiere `AccessKey`/cuenta incluso en el tier gratuito |
| **Vosk / otros STT con "hotword"** | Gratis | Sí | No es una solución de wake word dedicada — usar un motor STT completo solo para detectar una palabra es derrochar cómputo comparado con un modelo chico dedicado |

**Recomendación: `openWakeWord` como default.** Es la única opción 100%
gratuita y offline sin cuenta/`AccessKey` de por medio, coherente al pie de
la letra con "bajo costo" + "offline-first" de `docs/VISION.md` — el mismo
criterio que ya hizo elegir Ollama sobre OpenAI/Claude como proveedor LLM
default. Porcupine queda como alternativa documentada, no descartada, para
cuando/si aparece un caso real que justifique pagar por mejor precisión o
soporte comercial (mismo espíritu que dejar la puerta abierta a
`ElevenLabsProvider` en TTS).

**DECISIÓN 1 (final):** `openWakeWord` **sí tiene contrato propio**,
`IWakeWordProvider` (`docs/contracts/IWakeWordProvider.md`, mismo patrón
que `ISTTProvider`/`ITTSProvider`) — se prioriza consistencia con el resto
del sistema y la misma swappability futura (Porcupine u otro) por sobre
el argumento de "una sola implementación conocida no justifica un
contrato" que este documento había planteado. Implementación default:
`OpenWakeWordProvider`.

**Detalle de diseño no anticipado en el borrador, resuelto durante la
implementación:** `IWakeWordProvider.process_frame()` es el único método
**síncrono** (no `async def`) entre todos los contratos de proveedores del
proyecto — a propósito, documentado en el propio contrato: se llama en un
loop de tiempo real, frame a frame (80ms por frame, ~12.5 veces por
segundo), en lockstep con una lectura bloqueante del micrófono; envolverlo
en `async` no aportaría nada (no hay I/O real que solapar, es una
inferencia ONNX local de unos pocos milisegundos) y solo complicaría el
loop de captura con puenteo hilo-`asyncio` innecesario.

**Modelo default:** no existe (todavía) una wake word entrenada para
"Aries" — openWakeWord solo trae pre-entrenados `alexa`, `hey_mycroft`,
`hey_jarvis`, `hey_rhasspy`, `timer`, `weather` (todos en inglés).
Se eligió **`hey_jarvis`** como default (temáticamente el más cercano a
un asistente de IA) — entrenar un modelo custom "Aries"/"Hey Aries" queda
fuera de alcance de esta tarea (requiere recolectar datos y el proceso de
entrenamiento dedicado de openWakeWord), documentado como limitación
conocida en `PROGRESS.md`. El modelo es configurable
(`settings.voice_wake_word_model`), así que cambiarlo no requiere tocar
código cuando exista un modelo real para "Aries".

---

## 4. Captura y reproducción de audio

No son proveedores de IA (sección 2), sino infraestructura del pipeline:

**DECISIÓN 3 (final):** **`sounddevice`** — dependencia nueva, aprobada
explícitamente, agregada a `pyproject.toml` (extra `voice`). Se descartó
`SpeechRecognition`+`pydub` (que seguían declaradas del borrador
original) precisamente por la razón ya anotada en el borrador:
`pydub.playback.play()` depende de un binario externo (`ffmpeg`/`ffplay`)
fuera del control de `pyproject.toml`, mientras que `sounddevice` (bindings
a PortAudio, con el binario ya empaquetado en el wheel de Windows/Mac/Linux)
resuelve captura **y** reproducción sin esa dependencia oculta.
`SpeechRecognition`/`pydub` se **removieron** de `pyproject.toml` — no
tenía sentido dejarlas declaradas sin ningún consumidor real ni plan de
usarlas.

**DECISIÓN 6 (final):** el corte de turno (fin de utterance) en la
**captura en vivo** usa un umbral simple de energía RMS + duración de
silencio configurable (`voice/audio_io.py::record_until_silence`) — **no**
un VAD dedicado en esa capa. La pieza de VAD real del pipeline
(Silero VAD) vive en cambio dentro de `FasterWhisperProvider`
(`vad_filter=True`, ver sección 2 y decisión 4) para limpiar/filtrar el
clip ya capturado antes/durante la transcripción — separar estas dos
responsabilidades (corte de turno en vivo vs. limpieza de la señal ya
grabada) evitó tener que sumar la dependencia pesada del paquete
`silero-vad` (que instala PyTorch completo, +2GB con `torchaudio`) solo
para el corte de turno, cuando `faster-whisper` ya trae un Silero VAD
embebido en ONNX sin ese costo.

---

## 5. Cómo entra esto al Kernel/API

Esta era la pregunta arquitectónica central del documento — se presentaron
tres opciones sin decidir en silencio.

**DECISIÓN 2 (final): Opción A.**

### Opción A — Proceso de voz standalone, cliente de `POST /message` (elegida)

Voice corre como su **propio proceso local** (conceptualmente parte de
`desktop/`, no de `api/` ni de `core/`): un loop que escucha el
micrófono, detecta la wake word, transcribe localmente, y le pega a
`POST /message` **exactamente como cualquier otro cliente HTTP** (el
mismo endpoint que ya prueba `tests/integration/test_api_message.py`),
recibe `response_text`, lo sintetiza localmente y lo reproduce.

**Motivos:**
- **Cero cambios en `api.py`/`Planner`/`Brain`/`Kernel`.** Decisión 7 de
  `Planner.spec.md` ya anticipó literalmente este caso de uso — no hay
  nada que reabrir ni tocar.
- **El micrófono y el parlante son recursos de la máquina del usuario**,
  no del proceso servidor. `Kernel`/`api.py` hoy corren perfectamente en
  una máquina sin audio (un servidor headless) — mezclar acceso a
  hardware de audio ahí sería un acoplamiento real, no cosmético.
  `docs/03_PROJECT_STRUCTURE.md` ya separa `desktop/` de `voice/`/`api/`
  a nivel de carpetas, coherente con esto.
- **Coherente con "offline-first" de `docs/VISION.md`**: todo el tramo de
  audio (wake word, STT, TTS) corre en la máquina del usuario sin
  necesitar red, salvo la llamada a `POST /message` que ya corre
  localmente hoy en la mayoría de los casos de uso previstos (Ollama
  local también).
- Reutiliza `session_id` para que Voice tenga memoria de conversación
  entre turnos **gratis**, sin escribir nada nuevo — el Planner ya
  resuelve esto (ver `PROGRESS.md`, sección de Memory conectada al
  Planner).

**Contras:** un cliente de voz que corra en una máquina distinta a la del
servidor necesita esa máquina alcanzable por red para `POST /message`
(no es un problema hoy, todo corre en un solo proceso/máquina, pero vale
decirlo).

### Opción B — Endpoint HTTP dedicado (ej. `POST /voice/message`, recibe/devuelve audio)

El servidor recibe audio crudo, hace STT server-side, llama al Planner
internamente (sin pasar por HTTP), hace TTS server-side, devuelve audio.

**Motivos a favor:** permite clientes "delgados" (ej. un dispositivo IoT
que solo manda audio) y centraliza cómputo pesado (Whisper) en una
máquina con mejor hardware (GPU) que el dispositivo del usuario.

**Motivos en contra:** la detección de wake word **igual tiene que correr
localmente** en el dispositivo del usuario pase lo que pase (no se puede
detectar una wake word sobre un stream continuo sin tener el micrófono
ahí) — así que esta opción no elimina la necesidad de un componente local,
solo mueve STT/TTS al servidor. Agrega latencia de red real (subir/bajar
audio) contra offline-first. Requiere código nuevo en `api.py` (manejo de
audio binario, no solo JSON) que la Opción A no necesita en absoluto.

### Opción C — Parte del loop de `Kernel.run()`

**Descartada explícitamente, sin ambigüedad.** `Kernel.run()` es
housekeeping de fondo sin estado de sesión de usuario (`memory.clear_expired()`
en un intervalo, ver `core/kernel.py`) — un loop de captura de audio
continuo, con estado de conversación por usuario/dispositivo, es un
concern completamente distinto. Además, desde la tarea que unificó
`AgentManager`, `Kernel` vive **dentro del proceso de `api.py`**
(`PROGRESS.md`) — ese proceso puede correr en un servidor sin ningún
hardware de audio real. Meter acceso a micrófono/parlante ahí rompería esa
independencia sin ganar nada a cambio.

**Confirmado: Opción A.** Motivo de una línea: ya está pre-autorizada por
una decisión previa (Planner.spec.md #7), no toca código existente, y es
la única que no acopla hardware de audio a un proceso que hoy corre
perfectamente sin él. Implementado en `src/aries/voice/pipeline.py`
(`VoicePipeline`), que consume `POST /message` vía `httpx.AsyncClient`
igual que cualquier otro cliente HTTP — cero líneas nuevas en `api.py`.

---

## 6. Confirmación de acciones destructivas por voz

El mecanismo ya existe (`needs_confirmation`/`confirmed`, decisión 5 de
`Planner.spec.md`) — lo nuevo acá es **cómo se recolecta esa confirmación
cuando el canal es voz, no texto/UI**.

**DECISIÓN 5 (final):** se acepta confirmar por voz — **pero no con un "sí"
suelto**. Flujo implementado: si `POST /message` devuelve
`needs_confirmation=True`, el pipeline sintetiza y reproduce el motivo
(`error`, que ya lo trae) más una instrucción explícita para decir la
**frase de confirmación exacta** (`"confirmo"`, normalizada — minúsculas,
sin acentos ni puntuación — antes de comparar, para no fallar por un
signo de puntuación fantasma de la transcripción), graba la respuesta,
transcribe, y **solo si el texto normalizado matchea exactamente**
`"confirmo"` reintenta `POST /message` con el mismo `user_input` original
y `confirmed=True`. Cualquier otra cosa transcripta (silencio, "sí",
"no", una frase distinta) se trata como **no confirmado** — el pipeline
avisa por voz que canceló la acción y no reintenta.

Esto mitiga (sin eliminar del todo) el riesgo real que un "sí"/"no" suelto
tendría: una palabra de una sola sílaba es más fácil de transcribir mal
por error de STT, o de interpretar erróneamente si el usuario le hablaba
a otra persona, que una palabra específica y poco ambigua como "confirmo"
dicha a propósito. No se llegó a rechazar confirmación por voz por
completo para acciones destructivas (la otra alternativa que este
documento había dejado abierta) — la frase exacta se consideró suficiente
mitigación sin degradar la experiencia de un asistente de voz a "nunca
podés confirmar nada hablando".

---

## 7. Manejo de errores — mismo criterio que el resto del proyecto

- `ISTTProvider`/`ITTSProvider` **nunca propagan excepciones sin capturar
  más allá de su propio método** salvo lo ya documentado en cada contrato
  (`VoiceError`/`TimeoutError` como los únicos tipos esperados) — mismo
  criterio que `IAgent.execute()`/`PluginRegistry.load()`/etc. en todo el
  proyecto.
- Si STT no logra transcribir nada inteligible (audio vacío, ruido): el
  pipeline de Voice no llama a `POST /message` en absoluto — no tiene
  sentido mandarle al Planner una transcripción vacía o basura. Se
  reproduce (vía TTS) un mensaje corto tipo "no te escuché bien" y se
  vuelve a esperar la wake word. Ningún cambio en el Planner: esto se
  filtra antes de que el texto llegue a `POST /message`.
- Si `ILLMProvider`/Ollama no está disponible: esto **ya lo maneja** el
  Planner/Kernel hoy (`Kernel.initialize()` ya loguea si Ollama no
  responde, `Planner.handle()` nunca propaga) — Voice no necesita lógica
  nueva, el fallo ya vuelve como `PlanExecutionResult(success=False,
  error=...)`, que Voice sintetiza y reproduce tal cual, igual que
  cualquier otro error del Planner.
- Si el proveedor TTS falla al sintetizar la respuesta (o el de por
  defecto no está disponible): no hay nada que "decir" — el pipeline debe
  degradar a algún indicador no verbal (ej. un sonido corto de error) en
  vez de fallar en silencio total sin que el usuario sepa que algo salió
  mal. Detalle de implementación, no una decisión de arquitectura.

---

## 8. Resumen de las 8 decisiones finales

1. **Wake word:** `IWakeWordProvider` **sí** tiene contrato propio
   (`docs/contracts/IWakeWordProvider.md`). Default: `OpenWakeWordProvider`
   con el modelo pre-entrenado `hey_jarvis` (no existe todavía un modelo
   "Aries" entrenado — limitación conocida, ver `PROGRESS.md`).
2. **Integración a Kernel/API:** Opción A — proceso de voz standalone
   (`src/aries/voice/pipeline.py`) que reusa `POST /message` como
   cualquier cliente HTTP. Cero cambios en `api.py`/`Planner`/`Brain`/`Kernel`.
3. **Captura/reproducción de audio:** `sounddevice` (dependencia nueva,
   aprobada). `SpeechRecognition`/`pydub` removidas de `pyproject.toml`
   (quedaban declaradas sin plan real de usarlas).
4. **Formato de audio interno:** PCM WAV, mono, 16kHz — confirmado y
   verificado empíricamente contra `faster-whisper` (rechaza PCM sin
   header).
5. **Confirmación de acciones destructivas por voz:** se acepta, pero
   exige la frase exacta `"confirmo"` (normalizada) — no un "sí"/"no"
   suelto. Cualquier otra respuesta se trata como no confirmado.
6. **VAD/corte de turno:** corte por energía RMS simple en la captura en
   vivo (`voice/audio_io.py`); Silero VAD real (vía `vad_filter=True` de
   `faster-whisper`, sin dependencia de `torch`) se usa dentro de
   `FasterWhisperProvider` para limpiar el clip ya capturado, no para el
   corte de turno en sí.
7. **Dónde vive el código:** todo en `src/aries/voice/` (contratos en
   `src/aries/contracts/`, implementaciones + orquestación en
   `src/aries/voice/`) — `desktop/` queda como consumidor futuro, no
   dueño del loop de captura/reproducción.
8. **`session_id` de Voice:** uno nuevo por cada activación de wake word
   (`f"voice-{uuid4()}"`), no uno persistente por dispositivo. El
   contexto de conversación (vía `IMemory`, ya conectado al Planner) dura
   lo que dura una sola interacción activada por wake word, no entre
   reinicios del pipeline.

Las 8 están implementadas en `src/aries/contracts/` (`wake_word.py`,
`stt.py`, `tts.py`) y `src/aries/voice/` (`openwakeword_provider.py`,
`faster_whisper_provider.py`, `piper_provider.py`, `audio_io.py`,
`pipeline.py`) — ver `PROGRESS.md` para el detalle de archivos y tests.

## Referencias
- `docs/01_ARCHITECTURE.md`, `docs/02_TECH_STACK.md`, `docs/VISION.md`
- `docs/contracts/ILLMProvider.md` (patrón replicado por `ISTTProvider.md`/`ITTSProvider.md`/`IWakeWordProvider.md`)
- `docs/contracts/ISTTProvider.md`, `docs/contracts/ITTSProvider.md`, `docs/contracts/IWakeWordProvider.md`
- `docs/specs/Planner.spec.md` (front door HTTP ya decidido y implementado; mecanismo de confirmación reusado)
- `src/aries/config/settings.py` (`voice_enabled` y los `voice_*` nuevos)
- `src/aries/exceptions/__init__.py` (`VoiceError`)
- `pyproject.toml` (extra `voice`: `piper-tts`, `faster-whisper`, `sounddevice`, `openwakeword`)
- `src/aries/contracts/wake_word.py`, `stt.py`, `tts.py`; `src/aries/voice/` (implementación completa)
