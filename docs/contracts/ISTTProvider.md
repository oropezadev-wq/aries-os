# Contrato: ISTTProvider

## Responsabilidad
Define cómo transcribir audio a texto sin acoplar el resto del sistema a un
motor de reconocimiento de voz (STT, *speech-to-text*) específico — mismo
patrón que `ILLMProvider` ya establece para proveedores de LLM
intercambiables (ver `docs/contracts/ILLMProvider.md`, que este contrato
replica a propósito en estructura y espíritu).

## Métodos Requeridos

### async transcribe(audio, language=None, **kwargs) → STTResult
Transcribe audio a texto.

**Parámetros:**
- `audio` (bytes): **WAV completo (con header RIFF/fmt/data), mono,
  16kHz, PCM 16-bit** — formato de intercambio confirmado en
  `docs/specs/Voice.spec.md` (decisión 4). **No es PCM crudo sin
  encabezado** — verificado empíricamente: `faster-whisper` rechaza PCM
  crudo pasado como `bytes`/`BinaryIO` con `InvalidDataError`, necesita un
  contenedor real. El contrato recibe `bytes`, no un `Path`: no le importa
  si el audio vino de un archivo o de un stream de micrófono, y no fuerza
  a quien lo use a tocar disco solo para transcribir.
- `language` (str, opcional): código de idioma ISO 639-1 (ej. `"es"`).
  `None` = autodetección, si el proveedor la soporta.

**VAD interno (automático, no configurable por el llamador):** la
implementación default usa el parámetro nativo `vad_filter=True` de
`faster-whisper` en cada `transcribe()` — filtra/recorta silencio dentro
del audio ya recibido usando un modelo Silero VAD que la propia librería
trae embebido en ONNX (sin dependencia de `torch`/`silero-vad` como
paquete aparte), mejorando la calidad de la transcripción. Esto es
distinto del corte de turno en vivo durante la captura de micrófono (ver
`docs/specs/Voice.spec.md`, decisión 6) — acá se trata el audio que ya
llegó completo a `transcribe()`.

**Retorna:** `STTResult` con:
- `text`: texto transcripto
- `language`: idioma detectado o usado
- `confidence`: `float | None` (0.0–1.0), si el proveedor lo expone (no
  todos los motores STT dan un score de confianza por transcripción
  completa; `None` cuando no está disponible, nunca un valor inventado)

**Excepciones:**
- `VoiceError` (ya definida en `src/aries/exceptions/__init__.py`, sin usar
  todavía — este contrato es su primer consumidor real): error del
  proveedor (audio inválido/corrupto, modelo no cargado, formato no
  soportado)
- `TimeoutError`: se agotó el tiempo de transcripción

### async is_available() → bool
Verifica de forma asíncrona que el proveedor puede operar (modelo cargado
en memoria, recursos de cómputo disponibles). Mismo criterio que
`ILLMProvider.is_available()`.

### get_model_name() → str
Retorna el nombre/tamaño del modelo cargado (ej. `"faster-whisper-small"`).

## Implementaciones Conocidas
- **`FasterWhisperProvider`** (local, default, gratis, offline) — primera
  implementación concreta del contrato, en `src/aries/voice/faster_whisper_provider.py`.
  `faster-whisper>=0.10` declarado en `pyproject.toml` (extra `voice`).
- (futuras, no implementadas, ninguna offline-first): `WhisperAPIProvider`
  (OpenAI, cloud), `GoogleSTTProvider` (cloud) — el contrato no asume que
  el proveedor sea local, aunque el default sí lo sea.

## Casos de Uso

**Transcribir localmente con Faster-Whisper (default):**
```python
stt = FasterWhisperProvider(model_size="small")
result = await stt.transcribe(audio_bytes, language="es")
print(result.text)
```

## Restricciones
- No asumir un modelo/idioma específico en el Planner ni en el Kernel — el
  Planner sigue recibiendo texto plano (`user_input: str`) sin saber si
  vino de STT o de teclado (ver `docs/specs/Planner.spec.md`, sección 1,
  ya decidido y ya implementado así).
- El proveedor default debe funcionar completamente offline — coherente con
  el objetivo "offline-first" de `docs/VISION.md`.
- Soportar cambio de proveedor en runtime (mismo criterio que
  `ILLMProvider`).
