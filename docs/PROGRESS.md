# Aries OS — Progreso

> Fuente de verdad del estado del proyecto. Se actualiza al TERMINAR cada tarea, no al empezarla.
> Antes de cualquier tarea nueva, leer este archivo primero.

## Estado actual (fecha de hoy)
| Fase | Estado |
| --- | --- |
| v0.1 Blueprint | completa |
| v0.2 Foundation | completa |
| v0.3 Kernel | parcial |
| v0.4 Planner | no iniciada |
| v0.5 Plugins | parcial |
| v0.6 Memory | parcial |
| v0.7 Voice | no iniciada |
| v1.0 MVP | no iniciada |

## Qué existe implementado (código real, no contratos)
- `src/aries/core/kernel.py`: kernel básico con initialize/run/shutdown y estado local.
- `src/aries/config/settings.py`: configuración de aplicación con Pydantic Settings y .env loading.
- `src/aries/logging/__init__.py`: inicializa structlog con renderer y logger.
- `src/aries/api.py`: FastAPI app mínima con endpoint `/health`.
- `src/aries/exceptions.py`: excepciones personalizadas definidas.
- `src/aries/types.py`: alias de tipos comunes.
- `tests/unit/test_kernel.py`: tests de inicialización y apagado del kernel.
- `tests/unit/test_config.py`: tests de carga de configuración y overrides de env.

## Qué NO existe todavía (pendiente real)
- No hay ninguna clase concreta que implemente `IMemory`.
- No hay ninguna clase concreta que implemente `ILLMProvider`.
- No hay ninguna clase concreta que implemente `IAgent`.
- No hay ninguna clase concreta que implemente `IPlugin`.
- No hay ninguna clase concreta que implemente `ITool`.
- `src/aries/core/kernel.py` no integra memoria, agentes, plugins ni planner reales, solo usa sleeps como stub.
- No existen providers LLM reales ni persistencia de memoria.
- No hay planner ni ejecución de tools definidos en el código.
- No hay implementación de subsistema de voz.

## Próximo paso recomendado
Implementar una clase concreta mínima que extienda `IMemory` y permita almacenar/recuperar items en memoria en memoria local.

## Reglas para mantener este archivo
- Actualizar la tabla y "Qué existe implementado" al cerrar cada tarea, una línea por módulo
- Nunca borrar fases completadas, solo agregar filas nuevas
- "Próximo paso recomendado" siempre debe tener una sola tarea, nunca varias opciones
