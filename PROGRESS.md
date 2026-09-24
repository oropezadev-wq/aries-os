# Aries OS — Progreso

> Fuente de verdad del estado del proyecto. Se actualiza al TERMINAR cada tarea, no al empezarla.
> Antes de cualquier tarea nueva, leer este archivo primero.

## Seguimiento de uso real — criterio de éxito de Fase 1 (`docs/VISION.md`)

> Criterio: **2 semanas SEGUIDAS** de uso real diario de Voice + Routines +
> al menos 2 agentes, sin ninguna falla grave. Falla grave = algo que
> impide usar el sistema (no un bug cosmético). **Una falla grave resetea
> este contador a cero**, no descuenta solo ese día — un criterio que
> nadie mide no sirve, por eso una línea acá por cada día real.

**Contador PAUSADO desde el 2026-09-20 (decisión del usuario, ver `docs/VISION.md`).** Motivo: la tarea de Task Scheduler "Aries OS" está desregistrada (verificado) por el problema eléctrico del equipo, y sin arranque automático no se puede validar que Aries se recupera solo — justo la regla de abajo. Contar días de uso manual habría dejado llegar al día 14 sin haber probado nunca el arranque desatendido real. Mientras esté pausado el contador no avanza ni se resetea; hoy hay **0 días contados** (el día 1 nunca se completó). **El contador arranca (desde el día 1) recién cuando se cumplan las tres condiciones** (decisión del usuario, 2026-09-20; ver `docs/VISION.md`): (1) regulador/UPS conseguido; (2) tarea de Task Scheduler registrada de nuevo (`scripts\register-aries-task.ps1`); (3) **wake word que detecte la voz del usuario de forma confiable, con audio de captura verificado como sano** (sin compuerta ni filtrado de Windows; reformulada el 2026-09-20, antes decía "wake word propia en español" — ver la revisión del diagnóstico de Voice más abajo). **Aclarado el 2026-09-24: push-to-talk (hotkey global, sumado como vía de activación adicional — ver "Push-to-talk" más abajo) NO cuenta para la condición (3) — el criterio sigue siendo manos libres.** Los días de uso manual mientras tanto se anotan abajo como observación, sin sumar.

**Regla aclarada el 2026-09-20 (decisión del usuario, ver `docs/VISION.md`):** una caída del equipo por hardware (apagado o reinicio espontáneo) NO resetea el contador si Aries se recupera solo al volver a iniciar sesión, sin intervención. Se anota igual acá, en la fila del día, con su nota.

**Excepción temporal retirada (2026-09-20):** se había anotado una excepción ("arrancar a mano tras una caída del equipo no es falla grave", commit `ebbd96b`); se retiró porque suspendía justo la regla que valida el arranque desatendido. Mientras tanto Aries se arranca a mano con `scripts\start-aries.ps1`.

Días contados: ninguno todavía.

### Observaciones de uso manual (no suman al contador)

| Fecha | Voice | Routines | Agentes usados | Incidentes | Notas |
|---|---|---|---|---|---|
| 2026-09-20 | pendiente | pendiente | pendiente | pendiente | Sin relato de uso real todavía. Validación (no es uso): reinicio en frío de Windows OK (reportado por el usuario; verificado en `logs/supervisor.log`): inicio de sesión 08:29:43 → supervisor 08:30:08 → API 08:30:14 → Voice 08:30:26, `/health` en `ok` en los 3 checks, sin líneas ADVERTENCIA/ALERTA. |

### Diagnóstico de Voice del 2026-09-20 ("no detecta 'hey jarvis'")

