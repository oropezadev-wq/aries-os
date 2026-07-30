# Planner — Spec

> **APROBADO (2026-07-25).** Escrito originalmente en una sesión nocturna sin
> supervisión (2026-07-24) a partir de `docs/01_ARCHITECTURE.md`,
> `docs/contracts/IAgent.md`, `docs/contracts/ITool.md` y el código real ya
> implementado (`contracts/agent.py`, `contracts/tool.py`,
> `llm/ollama_provider.py`, `core/kernel.py`, `events/`). Los 9 puntos que
> quedaron marcados `[REQUIERE DECISIÓN]` se resolvieron el 2026-07-25 (ver
> cada decisión en su lugar, y el resumen en la sección 5) y ya están
> implementados en `src/aries/planner/`, `src/aries/brain/` y el endpoint
> `POST /message` de `src/aries/api.py`.
>
> **Corrección de un dato desactualizado:** este documento originalmente
> decía "solo tres `IAgent` (`FileSystemAgent`, `ProcessAgent`, `GitAgent`)"
> y "`agents/manager.py` está vacío". Ambas cosas cambiaron entre el 24 y el
> 25 de julio: hoy existen **cuatro** `IAgent` concretos (se sumó
> `DatabaseAgent`) y **`AgentManager` está implementado** (`agents/manager.py`,
> registra los 4 agentes y expone `dispatch()`/`list_agents()`) — el "hueco
> de implementación más grande" que la sección 2 señalaba ya no es tal; el
> Planner implementado usa `AgentManager` real, no un registro propio.

## Contexto: por qué esto bloquea 14 de 15 eventos

