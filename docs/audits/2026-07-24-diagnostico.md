# Diagnóstico — Módulos "parcial" (events, plugins, memory)

Fecha: 2026-07-24
Alcance: análisis de solo lectura. No se modificó ningún archivo de `src/` ni `tests/`.

Nota metodológica: `docs/01_ARCHITECTURE.md` es un esqueleto de una página (lista de componentes + una línea de flujo enfocada en voz: `Usuario -> Wake Word -> STT -> Planner -> Brain -> Skill -> Agent -> Resultado`). No menciona explícitamente el Event Bus, Memory ni Plugins en el flujo, y `docs/specs/Kernel.spec.md`, `docs/specs/Planner.spec.md`, `docs/specs/Memory.spec.md` y `docs/specs/PluginAPI.spec.md` existen pero están **vacíos**. Esto significa que la única fuente de verdad detallada para estos tres módulos son los contratos en `docs/contracts/*.md`, no las specs ni la arquitectura. Cualquier comparación "diseño vs. contrato" hecha abajo se apoya en esos contratos, no en documentos de diseño más finos que no existen todavía.

---

## 1. `src/aries/events/`

### Qué hace cada archivo y cómo encajan

- **`event.py`** — `BaseEvent`: dataclass frozen con `metadata`, `timestamp` y `event_type` (derivado de `__class__.__name__` en `__post_init__`). Expone `event_id` como propiedad calculada (`módulo.qualname`), pensada para evitar colisiones de nombre entre eventos definidos en distintos módulos/plugins.
- **`event_bus.py`** — `AsyncEventBus(IEventBus)`: única implementación del contrato. Mantiene `_handlers: dict[str, set[Handler]]` protegido por un `asyncio.Lock`. `publish` reúne handlers registrados tanto bajo el `event_id` completo como bajo el `event_type` corto, y delega la ejecución en `Dispatcher`.
- **`dispatcher.py`** — `Dispatcher`: ejecuta todos los handlers de un evento con `asyncio.gather`, aislando errores por handler (uno que falla no tumba a los demás) y soportando handlers síncronos vía `run_in_executor`. Maneja cancelación dejando terminar el hilo síncrono en curso antes de propagar `CancelledError`.
- **`publisher.py` / `subscriber.py`** — `EventPublisher` y `EventSubscriber`: envoltorios de una sola línea que delegan directamente en `IEventBus.publish` / `subscribe` / `unsubscribe`. No agregan comportamiento propio.
- **`core/events.py`** (fuera de `events/`, pero acoplado a él) — define los únicos dos eventos concretos que existen hoy: `KernelInitializedEvent` y `KernelShutdownEvent`.

Encaje: `event.py` es la base tipada, `event_bus.py` + `dispatcher.py` son el motor real, y `publisher.py`/`subscriber.py` son una fachada opcional sobre ese motor. `core/kernel.py` **no usa** `EventPublisher`/`EventSubscriber`; llama a `self.event_bus.publish(...)` directamente. Es decir, dos capas de acceso al bus conviven, pero solo una está en uso real.

### ¿Calza con el contrato y con la arquitectura?

Calza bien con `docs/contracts/IEventBus.md` en los tres métodos exigidos (`publish`, `subscribe`, `unsubscribe`), en la normalización estable de `event_type` (str o clase) y en no lanzar excepciones no controladas cuando no hay handlers. Los tests unitarios (`tests/unit/test_event_bus.py`) y de integración cubren estos casos, incluida concurrencia y cancelación.

Donde **no** calza es con lo que asume `docs/contracts/IPlugin.md`: ese contrato enumera un conjunto fijo de eventos "disponibles" para hooks (`KERNEL_STARTING`, `KERNEL_READY`, `KERNEL_SHUTDOWN`, `INTENT_DETECTED`, `PLAN_CREATED`, `PLAN_EXECUTED`, `ACTION_STARTED/COMPLETED/FAILED`, `MEMORY_STORED/DELETED/SEARCHED`, `ERROR_OCCURRED`, `PLUGIN_LOADED/UNLOADED`) tratados como si fueran nombres planos tipo enum. La implementación real solo define 2 de esos 14 (`KernelInitializedEvent`, `KernelShutdownEvent`, que ni siquiera tienen los mismos nombres que `KERNEL_STARTING`/`KERNEL_READY` del contrato). El resto de eventos que el flujo Kernel → Planner → Plugins → Memory necesitaría no existen como clases todavía.

