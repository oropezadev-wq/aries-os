# Copilot Instructions — Aries OS

## Contexto del proyecto
Aries OS es un paquete Python (`src/aries/`) en fase de **contratos y esqueleto arquitectónico**.
NO existen aún: providers reales (LLM/STT/TTS), memoria persistente, agentes o tools ejecutables.
Lo que sí existe: `Kernel` async, `settings.py` (pydantic-settings), logging (`structlog`), excepciones,
tipos comunes, y los contratos `ILLMProvider`, `IMemory`, `IAgent`, `IPlugin`, `ITool` con su documentación
en `docs/contracts/`.

Stack: Python 3.13, FastAPI, PostgreSQL, SQLAlchemy, Alembic, Redis, Ollama, Faster-Whisper, Piper, PySide6, Docker.

## Reglas duras (no negociables)

1. **Nunca implementes fuera del alcance pedido.** Si te pido "implementa `MemoryItem.to_dict()`",
   no toques `kernel.py`, no "mejores" el logging, no agregues features no pedidas.
2. **No inventes arquitectura nueva.** Los contratos en `src/aries/contracts/` y su documentación en
   `docs/contracts/` son la fuente de verdad. Si una implementación no calza con el contrato existente,
   pregúntame antes de cambiar el contrato.
3. **No generes código "por si acaso".** Nada de manejo de errores especulativo, configuración no usada,
   abstracciones para casos hipotéticos futuros. YAGNI estricto.
4. **Un archivo o módulo por tarea.** No toques múltiples módulos en una sola respuesta salvo que la
   tarea lo requiera explícitamente (ej. "conecta X con Y").
5. **Respeta el estilo ya presente:** async/await consistente con `kernel.py`, tipado estricto (el proyecto
   usa type hints en todo), pydantic para validación, structlog para logging (nunca `print`).
6. **Antes de escribir código, resume en 2-3 líneas qué vas a hacer y en qué archivo(s).** Si no coincide
   con lo que pedí, corrijo antes de que generes nada.
7. **No regeneres tests que ya pasan.** Solo agrega tests para código nuevo o modificado.
8. **Sin dependencias nuevas sin aprobación explícita.** Si crees que se necesita una librería nueva,
   dilo y espera confirmación — no la agregues a `pyproject.toml` por tu cuenta.

## Convención de idioma

- Nombres de clases, funciones, variables y módulos: en inglés.
- Docstrings, comentarios, mensajes de log y mensajes de excepción/error: en español.
- Nombres de tests (`test_*`): en inglés.
- Documentación y archivos `.md`: en español.

## Formato esperado de cada tarea que te doy
Cuando te pida algo, asumo que trabajas SOLO sobre:
- El archivo o función que te indique explícitamente
- Los contratos ya definidos como interfaz (no los reescribas)
- Los tests correspondientes a ese archivo, si aplica

Si una tarea mía es ambigua, pregunta antes de generar código — no rellenes los huecos por tu cuenta.