`docs/audits/2026-07-24-diagnostico.md` (sección "Propuesta catálogo de
eventos") ya identificó que `IntentDetectedEvent`, `PlanCreatedEvent` y
`PlanExecutedEvent` los publica el Planner, y que `ActionStartedEvent`/
`ActionCompletedEvent`/`ActionFailedEvent` se disparan alrededor de una
ejecución de `IAgent`/`ITool` — que hoy en la práctica **solo el Planner
orquesta** (no hay otro componente que invoque agentes). Sin una spec de
Planner, esos 6 eventos (más los 3 de `Memory*`, que también dependen de
quién los dispara y cuándo, y los 2 de `Plugin*`) no tienen un punto de
enganche concreto. Este documento no resuelve esa dependencia — solo la deja
menos vaga.

---

## 1. Qué recibe el Planner como input

`docs/01_ARCHITECTURE.md` describe el flujo `Usuario -> Wake Word -> STT ->
Planner -> Brain -> Skill -> Agent -> Resultado`. Voice sigue "no iniciada"
(`PROGRESS.md`), así que hoy el único input real posible es texto — ya sea
tipeado directamente o (más adelante) la salida de STT. Punto de diseño
importante: **el Planner no debería saber ni le debería importar si el texto
vino de voz o de teclado** — por diseño, STT ya convierte a texto antes de
llegar acá, así que la interfaz del Planner puede ser texto-primero desde el
día uno sin bloquear en Voice.

Input propuesto:

```python
async def handle(self, user_input: str, session_id: str | None = None) -> PlanExecutionResult:
    ...
```

- `user_input: str` — el texto ya transcripto/tipeado, sin procesar.
- `session_id: str | None` — para que el Planner pueda pedirle a `IMemory`
  contexto de conversación previo (`memory.search(query, memory_type="conversation")`
  o `memory.get_by_type("conversation")` filtrado por sesión). `IMemory` ya
  existe y funciona (`InMemoryStore`), pero **no tiene ningún campo de
  sesión/conversación hoy** (`MemoryItem` no tiene `session_id`).

  **DECISIÓN (2026-07-25):** `session_id` vive en `MemoryItem.metadata`
  (el dict libre que ya existe), no en un campo nuevo de `MemoryItem`. Se
  promueve a campo real recién cuando exista un backend persistente que
  necesite indexar/filtrar por sesión eficientemente — hoy `InMemoryStore`
  hace scan lineal, así que no hay ganancia en agregar la columna todavía.
  El Planner implementado sigue esta misma convención para el `metadata` de
  los eventos que publica (`session_id` va en `event.metadata`, no en un
  campo dedicado de cada evento) — no hace falta dos convenciones distintas
  para el mismo concepto. **Nota de alcance:** el Planner implementado en
  esta tarea *acepta* `session_id` y lo propaga al `metadata` de sus
  eventos, pero todavía no consulta `IMemory` para traer contexto de
  conversación previo — eso es trabajo de una tarea futura, no de esta
  (la tarea que la pidió fue específicamente "Planner + Brain + endpoint",
  no "Planner + integración de Memory").

No propongo qué recibe además de texto (imágenes, archivos adjuntos, etc.)
porque no hay nada en `docs/01_ARCHITECTURE.md` ni en los contratos que lo
sugiera todavía — se agrega cuando haga falta, no antes.

### De dónde saca el Planner el "entendimiento" del texto

El único componente de IA generativa que existe hoy en el código es
`ILLMProvider`/`OllamaProvider` (`complete()`, `embed()`, `is_available()`).
El Planner usa `llm_provider.complete(prompt, ...)` con un prompt que le
pide al modelo devolver una intención estructurada (JSON: acción +
parámetros) en vez de texto libre.

**DECISIÓN (2026-07-25):** prompting plano (pedirle JSON al modelo y
parsearlo), **validado con Pydantic** antes de confiar en él — no function
calling ni grammar-constrained decoding (`OllamaProvider` no expone nada de
eso hoy, y agregarlo sería una dependencia/diseño nuevo no pedido). Si el
JSON no parsea o no valida contra el schema (`ParsedIntent`, en
`planner/models.py`), se hace **un reintento** con un prompt de corrección
que le muestra al modelo su respuesta inválida anterior. Si el segundo
intento también falla, el Planner publica `ErrorOccurredEvent` y devuelve
un fallo explícito (`PlanExecutionResult(success=False, error=...)`) — nunca
ejecuta una acción a partir de un JSON que no pudo validar, y nunca deja
propagar la excepción de parseo/validación hacia quien llamó a `handle()`.

---

## 2. Cómo decide entre Agent y Tool

`docs/contracts/ITool.md` ya da la distinción conceptual:

> **Agent:** Ejecutor genérico de un sistema (ej: WindowsAgent)
> **Tool:** Acción específica ejecutable (ej: `send-email`), más específica,
> tipada y schema-driven.

Hoy **no existe ningún `ITool` concreto** (`PROGRESS.md`: "No hay ninguna
clase concreta que implemente `ITool`"), y ahora hay **cuatro** `IAgent`
(`FileSystemAgent`, `ProcessAgent`, `GitAgent`, `DatabaseAgent` — corregido,
ver nota al inicio del documento) registrados en `AgentManager`, que **sí
existe como código** (a diferencia de lo que decía la versión anterior de
este borrador). Así que, en la práctica, la regla de decisión Agent-vs-Tool
sigue siendo hoy un no-op (siempre gana Agent, porque no hay Tools con quien
competir), pero queda escrita para cuando existan Tools.

Regla de decisión (para cuando existan Tools):

1. El Planner consulta `AgentManager.list_agents()` (ya implementado, real)
   para saber qué agentes y acciones existen. **No existe ningún
   `ToolRegistry` equivalente** — no se construyó uno en esta tarea porque
   no hay ningún `ITool` concreto que registrar; el Planner implementado
   solo resuelve acciones contra `AgentManager`. El punto de extensión para
   cuando existan Tools es agregar la consulta a un futuro `ToolRegistry`
   *antes* de la consulta a `AgentManager` en el mismo lugar del código
   donde hoy se resuelve cada paso del plan — no hace falta rediseñar nada,
   solo insertar el chequeo que sigue.
2. **DECISIÓN (2026-07-25):** cuando la acción coincida con un Tool
   registrado, el Tool tiene prioridad sobre cualquier Agent que ofrezca una
   acción con el mismo nombre. Justificación: es literalmente lo que dice
   `ITool.md` sobre la diferencia conceptual ("más específico, tipado y
   schema-driven") — preferirlo es coherente con el propio contrato.
3. Si no hay Tool que la cubra, buscar un Agent cuyo `get_capabilities()`
   incluya la acción (esto es lo único que el Planner implementado hace hoy,
   vía `AgentManager.get_agent()`/`dispatch()`).
4. Si ninguno la cubre, el Planner no ejecuta nada — responde que la acción
   no está soportada y publica `ErrorOccurredEvent`. No hay fallback
   silencioso. **Implementado tal cual.**
5. Antes de ejecutar, el Planner consulta si la acción requiere
   confirmación.

**DECISIÓN (2026-07-25) sobre el método:** se unifica a
**`requires_confirmation`** en los dos contratos (`IAgent.md` e
`ITool.md`) — se elimina `requires_authorization` de `ITool.md`/`contracts/tool.py`
(ambos actualizados). Motivo: es un fix barato y aislado (no hay ningún
`ITool` concreto que romper), y estandariza en el nombre que ya usan los 4
agentes reales y que `IAgent.md` ya documenta con el patrón de extensión por
kwargs opcionales. Evita construir una capa de traducción permanente en el
Planner para lo que era solo un nombre distinto del mismo concepto. El
Planner implementado llama `agent.requires_confirmation(action, **kwargs)`
de forma defensiva (reintenta solo con `action` si el agente no acepta los
kwargs extra) porque **no todos los agentes reales aceptan los mismos kwargs
opcionales** (`FileSystemAgent.requires_confirmation` no tiene `**kwargs`
catch-all, a diferencia de `ProcessAgent`/`GitAgent`/`DatabaseAgent`) — esto
no es un bug de ningún agente (el contrato dice que aceptar kwargs extra es
opcional, "puede aceptar"), así que no se tocó ningún agente; el Planner
simplemente se adapta.

### Qué pasa si el usuario no confirma

Ni `IAgent.md` ni `ITool.md` dicen cómo se le pide confirmación al usuario
ni qué pasa si la niega.

**DECISIÓN (2026-07-25):** `Planner.handle(user_input, session_id=None,
confirmed: bool = False)`. Si el paso actual del plan requiere confirmación
y `confirmed` no es `True`, el Planner **no ejecuta ese paso ni ninguno
posterior**, y devuelve `PlanExecutionResult(success=False,
needs_confirmation=True, error="...")` explicando qué acción la requiere.
Nada de loops de espera ni mecanismo de UI/prompt-al-usuario todavía — quien
llame a `handle()` (hoy, el endpoint `POST /message`) es responsable de
mostrarle la advertencia al usuario y volver a llamar a `handle()` con
`confirmed=True` si el usuario acepta. Es deliberadamente el camino más
simple: no presupone una arquitectura de UI/voz que todavía no existe.

---

## 3. Comunicación con el Kernel vía eventos

`core/kernel.py` ya inyecta `event_bus: IEventBus` por constructor y publica
`KernelInitializedEvent`/`KernelShutdownEvent`. Propuesta: `Planner` recibe
el mismo `IEventBus` por constructor (mismo patrón de DI que ya usa
`Kernel`), no un bus separado.

Secuencia propuesta para una llamada a `handle(user_input)` (usando el
catálogo de `docs/audits/2026-07-24-diagnostico.md`, sección "Propuesta
catálogo de eventos"):

```
1. Planner.handle(user_input) arranca
2. Planner interpreta el texto (vía ILLMProvider) → arma la intención
3. publish(IntentDetectedEvent(intent, confidence, raw_input))
4. Planner arma la secuencia de pasos (Agent/Tool + kwargs por paso)
5. publish(PlanCreatedEvent(plan_id, steps, intent))
6. Para cada paso:
   a. publish(ActionStartedEvent(actor_type, actor_name, action))
   b. resultado = await actor.execute(action, **kwargs)
   c. si resultado indica éxito → publish(ActionCompletedEvent(...))
      si no → publish(ActionFailedEvent(...))
7. publish(PlanExecutedEvent(plan_id, success, results))
8. Planner devuelve una respuesta consolidada al caller de handle()
```

Si algo revienta en cualquier paso (excepción no controlada, capacidad no
encontrada), `publish(ErrorOccurredEvent(source, error, context))` y el plan
se corta ahí.

**DECISIÓN (2026-07-25):** un plan **aborta completo en el primer fallo** de
un paso — nada de ejecución best-effort de los pasos restantes. Motivo: la
mayoría de los planes multi-paso tienen dependencias implícitas entre pasos
(ej. "creá el archivo, después commiteálo" — commitear tras un `write_file`
fallido no tiene sentido), así que seguir tras un fallo parcial es el
default más peligroso. Un flag `on_error: "continue"` por paso queda como
posible extensión futura si aparece un caso real que lo pida — no se
construyó ahora sin ese caso concreto.

### Quién llama a `Planner.handle()`

Hoy `Kernel.run()` es un stub (`await asyncio.sleep(0.1)`, `core/kernel.py`)
— no invoca nada.

**DECISIÓN (2026-07-25):** el "front door" es un **endpoint HTTP nuevo,
`POST /message`, en `src/aries/api.py`** (FastAPI, que ya existe y ya tiene
un endpoint real, `/health`) — no un loop de consola, no esperar a que Voice
exista. Motivo: `api.py` ya es un servidor real y funcionando; agregar un
endpoint es el camino más barato a un flujo end-to-end real y testeable hoy,
y es la superficie que un futuro cliente de voz/UI terminaría llamando de
todos modos. `Kernel.run()` sigue sin invocar a Planner — esta decisión
deliberadamente no cablea Planner al Kernel, solo al endpoint HTTP.

### Nota sobre el Event Bus tal como está hoy

`AsyncEventBus` hace match exacto de clase, no jerárquico (documentado en
`docs/audits/2026-07-24-diagnostico.md`, sección 1). Un componente que
quiera reaccionar a "cualquier evento de acción" tiene que suscribirse a
`ActionStartedEvent`, `ActionCompletedEvent` y `ActionFailedEvent` por
separado. Esto no bloquea al Planner (el Planner es el que publica, no el
que se suscribe a sus propios eventos), pero si el Planner también necesita
*escuchar* eventos de otros componentes (ej. `PluginLoadedEvent` para saber
qué nuevas capacidades hay disponibles), esa misma limitación aplica.

---

## 4. Qué forma tiene el resultado de vuelta

Acá hay una discrepancia real entre los dos contratos, verificada contra el
código, no asumida:

**`ActionResult`** (`contracts/agent.py`, lo que devuelve `IAgent.execute()`,
ya implementado y usado por los cuatro agentes reales):
```python
@dataclass
class ActionResult:
    status: ActionStatus  # PENDING | RUNNING | SUCCESS | FAILED | CANCELLED
    output: Optional[str] = None
    error: Optional[str] = None
    data: Optional[dict[str, Any]] = None
    execution_time_ms: float = 0.0
```

**`ToolResult`** (`contracts/tool.py`, lo que devolvería `ITool.execute()`
— hoy sin ninguna implementación concreta):
```python
@dataclass
class ToolResult:
    success: bool
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
```

**Son formas distintas** — `ActionResult` tiene un enum de 5 estados y
separa `output` (texto) de `data` (estructurado); `ToolResult` tiene un
`bool` y un único `result` estructurado, sin campo de texto libre. Si un
plan mezcla pasos de Agent y de Tool (el caso normal, una vez que existan
Tools), el Planner recibe dos formas distintas de "resultado de un paso" y
tiene que decidir qué le devuelve a quien llamó a `handle()`, y qué le pone
en el payload de `PlanExecutedEvent.results`.

**DECISIÓN (2026-07-25): (a) normalizar todo a `ActionResult`.** Con 4
agentes reales ya construidos alrededor de `ActionResult` y cero Tools
reales, el peso del código ya favorece esa forma. El adaptador Tool→ActionResult
(mapeando `success`→`status`, `result`→`data`, sin `output`) viviría **dentro
del Planner** cuando exista el primer Tool real — hoy no existe código de
ese adaptador porque no hay ningún `ToolResult` real que adaptar todavía, y
escribirlo sin un caso real para probarlo hubiera sido código muerto. La
unión discriminada (b) se descarta: obligaría a todo consumidor futuro
(Memory, la respuesta al usuario, `PlanExecutedEvent`) a bifurcar por tipo
para siempre.

### Qué devuelve `handle()` en sí

Propuesta mínima, no vinculante:
```python
@dataclass
class PlanExecutionResult:
    plan_id: str
    success: bool
    steps: list[ActionResult]  # o list[ActionResult | ToolResult], ver arriba
    response_text: str | None  # lo que se le muestra/dice al usuario
```
`response_text` es nuevo — no existe en ningún contrato citado. Alguien
tiene que convertir "el plan corrió, estos fueron los resultados" en una
respuesta en lenguaje natural para el usuario, y eso pasa por otra llamada a
`ILLMProvider.complete()`.

**DECISIÓN (2026-07-25):** `response_text` se genera en un módulo nuevo,
**`src/aries/brain/`**, no dentro de `planner/` — una función mínima,
`generate_response(llm_provider, user_input, plan_success, step_summaries)`,
que arma un prompt con el resultado del plan y llama a
`ILLMProvider.complete()`. El Planner importa y usa esa función; no tiene su
propia lógica de fraseo. `brain/` **no hace nada más que esto por ahora** —
sin lógica de tono/personalidad, sin memoria de conversación propia. Es la
respuesta arquitectónicamente "correcta" según el diagrama de
`01_ARCHITECTURE.md` (Planner -> Brain -> Skill -> Agent), pero se
mantiene deliberadamente mínima: separar más responsabilidades de Brain
antes de que exista una segunda razón real para hacerlo (otro consumidor, un
concern genuinamente distinto) sería abstracción prematura.

---

## 5. Resumen de las 9 decisiones finales (2026-07-25)

1. `session_id` vive en `MemoryItem.metadata`/`event.metadata` (convención, no campo nuevo). Se promueve a campo real cuando exista backend persistente. Planner lo propaga en `metadata`, todavía no consulta `IMemory` (fuera de alcance de esta tarea).
2. Intención estructurada: prompt plano + JSON, validado con Pydantic (`ParsedIntent`). Un reintento con prompt de corrección si falla; si vuelve a fallar, `ErrorOccurredEvent` y fallo explícito.
3. Tool tiene prioridad sobre Agent cuando ambos cubren la misma acción — hoy es un no-op (0 Tools reales), el punto de extensión queda documentado en el código.
4. Unificado a `requires_confirmation` en `IAgent.md` e `ITool.md` — `requires_authorization` eliminado de ambos.
5. `Planner.handle(user_input, session_id=None, confirmed=False)` — si algo requiere confirmación y `confirmed` no es `True`, no ejecuta y devuelve `needs_confirmation=True`. Sin loops de espera ni UI.
6. Un plan aborta completo en el primer fallo de un paso. Sin best-effort parcial.
7. Front door: `POST /message` en `api.py` (FastAPI). No REPL, no Kernel, no esperar Voice.
8. Todo se normaliza a `ActionResult`. El adaptador Tool→ActionResult vive en el Planner (código pendiente hasta que exista el primer Tool real).
9. `response_text` se genera en `brain/` (módulo nuevo, mínimo), no dentro de Planner.

Las 9 están implementadas en `src/aries/planner/`, `src/aries/brain/` y
`src/aries/api.py` (ver `PROGRESS.md` para el detalle de archivos y tests).

## Referencias
- `docs/01_ARCHITECTURE.md`
- `docs/contracts/IAgent.md`, `src/aries/contracts/agent.py`
- `docs/contracts/ITool.md`, `src/aries/contracts/tool.py`
- `docs/contracts/IMemory.md`, `src/aries/contracts/memory.py`
- `docs/audits/2026-07-24-diagnostico.md` (sección "Propuesta catálogo de eventos")
- `src/aries/core/kernel.py`, `src/aries/llm/ollama_provider.py` (patrones de DI y del único proveedor de IA real que existe hoy)