### Problemas concretos

- **Emparejamiento exacto, no jerárquico.** `AsyncEventBus` indexa handlers por el `event_type`/`event_id` exacto de la instancia publicada. Suscribirse a la clase `BaseEvent` **no** recibe subclases (confirmado por `test_subscribe_to_base_event_does_not_receive_other_event_types`). Para un bus pensado para que plugins reaccionen a eventos de dominio (`ACTION_FAILED`, etc.), esto obliga a que cada evento futuro sea una clase concreta y que los handlers se suscriban exactamente a esa clase — no hay forma de escuchar "cualquier evento de tipo Acción". No es necesariamente incorrecto, pero no está documentado como decisión de diseño en ningún contrato, y es fácil de asumir lo contrario al escribir un plugin.
- **Capa muerta.** `EventPublisher`/`EventSubscriber` no se usan en ningún camino de ejecución real (`core/kernel.py` llama al bus directamente). Solo aparecen en el test de integración. Es una abstracción a medio adoptar: o se usa consistentemente como fachada (por ejemplo, para que plugins nunca toquen `IEventBus` directamente) o se elimina.
- **Ubicación de eventos concretos fuera del paquete `events/`.** `KernelInitializedEvent`/`KernelShutdownEvent` viven en `core/events.py`, no en `events/`. Esto separa "el mecanismo" (`events/`) de "el vocabulario de eventos del sistema" (disperso, hoy solo en `core/`). Cuando Planner y Plugins necesiten publicar sus propios eventos (`PLAN_CREATED`, `PLUGIN_LOADED`, etc.), no hay un lugar designado para definirlos — cada módulo probablemente creará su propio `events.py` local, lo cual funciona pero no está decidido como convención en ningún doc.
- **Import diferido dentro de métodos.** `core/kernel.py` hace `from .events import KernelInitializedEvent` dentro de `initialize()` y `from .events import KernelShutdownEvent` dentro de `shutdown()`, en vez de en el top-level del archivo (como el resto de imports). No hay ciclo de imports visible que lo justifique; es inconsistente con el estilo del resto del archivo y dificulta ver de un vistazo qué eventos publica el kernel.
- **Duplicado estructural no relacionado con `events/` pero que lo toca:** existe `src/aries/kernel/kernel.py` y `src/aries/kernel/__init__.py`, ambos **vacíos**, en paralelo a `src/aries/core/kernel.py` (que sí tiene la implementación real y es la que importa `core/events.py`). Es un paquete fantasma que puede confundir a quien busque el kernel real o a quien intente importar eventos del kernel.

### Recomendación

**Completar, no rehacer.** El motor (`event_bus.py` + `dispatcher.py`) es sólido: aislamiento de errores por handler, soporte sync/async, normalización de tipos y buena cobertura de tests, incluyendo casos de concurrencia y cancelación que suelen ser los que fallan en implementaciones apresuradas de un bus async. Rehacerlo no aportaría valor. Lo que falta no es reescritura sino:
1. Decidir y documentar dónde viven los eventos de dominio (¿`events/` centralizado con submódulos por owner, o un archivo `events.py` por paquete como ya se hizo en `core/`?).
2. Definir los eventos que el contrato de `IPlugin` da por hechos (`INTENT_DETECTED`, `PLAN_CREATED`, `ACTION_*`, `MEMORY_*`, `PLUGIN_*`) antes de que Planner/Plugins/Memory los necesiten, para no descubrir el hueco a mitad de esas implementaciones.
3. Resolver la duplicidad de fachada: usar `EventPublisher`/`EventSubscriber` en el kernel real o eliminarlas.

---

## 2. `src/aries/plugins/`

### Qué hace cada archivo y cómo encajan

`installer.py`, `loader.py`, `manifest.py`, `registry.py` y `__init__.py` están **vacíos** (0 bytes cada uno). No hay ninguna clase, función ni siquiera un docstring. La única pieza real relacionada con plugins en todo `src/` es el contrato `contracts/plugin.py` (`IPlugin`, `PluginMetadata`, `PluginHooks`). Una búsqueda de "plugin" en todo `src/` solo encuentra ese contrato y una mención en el docstring de `events/subscriber.py` ("Para un Plugin Manager, el plugin debe desuscribir..."). `bootstrap/discovery.py`, que por nombre sería el candidato natural para descubrir plugins en disco, también está vacío.