- **Síntoma:** las sesiones de las 10:52 y 11:49 (esta corrió ~10 h) tuvieron 0 detecciones, y el usuario dijo "hey jarvis" repetidas veces sin respuesta. Antes, las de las 08:30 y 09:56 habían tenido 47 y 20.
- **Descartado (medido, no supuesto):** permiso de micrófono para apps de escritorio (`Allow`); volumen de entrada 98 % y sin silenciar; mejoras de audio desactivadas en el endpoint activo (clave `{1da5d803-…},5` = 1, que interpreto como "desactivar mejoras" — a confirmar visualmente en Configuración de sonido); audio real por WASAPI/MME/DirectSound/WDM-KS (pico −17 a −20 dBFS, sin muestras en cero, energía sana sobre 300 Hz); modelo y onnxruntime (21 tests con detección real pasan); camino en vivo (`.aries/wake_probe.py`, mismas clases que Aries: scores 0,00001–0,0018 con el ambiente).
- **Hallazgo:** con la sonda, el "hey jarvis" del usuario da score máximo **0,033** (WASAPI/default) y 0,017 (MME) contra un umbral de 0,05 (`VOICE_WAKE_WORD_THRESHOLD` en `.env`). Las 67 detecciones de la mañana **fueron falsos disparos por habla de fondo** (videos/TV; el STT transcribió cosas como "¡Suscríbete!"), con scores 0,051–0,256 (mediana 0,083 y 0,074): **más altos que el "hey jarvis" real del usuario**. Ningún umbral puede separar las dos cosas. La mañana "funcionaba" solo porque el ambiente disparaba el detector; nunca hubo un baseline sano de detección genuina (el único dato previo es 0,056 del 2026-09-13, también al filo).
- **Conclusión (EN REVISIÓN, ver "Revisión del diagnóstico" más abajo):** `hey_jarvis` (modelo en inglés) no es viable para esta voz. El arreglo real es la wake word propia en español (`docs/specs/WakeWordTraining.spec.md`; al 2026-09-20 el dataset tiene 30 tomas de las 150–300 objetivo).
- **Efecto colateral:** cada falso disparo graba hasta 10 s, corre STT (Whisper small en CPU) y termina en una llamada al LLM (`neural-chat`, ~7B): 67 disparos en ~2,5 h de la mañana y 53 solicitudes a Ollama en los logs de la API de esas dos sesiones. Dos de las tres caídas del equipo de hoy (09:51 y 10:50) ocurrieron durante sesiones con esos disparos frecuentes; la de las 21:42 fue con Aries ocioso y las del 15 y 19/09 sin Aries corriendo. Es una correlación, no una causa demostrada.
- **Privacidad:** los logs INFO de Voice guardan el texto transcripto tras cada disparo, o sea conversaciones de fondo. Están en `logs/` (ignorado por git, retención 14 días).
- **Decidido por el usuario (2026-09-20):** el criterio de Fase 1 exige Voice en uso diario, así que una wake word que funcione pasa a ser condición para que el contador arranque, junto con el UPS y el re-registro de la tarea (ver arriba). **Reformulada el mismo día** (objeción del supervisor, aprobada por el usuario): la condición pasó de "wake word propia en español entrenada y funcionando" a "wake word que detecte mi voz de forma confiable, con audio de captura verificado como sano (sin compuerta ni filtrado de Windows)", para no cerrar la puerta a que el problema sea solo audio degradado, más barato de arreglar que entrenar un modelo. **Abierto:** "confiable" no tiene todavía una definición medible (ej. cuántas de N veces detecta la frase real y cuántos falsos disparos por hora tolera); "audio sano" sí se puede verificar con las sondas de `.aries/` (ceros digitales, bandas, comparación WASAPI vs WDM-KS).
- **Tomas de "Hola Aries" archivadas (2026-09-20, a pedido del usuario):** las 30 del 2026-09-11 se movieron (no se borraron; 27 + 3, mismos bytes) a `tools/wake_word_training/dataset/_descartado_2026-09-11_audio_degradado/`, con un `LEEME.txt` del motivo. `run_training.py` y `record_samples.py` leen solo `dataset/positive_train|test/`, que quedaron vacías, así que el próximo entrenamiento no las mezcla. La carpeta está ignorada por git. El camino de captura ya se verificó sano (2026-09-21, ver "Revisión del diagnóstico"), pero **antes de grabar tomas nuevas** se corre la sonda de pronunciación (puede evitar tener que grabar), y con las primeras tomas se corre `.aries/check_takes.py`.
- **Mitigación aplicada (2026-09-20, a pedido del usuario):** `VOICE_WAKE_WORD_THRESHOLD` subido de 0,05 a **0,3** en `.env` (máximo del ambiente observado: 0,256). Elimina los falsos disparos; a cambio Voice queda inerte con `hey_jarvis`, que de todos modos no detectaba la voz del usuario. Para pruebas puntuales se puede pisar por proceso con la variable de entorno `VOICE_WAKE_WORD_THRESHOLD` (pydantic-settings la prioriza sobre `.env`, verificado), sin editar el archivo.
- **Nota:** la sonda no soporta WDM-KS (API bloqueante de PortAudio no disponible en ese backend); fue una mala sugerencia, no un hallazgo del micrófono.

