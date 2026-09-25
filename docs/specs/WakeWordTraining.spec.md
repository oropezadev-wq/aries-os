# WakeWordTraining — Spec

> **APROBADO** (fase de plan — grabación/entrenamiento en curso). Motivado por
> `docs/specs/Voice.spec.md` sección 3: *"entrenar un modelo custom
> 'Aries'/'Hey Aries' queda fuera de alcance... documentado como limitación
> conocida en `PROGRESS.md`"* — y por el diagnóstico real de validación con
> hardware (`PROGRESS.md`, sección "Validación de VoicePipeline con hardware
> real"): `hey_jarvis` da scores consistentemente cercanos a cero con audio
> capturado correctamente (RMS sano, sin bug de resampling ni de timing) —
> descartado como problema de pronunciación en inglés (sonidos como la "j"
> de "Jarvis") que no matchea el training data del modelo pre-entrenado.
>
> **Corrección posterior (2026-09-13):** la investigación siguió después de
> escribir este documento y encontró la causa raíz real del score-cero:
> mejoras de audio de Windows ("Foco de voz"/"Voice Clarity" en las
> propiedades del micrófono) aplicaban un filtro de banda angosta que
> aplastaba el espectro por encima de ~300Hz — no pronunciación. Ver
> `PROGRESS.md`, sección "Validación de VoicePipeline con hardware real",
> resolución final, para la cadena completa de hipótesis descartadas. **La
> decisión de entrenar "Hola Aries" en español sigue siendo válida por
> motivos de UX (una wake word propia en español en vez de "hey jarvis"
> en inglés), pero ya no es la solución a este bug puntual** — queda como
> mejora de producto a evaluar, no como fix urgente.

## Decisión 1: frase — "Oye Aries"

Se evaluaron dos opciones:

- **"Aries" sola** — más corta y rápida de decir, pero de mayor riesgo de
  falso positivo: puede confundirse con conversación casual (astrología,
  "a ver", nombres parecidos). Un solo token corto no es el patrón que usan
  las wake words pre-entrenadas de openWakeWord (`hey_jarvis`,
  `hey_mycroft`) ni la mayoría de asistentes comerciales (`ok_google`,
  `hey_siri`) — todas usan un prefijo de activación además del nombre.
- **"Hola Aries"** (elegida originalmente) — sigue ese mismo patrón
  "prefijo + nombre", da al clasificador más contenido fonético distintivo
  frente a habla casual, a costa de tardar un poco más en decirse.
  Confirmado por el usuario.

**Revisión (2026-09-21):** tras descartar `hey_jarvis` como wake word
pre-entrenada (reconocía mal la pronunciación/acento del usuario incluso
con audio verificado sano — ver `PROGRESS.md`, "Revisión del diagnóstico
de Voice"), el usuario decidió entrenar un modelo propio en vez de seguir
ajustando `hey_jarvis`. En ese momento reconsideró también la frase:
**"Oye Aries"** (elegida) en vez de "Hola Aries" — mismo patrón
"prefijo + nombre", pero una frase que el usuario prefiere por ser más
personalizada y coherente con el nombre del proyecto. Las 30 tomas
grabadas en 2026-09-11 de "Hola Aries" ya estaban descartadas por audio
degradado (`tools/wake_word_training/dataset/_descartado_2026-09-11_audio_degradado/`),
así que el cambio de frase no pierde ningún dato utilizable.

## Decisión 2: origen de las muestras positivas — grabación real, no TTS sintético

`openwakeword/train.py` (el script de entrenamiento oficial instalado en
`.venv-313/Lib/site-packages/openwakeword/train.py`) genera muestras
sintéticas vía [`piper-sample-generator`](https://github.com/rhasspy/piper-sample-generator)
usando un checkpoint multi-speaker de Piper, `en_US-libritts_r-medium.pt`
— **inglés de EEUU, sin equivalente en español**. No es la voz de Piper
que ya usa `PiperProvider` (`es_MX-claude-high.onnx`): esa es un modelo
single-speaker para síntesis de salida, no un checkpoint multi-speaker
pensado para generar miles de variaciones de un hablante distinto (que es
lo que necesita el entrenamiento para generalizar).

Investigación en el repo oficial (`dscripka/openWakeWord`,
[discussion #52](https://github.com/dscripka/openWakeWord/discussions/52)):
el propio mantenedor confirma que el bloqueo para otros idiomas es
justamente la falta de checkpoints VITS multi-speaker no ingleses, que el
modelo de embeddings de audio de base (de Google) puede tener sesgo hacia
inglés (sin confirmar empíricamente), y **no hay ningún caso documentado
de un modelo entrenado con éxito en español** en los canales oficiales del
proyecto a la fecha de esta investigación (2026-09).

**Decisión: grabar la voz real del usuario en vez de generar muestras
sintéticas.** Justificación:

- Aries es un asistente personal de un solo usuario, no un producto que
  necesite generalizar a hablantes/acentos ajenos — grabar exactamente la
  pronunciación, el micrófono y el ambiente reales del único usuario es
  estrictamente mejor que intentar aproximarlo con TTS en un idioma que ni
  siquiera es el correcto.
- Revisando `train.py` (líneas 662-693): el flag `--generate_clips` solo
  llena una carpeta (`<output_dir>/<model_name>/positive_train/`) con
  archivos `.wav` — el resto del pipeline (augmentación con RIR/ruido,
  extracción de features, entrenamiento) no distingue el origen de esos
  `.wav`. Poblar esa carpeta a mano con grabaciones reales es válido sin
  tocar el resto del script.
- `piper-sample-generator` requiere Linux para la síntesis (reportado por
  la comunidad, ver Referencias) — al no usarlo, se evita esa restricción
  por completo en el setup Windows del usuario.

**Herramienta:** `tools/wake_word_training/record_samples.py` — script de
grabación asistida (no forma parte del paquete `aries`, uso único de
desarrollo). Reusa `MicrophoneListener`/`record_until_silence` de
`aries.voice.audio_io` tal cual (mismo fix WASAPI del pipeline en vivo,
ver `PROGRESS.md`), así las condiciones de grabación son las mismas que
las de uso real. Guarda `.wav` con nombre `uuid4().hex.wav` (mismo esquema
que usaría `generate_samples()`), con split 90/10 entre
`positive_train/`/`positive_test/`.

**Cantidad objetivo:** 150-300 tomas reales — la augmentación posterior
(RIR + ruido de fondo) multiplica cada toma en variaciones adicionales
antes de entrenar, así que no hace falta igualar los miles de muestras que
usaría un pipeline 100% sintético.

**Negativas:** no requieren grabación — se descargan datasets ya
preparados de habla/ruido/música (ACAV100M, Common Voice, FMA vía
[`davidscripka/openwakeword_features`](https://huggingface.co/datasets/davidscripka/openwakeword_features)
en Hugging Face) — independientes del idioma de la wake word.

## Decisión 3: cómputo — local (CPU, Windows), no Colab

Al sacar la generación sintética de la ecuación (la parte que exigía
GPU/Linux vía `piper-sample-generator`), lo que queda corriendo es:

- Extracción de features (mel-spectrograma + embedding de Google, vía
  `onnxruntime`) — ya corre en CPU en la máquina del usuario, es la misma
  inferencia que ya hace `OpenWakeWordProvider` en runtime.
- Entrenamiento del clasificador final (`openwakeword/train.py`, clase
  `Model`): red chica (lineal/LSTM sobre features `16x96` ya precomputadas)
  — nada comparable a entrenar un LLM, factible en CPU para un dataset de
  este tamaño.

**Decisión: local, en `.venv-313`**, con Colab como plan B explícito si el
entrenamiento en CPU resulta impracticablemente lento (el propio script
reporta tiempo por step, así que la decisión de migrar se toma con datos
reales del primer intento, no a priori).

**Dependencias nuevas** (extra `voice-training` en `pyproject.toml`,
separado de `voice` porque son deps pesadas de un solo uso, no de
runtime): `torch`, `torchinfo`, `torchmetrics`, `pyyaml`.

## Decisión 4: integración del modelo final — sin tocar el contrato

Una vez entrenado `oye_aries.onnx`:

1. El `.onnx` resultante se guarda en el repo (ubicación a definir al
   llegar a este paso — candidato: `models/wakeword/oye_aries.onnx`, en
   paralelo a cómo ya se maneja el modelo de voz de Piper).
2. `Settings.voice_wake_word_model` (`src/aries/config/settings.py`)
   cambia su default de `"hey_jarvis"` a la ruta del nuevo modelo —
   `OpenWakeWordProvider`/`openwakeword.Model()` ya aceptan tanto nombres
   de modelos pre-empaquetados como rutas a `.onnx` custom directamente,
   sin cambios de código.
3. `VOICE_WAKE_WORD_THRESHOLD` se recalibra desde cero (probablemente
   arrancando en 0.5, el default) — el modelo custom debería dar scores
   reales a diferencia de `hey_jarvis`, así que no hay motivo para heredar
   el `0.05` que se usó como workaround temporal durante el diagnóstico.
4. El log TEMPORAL de diagnóstico en `pipeline.py`
   (`_listen_for_activation_sync`, el `.get("hey_jarvis")` hardcodeado) se
   remueve en vez de actualizarse — su propósito (diagnosticar el score
   crudo) ya cumplió su función con el problema resuelto.

**Contrato `IWakeWordProvider` sin cambios** — todo lo anterior es
configuración (qué modelo/threshold se le pasa a `OpenWakeWordProvider`),
no lógica nueva. Ningún test existente debería romperse.

## Decisión 5: metodología de evaluación (pedido del supervisor, 2026-09-21)

Después de la primera corrida de entrenamiento de prueba (101 tomas reales,
ver `PROGRESS.md`), el supervisor del usuario marcó 4 puntos a resolver
antes de seguir grabando positivas — comparar scores crudos entre `hey_jarvis`
y un modelo nuevo, sobre datos que el modelo ya vio (aumentados) durante su
propio entrenamiento, no es una metodología de evaluación válida:

1. **Congelar un set de evaluación separado por sesión, no por toma al
   azar** — para que corridas futuras del modelo sean comparables entre sí
   de forma justa (el mismo set, nunca tocado por entrenamiento).
2. **Definir una métrica clara antes de seguir**: falsos rechazos sobre el
   set de evaluación congelado, a una tasa fija de falsas activaciones por
   hora — no comparar scores crudos entre modelos.
3. **Medir falsas activaciones en el ambiente real del usuario** (1-2 horas
   de audio de TV/videos de fondo grabado con su micrófono) antes de
   confiar en cualquier modelo.
4. **Grabar negativos difíciles**: decenas de tomas reales diciendo "oye" +
   otra palabra ("oye mira", "oye tu", "oye ya") y "aries" sola — para que
   el clasificador no aprenda el atajo de dispararse con una sola de las
   dos palabras de la wake word en vez de la frase completa.

**Resuelto (2026-09-21), puntos 1 y 4** (los que más cambian qué grabar
después, a pedido del usuario):

- `tools/wake_word_training/record_hard_negatives.py` — script nuevo,
  graba las 4 frases del punto 4. Sin split train/test (van a sumarse como
  fuente de negativos en `feature_data_files`, no como clase positiva) —
  cablearlas en `training_config.yaml` queda pendiente hasta que haya
  grabaciones reales, no tiene sentido apuntar a un directorio vacío.
- `tools/wake_word_training/record_samples.py` — ahora registra cada
  corrida como una sesión en `dataset/sessions.jsonl` (fuente de verdad
  explícita hacia adelante, en vez de inferir sesiones por fecha de
  modificación de archivo).
- `dataset/eval_frozen/` — 30 tomas reales movidas afuera de
  `positive_train`/`positive_test` (quedan 71 para entrenar), con
  `MANIFEST.json` documentando el motivo. **Salvedad real, no cosmética:**
  las dos "sesiones" detectadas en las 101 tomas originales son ambas del
  2026-09-21, separadas por ~35 minutos (mismo cuarto/mic/estado de voz) —
  no es una sesión genuinamente distinta (otro día/momento), que es lo que
  pide el punto 1 en espíritu. Se congeló igual como punto de partida
  (decisión del usuario) — el pool de evaluación puede crecer con sesiones
  futuras realmente distintas sin perder esto. `run_training.py` nunca lee
  de `dataset/eval_frozen/` (solo de `positive_train`/`positive_test`), así
  que queda protegido de entrenamiento por construcción, no por disciplina.

**Resuelto (2026-09-22), puntos 2, 3 y 4:**

- Punto 4: 80 tomas reales grabadas ("oye mira"/"oye tu"/"oye ya"/"aries"
  sola, 20 c/u) y cableadas en `run_training.py`/`training_config.yaml`
  como fuente de negativos (`feature_data_files.hard_negatives`).
- Punto 3: 90 min de audio ambiente real grabados
  (`record_ambient_audio.py`, `dataset/ambient_audio/`).
- Punto 2: `tools/wake_word_training/evaluate_model.py` — calcula falsos
  rechazos sobre `dataset/eval_frozen/` a una tasa fija de falsas
  activaciones/hora medida en `dataset/ambient_audio/` (streaming continuo
  frame por frame, no scores crudos). **Refinado (2026-09-24):** la
  primera versión reportaba el umbral más cercano al target entre los
  valores de `--thresholds` probados — no un punto de operación exacto,
  y no comparable entre corridas si la grilla de umbrales usada difiere.
  `_frr_at_fixed_fa_per_hour()` ahora interpola el umbral exacto donde
  FA/hora cruza el target sobre una grilla fina (400 puntos), dando un
  único número objetivo y reproducible entre corridas.

**Resultado de la primera corrida con la metodología completa
(2026-09-22) — no positivo, ver `PROGRESS.md` para el detalle numérico:**
ningún umbral da a la vez FA/hora ≤ 0.5 (el target del config) y un
recall usable sobre `eval_frozen/` (mejor punto: ~90 % de falso rechazo).
Se probó bajar el peso de `hard_negatives` en el batch (32→16) como
hipótesis de causa — la diferencia resultó ser ruido de muestra (1 toma
sobre 30), así que se descartó como causa dominante. Lectura: con 63
tomas reales de entrenamiento el modelo no generaliza a una toma nueva —
consistente con necesitar más dato (el plan de seguir grabando hacia
150-200 ya estaba en curso), no con un problema de configuración. La
metodología y las herramientas quedan listas para re-evaluar sin trabajo
adicional cuando el dataset crezca.

**Re-confirmado (2026-09-24) con la métrica interpolada, mismo modelo sin
reentrenar:** umbral=0,8821 → falso rechazo=93,3 % al FA/hora=0,5
objetivo — mismo resultado negativo, medido con más precisión. Ver
`PROGRESS.md` para el detalle. **La corrida de entrenamiento de
producción (steps=10000) queda pausada a pedido explícito del usuario
hasta terminar de grabar el dataset (101/150-200 al momento de esta
nota)** — no arrancarla todavía.

## Decisión 5 bis: 3 chequeos del supervisor antes de seguir grabando (2026-09-24)

Antes de seguir grabando hacia 150-200, el supervisor pidió 3 chequeos
concretos, el más importante siendo si se están generando positivos
sintéticos con Piper. Resultado completo con evidencia real (no
hipótesis) en `PROGRESS.md`, sección "Entrenamiento del modelo custom".
Resumen:

1. **Piper sintético:** no se usa — Decisión 2 (arriba) ya lo explica:
   sin checkpoint multi-speaker en español, bloqueo confirmado por el
   propio mantenedor de openWakeWord.
2. **Herencia de config entre corridas:** `--steps` no persiste (seguro
   por diseño). Se encontró un riesgo real distinto: caché de features
   en disco reusada silenciosamente sin `--overwrite-features` —
   modelo actual verificado limpio, pero recomendado invertir el
   default (pendiente confirmación del usuario).
3. **Pendiente/cambiado de foco por el hallazgo #3 de abajo** (curva
   completa a 1/2/5 FA/hora): implementado en `evaluate_model.py
   --fa-targets`, pero el hallazgo del experimento de reentrenamiento
   (ver PROGRESS.md) es más urgente que terminar de medir la curva del
   modelo actual.

**Hallazgo no pedido, encontrado durante el experimento de "pendiente
50→101" que sí pidió el supervisor:** dos reentrenamientos controlados
(50 tomas y 63 tomas, mismo `--steps 10000 --overwrite-features`
explícito) colapsaron ambos a **recall≈0%** — peor que el modelo ya
desplegado. Evidencia de `auto_train` escalando el peso de negativos
dos veces en ambas corridas, consistente con la sospecha ya anotada en
`training_config.yaml` sobre `max_negative_weight`. **Esto cambia la
lectura de fondo: la cantidad de datos no parece ser la variable
dominante — el pipeline de entrenamiento en sí parece inestable/no
determinístico (sin seed fijada) y propenso a colapsar.** Ver
PROGRESS.md para el detalle completo y las herramientas nuevas
(`run_training.py --positive-train-dir`, `evaluate_model.py
--fa-targets`, configs `training_config_diag50/101.yaml`).

**No se investigó más profundo a propósito** (un ablation sin
`hard_negatives`, o correr varias veces con seed fija para medir tasa
de colapso, serían los siguientes pasos lógicos) — se para acá,
pendiente de que el usuario/supervisor decida cómo seguir.

## Estado

- [x] Frase decidida: "Oye Aries" (originalmente "Hola Aries", revisada 2026-09-21)
- [x] Fuente de datos decidida: grabación real
- [x] Cómputo decidido: local/CPU
- [x] `pyproject.toml`: extra `voice-training` agregado
- [x] `tools/wake_word_training/record_samples.py`: script de grabación
- [ ] Grabar 150-300 tomas reales (usuario, en curso — 101/200 grabadas
      2026-09-21, frase "Oye Aries"; 30 de esas 101 congeladas en
      `dataset/eval_frozen/`, ver Decisión 5 — quedan 71 en
      `positive_train`/`positive_test` para entrenar)
- [x] Set de evaluación congelado (Decisión 5, punto 1 del supervisor)
- [x] Negativos difíciles (Decisión 5, punto 4 del supervisor) — 80 tomas
      reales grabadas y cableadas en el entrenamiento
- [x] Métrica de evaluación real: falsos rechazos a tasa fija de falsas
      activaciones/hora (Decisión 5, punto 2 del supervisor) —
      `evaluate_model.py`
- [x] Falsas activaciones en ambiente real medidas, 90 min de audio de
      fondo (Decisión 5, punto 3 del supervisor) — resultado: modelo
      actual no usable en ningún umbral, ver arriba y `PROGRESS.md`
- [x] Descargar datasets de negativos precomputados — completo: ACAV100M
      (features, 17GB) + MIT RIR survey (270 archivos) + validation set
      (previo a esta revisión), más `background_noise/` (363 clips de
      AudioSet, ~60 min, `tools/wake_word_training/download_negatives.py`,
      2026-09-21). Solo AudioSet — se evaluó sumar FMA (segunda fuente que
      usa el notebook oficial de openWakeWord) pero `rudraml/fma` expone
      los datos vía un script de carga que la versión instalada de
      `datasets` (5.x) ya no soporta ("Dataset scripts are no longer
      supported"); se documenta como limitación conocida, no bloqueante
      (AudioSet solo ya cubre razonablemente la variedad necesaria) — se
      puede retomar más adelante si hiciera falta más variedad de ruido.
- [x] Armar config YAML de entrenamiento — hecho
      (`tools/wake_word_training/training_config.yaml`); el punto de
      `piper_sample_generator_path` está resuelto (ver nota técnica
      actualizada abajo), no por el config sino por cómo lo invoca
      `run_training.py`.
- [ ] Entrenar, evaluar recall/falsos-positivos, ajustar threshold —
      mecanismo del pipeline ya validado end-to-end (`run_training.py`,
      commit `64577a8`, 2026-09-13) con las 27 tomas viejas de "Hola
      Aries" (descartadas después por audio degradado) — confirma que
      `augment_clips` → extracción de features → `auto_train` → export a
      `.onnx` corre y el modelo resultante carga con
      `openwakeword.model.Model`. **No** confirma que el modelo en sí
      sirva (muy pocas muestras, y esas muestras después se descartaron) —
      falta correr con las 150-300 tomas reales de "Oye Aries" y evaluar
      de verdad recall/falsos-positivos.
- [ ] Integrar `.onnx` final (Decisión 4)

**Nota técnica resuelta:** `train.py` (el script oficial de
`openwakeword`) importa `generate_samples` desde
`piper_sample_generator_path` incondicionalmente al arrancar (línea
638-639), incluso sin `--generate_clips`. En vez de parchear esa
importación, `tools/wake_word_training/run_training.py` evita el problema
de raíz: importa `openwakeword.train` como módulo (nunca ejecuta su
bloque `__main__`, que es donde vive ese import) y llama directo a las
piezas necesarias (`augment_clips`, `compute_features_from_generator`,
`Model.auto_train`) — ver el docstring de ese script para el detalle
completo. `piper_sample_generator_path` en el YAML apunta a un clone
vacío de `piper-sample-generator` (sin su checkpoint en inglés) que ya
existe en el repo — no hace falta tocarlo.

## Referencias
- `docs/specs/Voice.spec.md` sección 3 (decisión 1: `hey_jarvis` como
  default temporal, límite documentado)
- `PROGRESS.md`, sección "Validación de VoicePipeline con hardware real"
  (diagnóstico completo: audio sano post-fix WASAPI, score de `hey_jarvis`
  descartado como problema de pronunciación, no de audio/timing)
- [`dscripka/openWakeWord`](https://github.com/dscripka/openWakeWord) —
  repo oficial, `notebooks/automatic_model_training.ipynb`,
  `openwakeword/train.py`
- [`rhasspy/piper-sample-generator`](https://github.com/rhasspy/piper-sample-generator)
  — generador de muestras sintéticas (inglés únicamente en la práctica)
- [Discussion #52 — "Other language"](https://github.com/dscripka/openWakeWord/discussions/52)
  — posición oficial del mantenedor sobre idiomas no ingleses
- [`davidscripka/openwakeword_features`](https://huggingface.co/datasets/davidscripka/openwakeword_features)
  — datasets de negativos precomputados (ACAV100M, Common Voice, FMA)
- [openwakeword.com/train](https://openwakeword.com/train) — servicio de
  terceros evaluado y descartado por ahora (no verificado a fondo, implica
  subir grabaciones de voz a un servicio externo) — queda como alternativa
  documentada, no descartada de forma permanente, igual que Porcupine en
  `Voice.spec.md` sección 3
- `pyproject.toml` (extra nuevo `voice-training`: `torch`, `torchinfo`,
  `torchmetrics`, `pyyaml`)
- `tools/wake_word_training/record_samples.py`
