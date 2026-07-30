# Contrato: ITTSProvider

## Responsabilidad
Define cómo convertir texto a audio sin acoplar el resto del sistema a un
motor de síntesis de voz (TTS, *text-to-speech*) específico. **Diseñado
explícitamente para poder reemplazar el proveedor local/gratuito por uno de
pago/nube más adelante (ej. ElevenLabs) sin romper a ningún consumidor** —
exactamente el mismo intercambio que `ILLMProvider` ya permite hoy entre
Ollama (local, gratis) y OpenAI/Claude/Gemini (cloud, pago); ver
`docs/contracts/ILLMProvider.md`, que este contrato replica a propósito.

## Métodos Requeridos

### async synthesize(text, voice=None, **kwargs) → TTSResult
Sintetiza texto a audio.

**Parámetros:**
- `text` (str): texto a sintetizar — en el flujo de Voice, es el
  `response_text` que ya genera `brain/` hoy (ver
  `docs/specs/Planner.spec.md`, sección 4; `brain/` no cambia en nada para
  soportar esto, ya devuelve exactamente este string).
- `voice` (str, opcional): nombre/id de la voz a usar. `None` = voz default
  configurada del proveedor. **El espacio de nombres de voces no está
  unificado entre proveedores** (un id de voz de Piper no es válido para
  ElevenLabs) — es responsabilidad de quien configura el proveedor elegir
  un `voice` correcto para ese proveedor específico; el contrato no lo
  valida ni lo traduce.
- `**kwargs`: parámetros específicos del proveedor. `PiperProvider` los
  reenvía a `piper.config.SynthesisConfig` (`noise_scale`, `noise_w_scale`,
  `length_scale`, etc.). **Nota no obvia, verificada empíricamente:** Piper
  es estocástico por default (`noise_scale`/`noise_w_scale` internos no
  nulos) — dos llamadas con el mismo texto **no** producen el mismo audio.
  Pasar `noise_scale=0.0, noise_w_scale=0.0` da síntesis determinística
  (usado en tests que necesitan reproducibilidad exacta, ver
  `tests/unit/test_voice_pipeline.py`).

**Retorna:** `TTSResult` con:
- `audio`: **WAV completo (con header RIFF/fmt/data), PCM 16-bit** — mismo
  formato de contenedor que `ISTTProvider` recibe (`docs/specs/Voice.spec.md`,
  decisión 4), aunque acá el `sample_rate` puede no ser 16kHz (ver abajo)
- `sample_rate`: `int` en Hz — necesario porque no todos los proveedores
  (ni siquiera todas las voces de Piper) sintetizan al mismo sample rate.
  **Verificado empíricamente, no asumido:** la voz default elegida
  (`es_ES-carlfm-x_low`) sintetiza a **16kHz**, pero otras voces de Piper
  usan `22050Hz` u otros valores — quien reproduce el audio debe leer
  siempre este campo, nunca asumir un valor fijo.
- `voice`: nombre de la voz efectivamente usada

**Excepciones:**
- `VoiceError` (compartida con `ISTTProvider`, ver ese contrato): texto
  vacío, voz inexistente, error del proveedor
- `TimeoutError`: se agotó el tiempo de síntesis — más relevante para
  proveedores de nube, con latencia de red real, que para Piper local

### async is_available() → bool
Mismo criterio que `ILLMProvider.is_available()`: verifica conectividad (si
aplica) y que el modelo/voz estén listos para sintetizar.

### get_voice_name() → str
Retorna el nombre de la voz default configurada para este proveedor.

## Implementaciones Conocidas
- **`PiperProvider`** (local, default, gratis, offline) — primera
  implementación concreta del contrato, en `src/aries/voice/piper_provider.py`.
  `piper-tts>=1.2` declarado en `pyproject.toml` (extra `voice`). Voz
  default recomendada: `es_ES-carlfm-x_low` (la más liviana de las voces
  en español disponibles) — requiere descargar el modelo (`.onnx` +
  `.onnx.json`) por separado, no viene bundleado con el paquete pip (ver
  `python -m piper.download_voices`).
- (futura, cloud, de pago, no implementada): **`ElevenLabsProvider`** — el
  contrato ya está diseñado para que sumar esto sea un cambio de
  configuración de qué proveedor se instancia, no un cambio de código en
  el pipeline de Voice ni en el Planner/Brain.

## Casos de Uso

**Sintetizar localmente con Piper (default):**
```python
tts = PiperProvider(voice="es_ES-mls_10246-low")
result = await tts.synthesize("Listo, se creó el archivo.")
play_audio(result.audio, result.sample_rate)
```

**Cambiar a un proveedor de pago sin tocar el pipeline (futuro, ilustrativo):**
```python
tts = ElevenLabsProvider(api_key="...", voice="Rachel")
result = await tts.synthesize("Listo, se creó el archivo.")  # misma llamada
play_audio(result.audio, result.sample_rate)
```

## Restricciones
- No asumir proveedor local en el pipeline de voz — debe poder cambiarse a
  un proveedor de pago vía configuración, igual que `llm_provider` hoy.
- Manejar timeouts gracefully, en especial para proveedores cloud.
- El proveedor default debe funcionar completamente offline — coherente con
  "offline-first" de `docs/VISION.md`; los proveedores de pago son una
  opción explícita, no el camino por defecto.