#### Revisión del diagnóstico de Voice (2026-09-20, a pedido del supervisor)

- **Objeción del supervisor (válida):** con audio sano `hey_jarvis` debería dar ~0,40–0,49, no 0,033, y puede seguir habiendo degradación de audio tipo Voice Clarity. El diagnóstico anterior había medido solo el camino de *hoy* con ruido ambiente (nivel, permisos, registro, modelo) y nunca el espectro de habla ni las tomas grabadas; concluir "voz/modelo" desde un score marginal sin descartar eso fue prematuro.
- **Las 30 tomas de "Hola Aries"** (27 train + 3 test) se grabaron el **2026-09-11 entre las 23:51 y las 23:52**, con el mismo camino WASAPI de Aries, o sea 2 días antes de desactivar las mejoras de audio (13/09). Medido:
  - **Espectro:** 28 de 30 tienen >70 % de la energía bajo 300 Hz (mediana 82,6 %; el patrón degradado del 13/09 fue ~76 %); centroide mediano 238 Hz; 95 % de la energía bajo ~625 Hz; banda 1–4 kHz ≈ 2 %.
  - **Silencio digital (la evidencia fuerte):** mediana de **21,8 %** de muestras en cero exacto; **18 de 30** con rachas de ≥100 ms de silencio absoluto (máximo 790 ms) y 12 con SNR de 85–153 dB. Un micrófono real siempre tiene piso de ruido: esto es la firma de una compuerta/supresión de ruido en la cadena de captura. **Hoy**, por WASAPI y por WDM-KS: 0,19 % de ceros y racha máxima 0 ms.
  - **Descartado que lo produzca el código:** `record_until_silence` solo concatena frames crudos y corta; el único relleno con ceros del camino (`np.pad` del resampleo) agrega 1–2 muestras por frame.
  - **Salvedad honesta:** la referencia sintética de Piper (otra voz, sin efecto de proximidad del micrófono) no es un patrón sano perfecto, y el porcentaje bajo 300 Hz por sí solo no prueba nada (una voz grave con micrófono cercano ya concentra energía ahí). La firma de compuerta sí es concluyente.
- **Conclusión sobre las tomas:** se capturaron por un camino degradado y **no sirven para entrenar**. Decisión de archivarlas (mover aparte, no borrar) pendiente del usuario; mientras estén en `dataset/positive_train` y `positive_test` un entrenamiento las mezclaría con las tomas nuevas.
- **Estado del camino de hoy:** sin compuerta y con el mismo piso de ruido por WASAPI (−39,1 dBFS) que por WDM-KS, que no pasa por el motor de audio (−40,8 dBFS): en ambiente, el motor compartido no está suprimiendo nada. La clave del registro del endpoint activo sigue diciendo mejoras desactivadas.
- **Sonda de habla del usuario (2026-09-21, `.aries/speech_probe.py`, 4 frases "hey jarvis" por camino):**

  | Camino | score máx | <300 Hz | ceros digitales |
  |---|---|---|---|
  | WASAPI (el de Aries) | 0,019 | 39,8 % | 0,15 % |
  | WDM-KS (sin motor de Windows) | 0,035 | 51,4 % | 0,10 % |
  | MME | 0,003 | 38,1 % | 0,11 % |
  | DirectSound | 0,003 | 50,3 % | 0,11 % |
  | *(tomas viejas, referencia)* | – | 82,6 % | 21,8 % |

  Ningún camino tiene compuerta ni el patrón degradado, y WDM-KS ≈ WASAPI, o sea que el motor de audio de Windows no degrada. Ninguno se acerca a 0,05. Nota: con la misma frase el score varió hasta 10× entre caminos (0,003 vs 0,035), así que un único número por ronda es ruidoso.
