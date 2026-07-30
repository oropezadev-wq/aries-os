# Contrato: IWakeWordProvider

## Responsabilidad
Define cómo detectar una palabra/frase de activación ("wake word") sobre
un stream continuo de audio, sin acoplar el resto del sistema a un motor
específico — mismo patrón que `ILLMProvider` (ver
`docs/contracts/ILLMProvider.md`, que este contrato replica a propósito).

## Métodos Requeridos

### process_frame(frame) → list[WakeWordDetection]
Procesa un único frame de audio y devuelve las wake words detectadas en
ese frame (lista vacía si ninguna).

**Nota de diseño — único método síncrono entre todos los contratos de
proveedores del proyecto, a propósito:** se llama en un loop de tiempo
real, frame a frame (con el proveedor default, cada 80ms — ver
`frame_size()`), en lockstep con una lectura bloqueante del micrófono.
Envolverlo en `async def` no aportaría nada (no hay I/O real que solapar,
es una inferencia ONNX local de pocos milisegundos) y solo obligaría al
loop de captura a puentear hilo-`asyncio` sin beneficio real.

**Parámetros:**
- `frame` (`numpy.ndarray`, `int16`, mono): un frame de audio de exactamente
  `frame_size()` samples, al sample rate que el proveedor espera (16kHz
  para el proveedor default).

**Retorna:** lista de `WakeWordDetection`, una por cada wake word
detectada en este frame por encima de su umbral interno:
- `name`: nombre de la wake word detectada
- `score`: `float | None` — score de confianza (0.0–1.0), si el proveedor
  lo expone

El proveedor decide internamente qué umbral/lógica de debounce aplicar
antes de reportar una detección — el contrato no impone un umbral
universal porque distintos motores exponen esto de formas muy distintas
(openWakeWord da un score continuo por frame; otros motores, como
Porcupine, dan un índice de detección binario ya filtrado internamente).

### frame_size() → int
Cantidad exacta de samples que `process_frame()` espera recibir por
llamada. El proveedor default (`OpenWakeWordProvider`) espera 1280
samples (80ms a 16kHz).

### async is_available() → bool
Verifica de forma asíncrona que el proveedor puede operar (modelo(s)
cargado(s) en memoria). Mismo criterio que `ILLMProvider.is_available()`
— este método sí es async, ya que no se llama en el loop de tiempo real
por frame, solo al arrancar el pipeline.

### get_wake_words() → list[str]
Nombres de las wake words que este proveedor puede detectar (los modelos
cargados).

## Implementaciones Conocidas
- **`OpenWakeWordProvider`** (local, default, gratis, offline) — primera
  implementación concreta. Usa `openwakeword>=0.6` (extra `voice` de
  `pyproject.toml`). Modelo default: `hey_jarvis` (pre-entrenado; no
  existe todavía un modelo "Aries" propio — ver `docs/specs/Voice.spec.md`,
  decisión 1, sección "Modelo default").
- (futura, de pago, no implementada): **`PorcupineProvider`** (Picovoice)
  — el contrato ya está diseñado para aceptarlo sin romper al pipeline,
  mismo espíritu que `ITTSProvider`/`ElevenLabsProvider`.

## Casos de Uso

**Detectar sobre un stream continuo de audio (loop simplificado):**
```python
wake_word = OpenWakeWordProvider(wakeword_models=["hey_jarvis"], threshold=0.5)
frame_size = wake_word.frame_size()

while True:
    frame = microphone.read(frame_size)  # numpy.ndarray int16, bloqueante
    detections = wake_word.process_frame(frame)
    if detections:
        print(f"Detectada: {detections[0].name} (score={detections[0].score})")
        break
```

## Restricciones
- El proveedor default debe funcionar completamente offline — coherente
  con "offline-first" de `docs/VISION.md`.
- `process_frame()` nunca debe bloquear más de lo que tarda una inferencia
  local — no debe hacer I/O de red ni operaciones de larga duración,
  precisamente porque se llama en el loop de tiempo real de captura.