Es decir: no hay "cómo encajan entre sí" que describir, porque no encajan — no hay implementación que relacionar.

### ¿Calza con el contrato y con la arquitectura?

No aplica una comparación de diseño porque no hay diseño implementado. El contrato `docs/contracts/IPlugin.md` es razonablemente completo (metadatos, ciclo de vida `initialize`/`shutdown`, hooks, capacidades, compatibilidad de versión), y `docs/specs/PluginAPI.spec.md` existe pero está vacío, así que ni siquiera hay una spec más detallada de cómo `loader.py`/`registry.py`/`installer.py`/`manifest.py` deberían dividirse el trabajo (p. ej., ¿el manifest es un archivo TOML/JSON en disco? ¿el loader usa `importlib`? ¿el registry es un diccionario en memoria o persiste?). Nada de eso está decidido.

### Problemas concretos

- **Etiqueta engañosa en PROGRESS.md.** Marcar este módulo como "parcial" sobrestima el avance real: es 0% código, solo nombres de archivo reservados. Esto puede llevar a subestimar el esfuerzo restante en la planificación.
- **Sin punto de enganche con el Event Bus.** El contrato dice que los plugins son "Hookeable: Plugin se conecta solo por eventos", pero como se documentó en la sección de `events/`, la mayoría de los eventos que un plugin necesitaría escuchar no existen todavía. Aun si se escribiera `loader.py` hoy, no tendría a qué suscribir los hooks de un plugin real más allá de `KernelInitializedEvent`/`KernelShutdownEvent`.
- **Sin manifest ni discovery.** No hay ninguna definición de formato de manifiesto (ni siquiera un ejemplo), y `bootstrap/discovery.py` —el lugar lógico para escanear un directorio de plugins— está vacío. No hay forma de decidir si "loader" carga desde un path fijo, un entry_point de `pip`, o algo más.
- **Sin registry ni versión de kernel para `is_compatible`.** El contrato pide `is_compatible(kernel_version)`, pero no existe ningún concepto de "versión del kernel" en `core/kernel.py` ni en `Settings` — no hay un valor contra el cual comparar.
- **Huecos frente al flujo Kernel → Event Bus → Planner → Plugins → Memory:** este es, de los tres módulos, el que tiene el hueco más grande y más simple de describir: el hueco es el 100% del módulo. No hay forma de que un plugin participe del flujo hoy, ni para bien (extender capacidades) ni para mal (no hay riesgo de acoplamiento porque no hay código que acoplar).

### Recomendación