- **Experimento de control electrónico (2026-09-21, sin micrófono, mismo detector y mismos frames de 1280):** "hey jarvis" limpio en inglés (Piper) → **0,998**; el mismo audio con pico de −3 a −50 dBFS → **0,998–0,999** (el volumen no importa); pasa-bajos a 300 Hz → 0,386 y banda telefónica 300–3400 Hz → 0,998 (filtrar el espectro por sí solo no explica 0,03); frase con **fonética española**: es_ES "hey jarvis" **0,000**, "hei yarvis" 0,002, "jei jarvis" 0,000; es_MX "hey jarvis" **0,103**, "hei yarvis" **0,487**, "jei jarvis" 0,012. El modelo es extremadamente sensible a la fonética: un texto leído con fonética española da 0,00–0,10, y una aproximación fonética ("hei yarvis") llegó a 0,49 con una de las voces. **Salvedad:** son voces sintéticas, un proxy y no la voz del usuario.
- **Lectura actual:** el pipeline funciona (0,998 con audio limpio), el camino de captura de hoy es sano, el volumen y el filtrado espectral quedan descartados como explicación suficiente; lo que queda es pronunciación/acento, **por descarte y con un proxy que lo reproduce, todavía no medida con la voz real**. La expectativa de 0,40–0,49 con audio sano no es un número del pipeline (que da ~1,0 con voz inglesa limpia), sino de un hablante nativo.
- **Pendiente antes de grabar tomas:** `.aries/pronunciation_probe.py` (4 rondas con la voz real por WASAPI: normal, "hei YAR-vis", "hey JAR-vis" con la j inglesa, estilo película; mide picos por frase y cuántos pasan 0,3). Si alguna pronunciación supera 0,3 de forma consistente, `hey_jarvis` cumpliría la condición (3) del contador sin entrenar nada. Para las tomas nuevas: `.aries/check_takes.py` (falla con ≥2 % de ceros digitales o racha ≥50 ms; validado: 30/30 tomas viejas fallan, una captura sana de hoy pasa).

#### Entrenamiento del modelo custom "Oye Aries" (2026-09-21 en adelante)

