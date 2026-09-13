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

## Decisión 1: frase — "Hola Aries"

Se evaluaron dos opciones:

- **"Aries" sola** — más corta y rápida de decir, pero de mayor riesgo de
  falso positivo: puede confundirse con conversación casual (astrología,
  "a ver", nombres parecidos). Un solo token corto no es el patrón que usan
  las wake words pre-entrenadas de openWakeWord (`hey_jarvis`,
  `hey_mycroft`) ni la mayoría de asistentes comerciales (`ok_google`,
  `hey_siri`) — todas usan un prefijo de activación además del nombre.
- **"Hola Aries"** (elegida) — sigue ese mismo patrón "prefijo + nombre",
  da al clasificador más contenido fonético distintivo (4-5 sílabas vs. 2-3)
  para diferenciar de habla casual, a costa de tardar un poco más en
  decirse. Confirmado por el usuario.

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

Una vez entrenado `hola_aries.onnx`:

1. El `.onnx` resultante se guarda en el repo (ubicación a definir al
   llegar a este paso — candidato: `models/wakeword/hola_aries.onnx`, en
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

## Estado

- [x] Frase decidida: "Hola Aries"
- [x] Fuente de datos decidida: grabación real
- [x] Cómputo decidido: local/CPU
- [x] `pyproject.toml`: extra `voice-training` agregado
- [x] `tools/wake_word_training/record_samples.py`: script de grabación
- [ ] Grabar 150-300 tomas reales (usuario, en curso)
- [ ] Descargar datasets de negativos precomputados
- [ ] Armar config YAML de entrenamiento (`piper_sample_generator_path`
      apunta a un clone vacío/no usado solo para satisfacer el import
      incondicional de `train.py` línea 638-639, ver nota abajo)
- [ ] Entrenar, evaluar recall/falsos-positivos, ajustar threshold
- [ ] Integrar `.onnx` final (Decisión 4)

**Nota técnica pendiente de resolver al armar el config:** `train.py`
importa `generate_samples` desde `piper_sample_generator_path`
incondicionalmente al arrancar (línea 638-639), incluso si no se usa el
flag `--generate_clips` — hace falta clonar `piper-sample-generator` igual
(sin descargar su checkpoint en inglés) solo para que el import no falle,
o parchear esa importación para hacerla condicional al flag. Se decide al
llegar a esa etapa, no bloquea la grabación de muestras.

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