**Rehacer, en el sentido de "empezar desde cero con diseño explícito", no "reescribir código existente".** No hay código que rehacer; lo que hace falta es la secuencia inversa a la habitual: antes de escribir `manifest.py`/`loader.py`/`registry.py`/`installer.py`, llenar `docs/specs/PluginAPI.spec.md` con las decisiones que el contrato deja abiertas (formato de manifiesto, mecanismo de carga, ciclo de vida de aislamiento, cómo se resuelven `requires`). Escribir el código antes de esas decisiones, solo por tener algo en los archivos vacíos, probablemente produzca una implementación que haya que descartar en cuanto Planner o el catálogo de eventos de dominio queden definidos (dependencia directa del hueco #2 de `events/`).

---

## 3. `src/aries/memory/`

### Qué hace cada archivo y cómo encajan

- **`contracts/memory.py`** — define `MemoryItem` (dataclass con `id`, `type`, `content`, `metadata`, `created_at`, `updated_at`, `importance`) e `IMemory` (ABC con `store`, `retrieve`, `search`, `delete`, `clear_expired`, `get_by_type`).
- **`memory/in_memory.py`** — `InMemoryStore(IMemory)`: única implementación concreta. Guarda todo en un `dict[str, MemoryItem]` protegido por `asyncio.Lock`. Implementa los 6 métodos del contrato con validación de tipos/rangos en cada uno (p. ej. `importance` entre 1 y 10).
- **`memory/__init__.py`** — vacío (no re-exporta `InMemoryStore`; quien lo use debe importar desde `aries.memory.in_memory` directamente, como hace `__main__.py`).

De los tres módulos, este es el único con una implementación funcionalmente completa de su contrato y con cobertura de tests real (`tests/unit/test_in_memory_store.py`: store/retrieve, retrieve faltante, búsqueda con filtro de tipo, sin resultados, delete existente/faltante, `get_by_type`, `clear_expired`, validación de `importance`, y una prueba de concurrencia con 20 escrituras simultáneas).

### ¿Calza con el contrato y con la arquitectura?

Calza bien a nivel de firma de métodos: los 6 métodos de `docs/contracts/IMemory.md` están implementados con la misma forma. Donde se abre una brecha es en dos puntos que el contrato sí especifica pero `MemoryItem`/`InMemoryStore` no reflejan:

1. El contrato define un esquema SQL esperado que incluye `expires_at TIMESTAMP`, y describe `clear_expired()` como responsable de "limpiar información vieja/vencida". `MemoryItem` **no tiene** campo `expires_at` (ni ningún campo de expiración). Como consecuencia, `clear_expired()` en `InMemoryStore` es un no-op permanente que siempre retorna 0 — no porque falte "conectar" la lógica, sino porque no hay ningún dato en el modelo sobre el cual esa lógica podría operar nunca. El propio código lo señala con un comentario, así que es un hueco conocido, no oculto.
2. El contrato enumera 7 tipos de memoria como taxonomía cerrada (`conversation`, `preference`, `profile`, `document`, `learning`, `automation`, `context`), pero `memory_type` se valida solo como `str` no vacío — cualquier string pasa. No hay un `Enum`/`Literal` que lo restrinja, así que un caller (Planner, un Plugin) puede introducir un tipo arbitrario sin que nada lo marque como inconsistente con la taxonomía documentada.

`search()` hace `query in item.content` (substring, sensible a mayúsculas/minúsculas, sin tokenización). El propio contrato dice "Nota: Implementar búsqueda fulltext si es posible" — para una implementación de desarrollo en memoria esto es una limitación aceptada, no un bug, pero vale la pena que quede explícito que no es equivalente a un `FULLTEXT INDEX` real cuando llegue una implementación de producción (Postgres/SQLite mencionadas como "Implementaciones Esperadas" en el contrato, y ninguna existe aún — consistente con lo que dice `PROGRESS.md`: "No hay persistencia de memoria").

### Problemas concretos

- **Memory está inyectada en el Kernel pero no se usa.** `core/kernel.py` recibe `memory: IMemory` en el constructor y la guarda en `self.memory`, pero ningún método (`initialize`, `run`, `shutdown`) llama a `store`, `retrieve`, `search`, `delete`, `get_by_type` ni `clear_expired`. Es una dependencia inyectada pero muerta en el flujo actual. Esto es exactamente el hueco frente al flujo Kernel → Event Bus → Planner → Plugins → Memory: hoy Memory no participa de ese flujo en absoluto, más allá de existir como parámetro.
- **Sin eventos `MEMORY_STORED`/`MEMORY_DELETED`/`MEMORY_SEARCHED`.** El contrato de `IPlugin` espera que estas operaciones disparen eventos hookeables por plugins. `InMemoryStore` no publica nada al Event Bus (de hecho, ni siquiera recibe una referencia al bus en su constructor). Cualquier plugin que quisiera reaccionar a "se guardó un recuerdo" no tiene forma de enterarse hoy.
- **`clear_expired` es un no-op estructural**, no solo funcional — no hay campo `expires_at` en el modelo, así que ni siquiera hay un "TODO de una línea" posible sin antes tocar `MemoryItem`.
- **Sin restricción de la taxonomía de `memory_type`**, lo que facilita que Planner/Plugins introduzcan valores inconsistentes con lo documentado (ver arriba).
- **`memory/__init__.py` vacío** — asimetría menor con `events/__init__.py`, que sí re-exporta sus símbolos públicos (`BaseEvent`, `AsyncEventBus`, etc.). No es grave, pero rompe la convención del resto del proyecto y obliga a importar desde el submódulo interno (`aries.memory.in_memory`) en vez de `aries.memory`.

### Recomendación

**Completar, no rehacer.** `InMemoryStore` es una base correcta y bien probada para la interfaz actual; no tiene bugs de concurrencia ni de contrato que ameriten descartarla. Falta:
1. Decidir si `expires_at` se agrega a `MemoryItem` ahora o se documenta explícitamente como "fuera de alcance hasta v0.6 avance más" (hoy es ambiguo: el contrato lo pide, el código lo omite en silencio salvo un comentario).
2. Conectar `InMemoryStore` (o quien la envuelva) al Event Bus para publicar `MEMORY_STORED`/`MEMORY_DELETED`/`MEMORY_SEARCHED`, lo cual depende de que esos eventos existan primero (mismo hueco que se señaló en `events/`).
3. Cablear el uso real de `self.memory` dentro de `core/kernel.py` (aunque sea mínimo, p. ej. registrar el arranque como un `MemoryItem` de tipo `context`), para que deje de ser una dependencia inyectada sin efecto.

---

## Addendum (2026-07-24, post-diagnóstico) — bug bloqueante encontrado al intentar correr tests

Durante la implementación de la tarea de `memory/` (agregar `expires_at` y cablear `self.memory` en `core/kernel.py`), se intentó correr `pytest` para verificar los cambios y **`import aries` falla por completo**, con o sin los cambios de esta tarea:

```
ImportError: cannot import name 'Handler' from partially initialized module 'aries.contracts.event_bus'
(most likely due to a circular import) (E:\Proyectos\Aries\Aries_OS\src\aries\contracts\event_bus.py)
```

Cadena del ciclo: `aries.core.kernel` → `aries.contracts.event_bus` → (al hacer `from ..events.event import BaseEvent`, Python ejecuta primero `aries/events/__init__.py`) → `aries.events.event_bus` → `from ..contracts.event_bus import Handler, IEventBus, EventType`, pero `contracts.event_bus` todavía está a medio ejecutar (es el módulo que inició la cadena), así que `Handler` aún no existe en él.

Se confirmó que el ciclo es **preexistente y no fue causado por los cambios de esta tarea**: se reproduce con `python -c "import aries"` en un intérprete limpio, y las tres piezas involucradas (`src/aries/contracts/event_bus.py`, `src/aries/contracts/__init__.py`, `src/aries/events/__init__.py`, `src/aries/events/event_bus.py`) ya aparecían modificadas/sin trackear en `git status` antes de empezar cualquier trabajo de hoy — quedaron así de una sesión anterior no comiteada.

**Impacto:** ningún test del proyecto puede ejecutarse hoy (`pytest` falla en la recolección de `conftest.py` para todo el suite, no solo para `memory/`), incluidos los tests nuevos escritos para esta tarea. El diagnóstico original de la sección 1 (`events/`) se basó en lectura estática del código, no en ejecución real de los tests — con el import roto, esa cobertura de tests no se pudo verificar en la práctica hasta ahora.

**Actualización:** el usuario autorizó una excepción puntual al alcance para desbloquear la verificación por test. Se aplicó un fix mínimo, solo de orden de imports (sin tocar lógica de negocio):

- `src/aries/contracts/event_bus.py`: se movió `from ..events.event import BaseEvent` (y el cálculo de `EventType`) a **después** de la definición de `IEventBus`, para que `Handler` e `IEventBus` ya existan en el módulo cuando ese import dispare la carga de `aries/events/__init__.py`.
- `src/aries/events/event_bus.py` y `src/aries/events/subscriber.py`: `EventType` dejó de importarse en tiempo de ejecución desde `contracts.event_bus` (en el momento en que estos módulos se cargan, `EventType` todavía no existe ahí — sigue sin estar definido hasta que termina de ejecutarse el import diferido de arriba). Se movió a un import bajo `TYPE_CHECKING`, seguro porque ambos archivos ya usan `from __future__ import annotations` (las anotaciones nunca se evalúan en runtime).

Verificado con `python -c "import aries"` (ya no falla) y con el suite completo de `pytest` (ver más abajo). Este fix se limitó estrictamente a orden/alcance de imports; no se tocó ninguna lógica de `AsyncEventBus`, `Dispatcher`, `EventPublisher` ni `EventSubscriber`.

**Segundo hallazgo, destapado por el mismo fix:** con `pytest` corriendo por primera vez, aparecieron como **flaky** (fallan de forma intermitente, no consistente) `tests/unit/test_kernel.py::test_kernel_publishes_initialized_event` y `::test_kernel_publishes_shutdown_event`. Ambos comparan un evento publicado por el kernel contra una instancia nueva del mismo tipo por igualdad de dataclass, pero `BaseEvent.timestamp` (default factory `datetime.now(UTC)`) casi nunca coincide al microsegundo entre dos instancias distintas — la comparación de igualdad estaba rota desde que se agregó `timestamp` a `BaseEvent`, simplemente nunca se había ejecutado el test hasta ahora. No se corrigió: es un problema de `events/`/tests preexistente, fuera del alcance de la tarea de `memory/` de hoy (que explícitamente pidió no tocar `events/` salvo el fix de import ya descrito). Queda anotado en `PROGRESS.md` para una tarea futura.

## Prioridad sugerida

1. **`events/`** — Atacar primero. No tiene bugs que arreglar en el motor, pero es la dependencia compartida de los otros dos: tanto Plugins (que se conecta "solo por eventos") como Memory (que necesita publicar `MEMORY_*`) están bloqueados por la falta de un catálogo de eventos de dominio más allá de `KernelInitializedEvent`/`KernelShutdownEvent`. Definir dónde viven los eventos y crear los que exige `docs/contracts/IPlugin.md` desbloquea a los otros dos módulos sin tocar su código.
2. **`memory/`** — Segundo. Ya tiene una implementación correcta y probada; el trabajo restante es acotado y no depende de decisiones de arquitectura nuevas más allá de lo que resuelva el punto 1 (eventos) y una decisión pequeña sobre `expires_at`. Es la vía más rápida para mostrar avance real y conectar algo tangible al flujo Kernel → Memory.
3. **`plugins/`** — Tercero, a propósito. Es el módulo con más superficie por decidir (formato de manifiesto, mecanismo de carga, versión de compatibilidad) y depende funcionalmente de que `events/` tenga ya el catálogo de eventos de dominio (sin eso, un plugin no tiene a qué engancharse). Empezar aquí antes de resolver 1 arriesga construir `loader.py`/`registry.py` sobre una lista de eventos que todavía va a cambiar.

---

## Propuesta catálogo de eventos (borrador, 2026-07-24 — solo diagnóstico, sin implementar)

Objetivo: dar a `events/` el catálogo de eventos de dominio que `docs/contracts/IPlugin.md` da por hecho, para que `plugins/` tenga a qué engancharse. **Nada de esto se implementó** — es un borrador para discutir antes de tocar código de `events/` o `plugins/`.

### Decisiones de producto ya resueltas (vía AskUserQuestion en esta sesión)

1. **Convención de nombres:** clases `PascalCase` que heredan de `BaseEvent` (como ya existe en `core/events.py`), no strings `SCREAMING_SNAKE_CASE`. `docs/contracts/IPlugin.md` queda con notación desactualizada — corregirla es trabajo pendiente de una tarea futura, no de este borrador.
2. **Alcance:** el catálogo cubre solo lo que `IPlugin.md` necesita hoy (Kernel, Intent, Plan, Action, Memory, Plugin, Error). Deliberadamente **no** incluye eventos de voz (`WAKE_WORD_DETECTED`, `STT_COMPLETED`, etc.) sugeridos por el flujo de `docs/01_ARCHITECTURE.md`, porque Voice sigue "no iniciada" en `PROGRESS.md`.
3. **Agent vs Tool:** se unifican bajo una sola familia `Action*`. Tanto `IAgent.execute()` como `ITool.execute()` publican `ActionStartedEvent`/`ActionCompletedEvent`/`ActionFailedEvent`; el `TOOL_EXECUTED` mencionado (pero no definido con estados) en `docs/contracts/ITool.md` se descarta como evento separado — su paso 9 ("Disparar evento TOOL_EXECUTED") debería corregirse en ese contrato para apuntar a esta familia unificada.

### Catálogo propuesto

| # | Evento (clase propuesta) | Dispara cuando | Quién lo publica | Payload sugerido (más allá de `metadata`/`timestamp`) | Estado hoy |
|---|---|---|---|---|---|
| 1 | `KernelStartingEvent` | Al entrar a `Kernel.initialize()`, antes de validar el LLM provider | `core/kernel.py` | — | **Nuevo**, no existe |
| 2 | `KernelInitializedEvent` | Al terminar `Kernel.initialize()` con éxito | `core/kernel.py` | — | Ya existe (equivale semánticamente a `KERNEL_READY` de `IPlugin.md`; no se renombra para no romper tests) |
| 3 | `KernelShutdownEvent` | Al terminar `Kernel.shutdown()` | `core/kernel.py` | — | Ya existe |
| 4 | `IntentDetectedEvent` | El Planner interpreta la entrada del usuario y determina una intención | Planner (no existe aún) | `intent: str`, `confidence: float \| None`, `raw_input: str` | Bloqueado por Planner ("no iniciada") |
| 5 | `PlanCreatedEvent` | El Planner arma la secuencia de pasos/tools para cumplir la intención | Planner | `plan_id: str`, `steps: list`, `intent: str` | Bloqueado por Planner |
| 6 | `PlanExecutedEvent` | El Planner termina de ejecutar todos los pasos del plan | Planner | `plan_id: str`, `success: bool`, `results: list[ActionResult]` | Bloqueado por Planner |
| 7 | `ActionStartedEvent` | Justo antes de que un `IAgent.execute()` o `ITool.execute()` empiece a correr | Agent/Tool (ninguno implementado aún) | `actor_type: "agent"\|"tool"`, `actor_name: str`, `action: str` | Bloqueado — no hay `IAgent`/`ITool` concretos |
| 8 | `ActionCompletedEvent` | `execute()` termina con éxito (`ActionStatus.SUCCESS` o `ToolResult.success is True`) | Agent/Tool | `actor_type`, `actor_name`, `action`, `result` | Bloqueado |
| 9 | `ActionFailedEvent` | `execute()` termina en error/excepción (`FAILED`/`CANCELLED` o `ToolResult.success is False`) | Agent/Tool | `actor_type`, `actor_name`, `action`, `error: str` | Bloqueado |
| 10 | `MemoryStoredEvent` | `IMemory.store()` guarda un item con éxito | `memory/in_memory.py` (u otra impl.) | `memory_id: str`, `memory_type: str` | Bloqueado — ver nota de implementación abajo |
| 11 | `MemoryDeletedEvent` | `IMemory.delete()` borra un item (retorna `True`) | `memory/in_memory.py` | `memory_id: str` | Bloqueado — ídem |
| 12 | `MemorySearchedEvent` | `IMemory.search()` termina de ejecutarse | `memory/in_memory.py` | `query: str`, `memory_type: str \| None`, `result_count: int` | Bloqueado — ídem |
| 13 | `ErrorOccurredEvent` | Excepción no controlada en un punto clave del flujo (Kernel, Planner, Agent, Tool, Memory, Plugin) | El módulo donde ocurre | `source: str`, `error: str`, `context: dict \| None` | Bloqueado — requiere decidir en qué puntos exactos se captura |
| 14 | `PluginLoadedEvent` | El (futuro) `loader.py` carga e inicializa un plugin con éxito | `plugins/loader.py` | `plugin_name: str`, `version: str` | Bloqueado por `plugins/` (0% implementado) |
| 15 | `PluginUnloadedEvent` | Un plugin se descarga | `plugins/loader.py` | `plugin_name: str` | Bloqueado por `plugins/` |

### Notas de implementación pendientes (no decididas en este borrador)

- **Eventos 10–12 (`Memory*`):** `InMemoryStore` no recibe hoy una referencia a `IEventBus` en su constructor — no hay forma de publicar estos eventos sin cambiar esa firma o envolver el store en una capa intermedia (p. ej. un decorator `ObservableMemory(IMemory)` que envuelva cualquier implementación y publique al bus). Cuál de los dos enfoques usar es una decisión de diseño para la tarea que implemente esto, no de este borrador.
- **Emparejamiento exacto del Event Bus:** como ya se documentó en la sección 1 de este diagnóstico, `AsyncEventBus` solo hace match exacto de clase, no jerárquico. Un plugin que quiera reaccionar a "cualquier acción" tendría que suscribirse a `ActionStartedEvent`, `ActionCompletedEvent` y `ActionFailedEvent` por separado — no hay (todavía) una forma de suscribirse a una clase base `ActionEvent` y recibir las tres. Sigue sin resolverse; queda como el mismo hueco ya señalado.
- **`docs/contracts/IPlugin.md` e `docs/contracts/ITool.md` quedarían desactualizados** una vez que se implemente este catálogo (notación de eventos distinta, y el paso 9 del flujo de `ITool.md` referenciando un evento que ya no existiría tal cual). Actualizarlos es trabajo de la tarea de implementación, no de este borrador.