- **Decisión (2026-09-21):** en vez de la sonda de pronunciación, se entrena un modelo propio con la voz real del usuario en vez de seguir con `hey_jarvis`. Frase revisada de "Hola Aries" a **"Oye Aries"**. Se reutiliza el pipeline ya existente (`tools/wake_word_training/`); decisiones de diseño completas en `docs/specs/WakeWordTraining.spec.md` (Decisiones 1 y 5).
- **Primera corrida de prueba (2026-09-21, 101 tomas reales):** comparación de scores crudos `hey_jarvis` vs el modelo nuevo sobre las mismas 101 tomas (sin aumentar) dio mediana 0,0005 vs 0,55 — señal fuerte, pero **sesgada**: el modelo había visto esas mismas tomas (aumentadas) durante su propio entrenamiento. Marcada explícitamente como "señal temprana", no como verificación real.
- **Objeción del supervisor (2026-09-21/22) — metodología de evaluación:** comparar scores crudos sobre datos que el modelo ya vio no es válido. Pide 4 puntos: (1) congelar un set de evaluación por sesión, (2) definir una métrica real (falso rechazo a una tasa fija de falsas activaciones/hora), (3) medir falsas activaciones en el ambiente real del usuario, (4) grabar negativos difíciles ("oye"/"aries" sueltos, para que el modelo no aprenda el atajo de dispararse con una sola palabra). Estado y detalle completo de cada punto: `docs/specs/WakeWordTraining.spec.md`, Decisión 5.
- **Set de evaluación congelado (2026-09-21):** 30 de las 101 tomas movidas a `dataset/eval_frozen/`, nunca tocadas por entrenamiento desde entonces. Salvedad honesta: las dos "sesiones" detectadas por fecha de modificación son del mismo día, separadas por ~35 min — no la diversidad de sesión real (otro día/estado de voz) que busca el punto 1 en espíritu; se congeló igual como punto de partida.
- **Negativos difíciles grabados (2026-09-22):** 80 tomas reales (20 × "oye mira"/"oye tu"/"oye ya"/"aries" sola), cableadas en el entrenamiento como fuente de negativos (`training_config.yaml`, `feature_data_files.hard_negatives`).
- **Audio ambiente real grabado (2026-09-22):** 90 min de audio de fondo variado (YouTube, voces + música) con el micrófono real, `dataset/ambient_audio/`.
- **Evaluación real (2026-09-22, `tools/wake_word_training/evaluate_model.py`) — resultado honesto, no positivo:** sobre las 30 tomas de `eval_frozen/` (nunca vistas) y las 90 min de audio ambiente (streaming continuo, frame por frame, igual que en producción, no ventanas de duración fija):

  | Umbral | Recall (eval_frozen) | Falso rechazo | FA/hora (ambiente) |
  |---|---|---|---|
  | 0,50 | 20 % | 80 % | 2,00 |
  | 0,70 | 13 % | 87 % | 1,33 |
  | 0,80 | 10 % | 90 % | 0,67 |

  **Ningún umbral da a la vez FA/hora ≤ 0,5 (el target de `training_config.yaml`) y un recall usable.** El mejor punto de compromiso (umbral 0,80) rechaza el 90 % de las veces que el usuario realmente dice la frase. Como referencia, `hey_jarvis` da FA/hora = 0 en el mismo rango, pero porque tiene 0 % de recall en absoluto — no es una señal de estar bien calibrado, es que nunca reconoce nada en español.
  - **Hipótesis probada y descartada:** bajar el peso de los negativos difíciles en el batch de entrenamiento (32→16) no cambió el resultado de forma significativa (90 % vs 93 % de falso rechazo al mismo FA/hora — diferencia de 1 toma sobre 30, dentro del ruido de muestra). No era la causa dominante.
  - **Lectura:** con solo 63 tomas reales de entrenamiento (126 aumentadas), el modelo no generaliza a una toma nueva no vista — consistente con "hace falta más dato", no con un problema de configuración puntual. No se sigue ajustando hiperparámetros a ciegas sobre esto.
- **Re-confirmado con la métrica de punto de operación interpolada (2026-09-24, mismo modelo `oye_aries.onnx`, sin reentrenar — el usuario pidió explícitamente no arrancar la corrida de producción hasta terminar de grabar):** `evaluate_model.py` ahora interpola el umbral exacto donde FA/hora cruza el target (en vez de reportar el punto más cercano entre umbrales probados manualmente — ver `docs/specs/WakeWordTraining.spec.md`, refinamiento del punto 2). Resultado sobre los mismos `eval_frozen/`+`ambient_audio/` (1,50 h, 67500 frames): **umbral=0,8821 → falso rechazo=93,3 % (recall=6,7 %) al FA/hora=0,5 objetivo.** Consistente con la corrida del 2026-09-22 (mismo modelo, sin cambios) — no es una regresión, es una medición más precisa del mismo resultado negativo ya conocido. No cambia la conclusión ni el próximo paso.
- **Próximo paso:** seguir grabando positivas hacia las 150-200 (plan en curso, 101/200 al momento de esta nota — 71 disponibles para entrenar tras separar `eval_frozen/`) y volver a correr `evaluate_model.py` con el dataset más grande — la metodología y las herramientas ya están listas y son reutilizables sin trabajo adicional. **La corrida de entrenamiento de producción (steps=10000) queda explícitamente pausada hasta que el usuario termine de grabar** (decisión del usuario, 2026-09-24) — no arrancarla sin ese dataset completo.

