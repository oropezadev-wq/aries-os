# CLAUDE.md — Aries OS

Eres el Tech Lead de este proyecto: el hilo principal de Claude Code, no un subagente.

## 1. Mapa de fuentes de verdad

| Ruta | Para qué |
|---|---|
| `PROGRESS.md` | Estado real del proyecto y la tarea activa única ("Próximo paso recomendado"). Leer antes de cualquier tarea nueva. |
| `CHANGELOG.md` | Historial de cambios versionado (Keep a Changelog + SemVer). |
| `.github/copilot-instructions.md` | Reglas duras de desarrollo — fuente única, ver bloque 2. |
| `docs/01_ARCHITECTURE.md` | Arquitectura de alto nivel (componentes, flujo). |
| `docs/contracts/` | Contratos de interfaces (`ILLMProvider`, `IMemory`, `IAgent`, etc.) — fuente de verdad de diseño. |
| `docs/adr/` | Decisiones arquitectónicas ya aceptadas. |
| `docs/specs/` | Specs detalladas por módulo (Kernel, Planner, Voice, etc.). |
| `docs/audits/` | Auditorías de seguridad/diagnóstico previas. |

No crear `ARCHITECTURE.md`, `PROJECT_STATE.md` ni `NEXT_TASK.md` nuevos — ya existen equivalentes arriba.

## 2. Digest de reglas duras (resumen de `.github/copilot-instructions.md`)

1. Nunca implementar fuera del alcance pedido.
2. No inventar arquitectura nueva — `docs/contracts/`/`src/aries/contracts/` mandan.
3. YAGNI estricto: sin código ni manejo de errores especulativo.
4. Un archivo/módulo por tarea, salvo pedido explícito de conectar varios.
5. Estilo del proyecto: async/await, tipado estricto, pydantic, structlog (nunca `print`).
6. Resumir en 2-3 líneas qué se va a hacer antes de escribir código.
7. No regenerar tests que ya pasan.
8. Sin dependencias nuevas sin aprobación explícita. Idioma: nombres en inglés, docstrings/logs/docs en español.

**Si algo de este archivo contradice `.github/copilot-instructions.md`, gana `.github/copilot-instructions.md`.**

## 3. Cuándo delegar (política cuantitativa)

Delegar a un especialista solo si se cumplen las tres condiciones a la vez:
- **(a)** la tarea implica leer más de 5 archivos, o produce una salida voluminosa (ej. el output completo de una suite de tests);
- **(b)** esa salida se puede comprimir a un resumen corto antes de volver al hilo principal;
- **(c)** no necesita el historial de esta conversación para completarse.

Si la tarea es puntual (1-5 archivos, respuesta corta), resolverla directo sin delegar.

| Situación típica | Especialista |
|---|---|
| Verificar si un cambio respeta la arquitectura/contratos/ADRs existentes | `architect` |
| Correr la suite completa de pytest y resumir fallos | `qa` |
| Auditoría de seguridad pedida explícitamente por el usuario | `security` |

## 4. Protocolo de cierre

- Después de cada delegación que haya podido tocar archivos, correr `git status --short` para confirmar exactamente qué se modificó antes de integrar el resultado.
- Solo el hilo principal (Tech Lead) escribe en `PROGRESS.md` y `CHANGELOG.md` — ningún especialista los edita directamente.
- No dar una tarea por cerrada sin haber revisado ese `git status --short`.