#### Push-to-talk (2026-09-24)

Vía de activación adicional a la wake word — un hotkey global. **No
cuenta para la condición (3) del contador** (ver arriba): el criterio de
Fase 1 sigue siendo manos libres, push-to-talk es un atajo para cuando
eso no es práctico todavía, no un reemplazo.

4 decisiones del usuario, confirmadas antes de escribir código:

- **Misma vía de activación que la wake word, mismo punto de entrada**
  (no un camino paralelo a whisper): `VoicePipeline._listen_for_activation_sync`
  ahora espera wake word O hotkey en el mismo loop — de ahí en más
  (grabar, STT, `POST /message`, confirmación, hablar) el flujo es
  idéntico sin importar quién activó el turno.
- **Guarda de concurrencia — se ignora, no cancela:** una pulsación
  mientras el pipeline ya está escuchando/procesando se descarta
  directo, no se encola para la próxima vez que quede libre.
- **Feedback sonoro:** `winsound.Beep` (stdlib, sin dependencia nueva)
  al empezar a grabar y al cortar por silencio — dos tonos distintos.
  El proceso corre con ventana oculta, sin consola visible; sin esto no
  hay ninguna señal de que está escuchando.
- **El listener del hotkey vive dentro de `VoicePipeline` directamente**
  (arrancado/parado en `run_forever()`, no vía MessageBus/Redis) —
  sigue funcionando aunque Redis esté caído.

**Mecanismo del hotkey — decisión de diseño no trivial, confirmada por
el usuario:** `ctypes` + `RegisterHotKey` de Win32 (stdlib), no una
librería de terceros (`keyboard`/`pynput`) — sin dependencia nueva.
`RegisterHotKey` exige una ventana con loop de mensajes para recibir
`WM_HOTKEY`; se usa una ventana "message-only" (nunca visible) en un
hilo propio. Combinación configurable (`Settings.voice_hotkey_combo`,
default `ctrl+alt+shift+v`), elegida rara a propósito para no pisar
atajos de Windows/VSCode.

Dos bugs reales de `ctypes` encontrados y corregidos durante la
verificación (no eran obvios de antemano — ver commit
`bda258e`): (1) sin `argtypes`/`restype` declarados explícitamente,
`ctypes` no marshalea bien un handle de 64 bits como argumento; (2)
Windows guarda el `WNDPROC` a nivel de *clase* de ventana al
registrarla, no por ventana — dos listeners con el mismo nombre de
clase en el mismo proceso terminaban compartiendo el callback del
primero que logró registrarla. Verificado con Win32 real (no
mockeado): registro/creación de ventana real, y entrega real de
`WM_HOTKEY` vía `PostMessageW` (no se puede simular una tecla física en
un entorno headless, pero esto ejercita toda la plomería real salvo la
captura física del teclado por el sistema operativo).

**Bug real con hardware real (2026-09-24), reportado por el usuario:**
hotkey y beep de inicio funcionaban, pero tras hablar el STT no
reconocía nada ("no te escuché bien"). Diagnóstico con evidencia de
`logs/voice_20260924_050834.err.log` (15 activaciones reales): las 5
fallidas compartían el mismo patrón exacto — duración ~1.1-1.3s con
el filtro VAD de faster-whisper removiendo el 100% del audio; las 10
exitosas medían 1.68-3.28s con solo una fracción chica removida.
Causa raíz: `winsound.Beep()` bloquea ~150ms, pero el `InputStream`
de `sounddevice` sigue capturando en background durante ese bloqueo
— nadie lo pausa. La primera lectura de `record_until_silence()` tras
el beep consumía ese buffer acumulado (muy probablemente la cola
acústica del propio beep, colada por acoplamiento parlante→micrófono),
que el gate de RMS interpretaba como inicio de habla real, seguido de
silencio genuino → corte antes de que el usuario llegara a decir nada.
**Fix:** `MicrophoneListener.drain()` (`audio_io.py`) descarta sin
bloquear lo acumulado en el stream, invocado en
`_listen_for_activation_sync()` justo después del beep de inicio y
antes de `record_until_silence()` (commit `21bd881`).

**Estado: fix implementado, pendiente mi verificación física — NO
dado por cerrado.** No es verificable en este entorno (sin
micrófono/hotkey real); requiere que el usuario lo prenda con
hardware real y confirme que el corte dejó de pasar antes de
considerarlo resuelto.

### Registro previo al contador vigente (no cuenta)

- **2026-09-15 — descartado como día 1.** Se había anotado como día 1, pero del 14 al 20 el usuario casi no usó Aries (equipo apagado la mayoría de esos días). El contador reinició el 2026-09-20.
- **Muerte del supervisor del 2026-09-15 (05:06, último renglón de esa corrida en `supervisor.log`, sin línea de apagado).** El usuario la atribuyó a una suspensión del equipo. El registro de eventos de Windows no lo respalda: no hay ningún evento de suspensión el 15/09, y esa sesión de Windows (arrancada 04:42 tras un apagado inesperado a las 04:41) terminó con otro apagado inesperado (Kernel-Power 41, registrado al arrancar el 2026-09-16 05:15:59). Consistente con la falla de hardware del equipo, no con un bug de Aries.
- **2026-09-19 — apagado inesperado del equipo** (arrancó 22:52:54, se cayó enseguida; Kernel-Power 41 registrado al volver a arrancar a las 23:09:07). Fue ~1 hora antes de la primera corrida de Aries de ese día (23:59), así que no hay relación con Aries. El usuario sospecha RAM defectuosa (ya venía con reinicios espontáneos; sacó un módulo y quedó en 8 GB; el problema volvió, ahora como apagado).
- **Diagnóstico de memoria de Windows (2026-09-20, reportado por el usuario):** 0 bad pages en las 12 pruebas — la RAM está sana. Hipótesis actual del usuario para las caídas: picos de corriente combinados con estar al límite de los 8 GB cuando corre todo junto (WSL2 + Redis + API + Voice); mitigación pendiente: regulador/UPS. Medición de apoyo (2026-09-20, sin Aries corriendo): 6,9 de 7,9 GB en uso y 1,0 GB libre, y no existía `.wslconfig` (WSL2 sin tope de memoria propio, default hasta el 50% de la RAM). **Mitigación aplicada (2026-09-20):** `%USERPROFILE%\.wslconfig` (fuera del repo, no versionado) con `[wsl2] memory=1GB`. Verificado con WSL en frío: la VM ve 896 MB en total, usa ~396 MB con Ubuntu + systemd y Redis ~1 MB. Ojo si se instala/usa Docker Desktop: comparte esa misma VM y quedaría limitado por este tope.
- **Suspensión/reanudación del equipo con Aries corriendo — APROBADA por el usuario (2026-09-20):** el usuario decidió hacerla ahora, por ser más relevante que el arranque en frío (el equipo sí entra en suspensión solo, ej. 2026-09-20 00:17). Es una validación, no suma al contador. Su chequeo de Voice no puede depender de "hey jarvis" (ver el diagnóstico de Voice más arriba): se usa habla de fondo cerca del micrófono para provocar una detección antes y después de suspender. **Resultado** (horas locales, Aries arrancado a mano a las 23:16, umbral en 0,05): suspensión de 12 min 28 s (Kernel-Power 42 a las 23:22:06, reanudación a las 23:34:34). Antes: 2 detecciones (0,127 y 0,113) con transcripción OK. `supervisor.log` sin ninguna línea ALERTA: el holder de WSL, la API y Voice conservaron sus PIDs y nada se relanzó. Un único warning de Redis en Voice a las 23:34:32 (`Timeout reading`, el `BLOCK` pendiente al despertar), sin repetirse: reconexión en un ciclo. Nueva detección a las 23:36:26 (0,116) con transcripción OK; `redis-cli ping` = PONG; `/health`: kernel ok, redis ok, ollama error (cerrado a propósito) → `degraded` con HTTP 200, como está diseñado. **Alcance:** una muestra y suspensión corta (S3); no cubre suspensión larga (horas/noche), rutinas que vencen durante el sueño ni la reconexión al LLM.
  - **Observación, no bloqueante y sin causa confirmada:** `stop-aries.ps1` avisó que el supervisor no bajó en 30 s y forzó el cierre. El log muestra que el supervisor **sí completó** su apagado ordenado (a las 23:40:08 detuvo Voice, API y holder y escribió "apagado"), así que no quedó nada huérfano ni estado sucio (`.aries/` sin pid ni flag, mutex libre, sin procesos). Lo que tardó fue en *notar* el `stop.flag`: por el aviso de 30 s, se infiere ~30 s en vez de los ≤ ~16 s esperables (sleep de 15 s + iteración). Hipótesis: una iteración lenta del loop (las llamadas a `wsl.exe` del supervisor no tienen timeout) tras la carga de la prueba (7 disparos con Whisper entre 23:36 y 23:39). No se puede confirmar porque el supervisor no registra cuánto dura cada iteración. Primera vez que ocurre.
  - **Mitigado (commit `8afd6e8`, 2026-09-20):** timeout duro de 10 s a las llamadas a `wsl.exe` del loop (un PING que excede el tope se loguea pero no reinicia redis-server; solo una falla definitiva lo reinicia), aviso en `supervisor.log` cuando una iteración pasa de 10 s (con la duración del chequeo de Redis), y `stop-aries.ps1` espera 60 s en vez de 30 antes de forzar. Medido: una iteración normal dura ~0,3 s. **Sigue abierto:** el backoff de reinicio de un hijo caído (hasta 300 s) no mira el `stop.flag`, así que un stop durante un backoff puede tardar; el aviso de iteración lenta lo va a mostrar si ocurre.
  - `.env`: el usuario encontró que había quedado en 0,05 tras su primera edición en VS Code y lo corrigió a 0,3 (verificado). No afecta la validez de la prueba, que usó 0,05.

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
- Ninguno. El par flaky que vivió acá varias tareas (`test_kernel_publishes_initialized_event`/`::test_kernel_publishes_shutdown_event`) se cerró — ver sección dedicada más abajo. La métrica de salud de la suite es **0 failed**, no un conteo fijo de passed — ese número crece con el proyecto y no es lo que hay que vigilar. Referencia de fecha (no es un piso a mantener, solo contexto de cuándo se corrió): 430 passed, 4 skipped al 2026-09-13.

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
- `src/aries/api.py`: `_llm_provider`/`_kernel` se construyen dentro de `lifespan()` (uno nuevo por ciclo de arranque de la app, para no reutilizar un `httpx.AsyncClient` ya cerrado — ver commit `6576742`) pero **también se reasignan a globals de módulo** (`_llm_provider`, `_kernel`, `_kernel_run_task`) como puente de compatibilidad para `get_planner()` y para los tests de integración que los leen directo (`api._kernel_run_task`, etc.). **No es el diseño final, es deuda conocida:** con dos instancias de `app` corriendo en el mismo proceso, esos globals apuntarían a la última que arrancó, no a la que los llamó. Aceptable hoy porque solo existe una instancia de `app` por proceso; revisar si alguna vez hace falta correr más de una.

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
