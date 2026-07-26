# Planner — Spec

> **BORRADOR — requiere aprobación.** Escrito en una sesión nocturna sin
> supervisión (2026-07-24) a partir de `docs/01_ARCHITECTURE.md`,
> `docs/contracts/IAgent.md`, `docs/contracts/ITool.md` y el código real ya
> implementado (`contracts/agent.py`, `contracts/tool.py`,
> `llm/ollama_provider.py`, `core/kernel.py`, `events/`). **No se implementó
> nada de código de Planner** — esto es solo la propuesta de diseño para
> revisar mañana. Cada punto marcado **[REQUIERE DECISIÓN]** es una elección
> de producto/arquitectura que este borrador señala pero no resuelve por su
> cuenta.

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
  sesión/conversación hoy** (`MemoryItem` no tiene `session_id`) —
  **[REQUIERE DECISIÓN]** si se agrega ese campo a `MemoryItem` o si el
  Planner arma el `session_id` como parte de `metadata` (ya es un
  `dict[str, Any]` libre, así que técnicamente ya soportaría esto sin tocar
  el contrato — solo hace falta decidir la convención).

No propongo qué recibe además de texto (imágenes, archivos adjuntos, etc.)
porque no hay nada en `docs/01_ARCHITECTURE.md` ni en los contratos que lo
sugiera todavía — se agrega cuando haga falta, no antes.

### De dónde saca el Planner el "entendimiento" del texto

El único componente de IA generativa que existe hoy en el código es
`ILLMProvider`/`OllamaProvider` (`complete()`, `embed()`, `is_available()`).
Propuesta: el Planner usa `llm_provider.complete(prompt, ...)` con un prompt
que le pide al modelo devolver una intención estructurada (JSON: acción +
parámetros) en vez de texto libre — es el patrón estándar de "structured
output via prompting" y no requiere ningún componente nuevo más allá de lo
que ya existe. **[REQUIERE DECISIÓN]**: si esto se hace con prompting plano
(pedirle JSON al modelo y parsearlo, frágil pero cero dependencias nuevas) o
si se necesita algo más robusto (function calling si el proveedor lo
soporta, grammar-constrained decoding, etc.) — `OllamaProvider` tal como
está hoy no expone nada de eso, solo `complete()`/`embed()` genéricos.

---

## 2. Cómo decide entre Agent y Tool

`docs/contracts/ITool.md` ya da la distinción conceptual:

> **Agent:** Ejecutor genérico de un sistema (ej: WindowsAgent)
> **Tool:** Acción específica ejecutable (ej: `send-email`), más específica,
> tipada y schema-driven.

Hoy **no existe ningún `ITool` concreto** (`PROGRESS.md`: "No hay ninguna
clase concreta que implemente `ITool`"), solo tres `IAgent` (`FileSystemAgent`,
`ProcessAgent`, `GitAgent`). Así que, en la práctica, cualquier regla de
decisión Agent-vs-Tool es hoy un no-op (siempre gana Agent, porque no hay
Tools con quien competir) — pero vale la pena dejar la regla escrita para
cuando existan Tools, en vez de improvisarla ese día.

Propuesta de regla de decisión (para cuando ambos existan):

1. El Planner mantiene (o consulta a) un registro de capacidades: para cada
   `IAgent` registrado, `get_capabilities() -> list[str]`; para cada `ITool`
   registrado, `get_actions() -> list[str]` (parte de `get_metadata()`).
   **Ese registro no existe como código todavía** — `agents/manager.py` está
   vacío (`PROGRESS.md`), y no hay ningún `ToolRegistry` equivalente. Este
   es el hueco de implementación más grande para que el Planner pueda hacer
   cualquier cosa, más allá de la lógica de decisión en sí.
2. Si la acción que el LLM identificó coincide con `get_actions()` de algún
   Tool registrado, preferir el Tool sobre cualquier Agent que también
   ofrezca una acción con ese nombre. Motivo: un Tool es "más específico,
   tipado y schema-driven" por definición del propio contrato — se asume
   más seguro/predecible que un Agent genérico. **[REQUIERE DECISIÓN]**:
   esto es una prioridad implícita que nadie escribió explícitamente en
   ningún contrato — la estoy proponiendo acá, no citándola de otro lado.
3. Si no hay Tool que la cubra, buscar un Agent cuyo `get_capabilities()`
   incluya la acción.
4. Si ninguno la cubre, el Planner no ejecuta nada — responde que la acción
   no está soportada y publica `ErrorOccurredEvent` (ver catálogo de
   eventos). No hay fallback silencioso.
5. Antes de ejecutar, el Planner debe consultar `requires_confirmation(action, **kwargs)`
   (Agent) o `requires_authorization(action)` (Tool) — **dos métodos con
   nombre distinto para el mismo concepto**, ya señalado como inconsistencia
   entre `IAgent.md` e `ITool.md`. El Planner tendría que normalizar esto
   internamente (ej. un `_needs_confirmation(actor, action, **kwargs) -> bool`
   propio que llame al método correcto según el tipo de `actor`).
   **[REQUIERE DECISIÓN]**: si esta inconsistencia de nombres se corrige en
   los contratos (unificar a un solo nombre de método) antes de escribir el
   Planner, o si el Planner simplemente absorbe la diferencia.

### Qué pasa si el usuario no confirma

Ni `IAgent.md` ni `ITool.md` dicen cómo se le pide confirmación al usuario
ni qué pasa si la niega — el flujo de `ITool.md` dice "Si requiere auth,
pedir OK al usuario" sin más detalle. **[REQUIERE DECISIÓN]** completa: es
un mecanismo de UI/interacción que no existe en ningún contrato todavía
(¿el Planner bloquea y espera una respuesta? ¿publica un evento y otro
componente maneja el prompt al usuario? ¿por dónde entra esa respuesta:
otro `handle()`, un evento de vuelta?).

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
se corta ahí — **[REQUIERE DECISIÓN]**: si se sigue ejecutando el resto de
los pasos del plan tras un fallo parcial, o se aborta todo el plan. Ninguno
de los contratos existentes lo dice.

### Quién llama a `Planner.handle()`

Hoy `Kernel.run()` es un stub (`await asyncio.sleep(0.1)`, `core/kernel.py`)
— no invoca nada. Para que el Planner reciba texto de verdad, `Kernel.run()`
(o algún loop nuevo) tiene que llamarlo. **[REQUIERE DECISIÓN]** completa,
fuera del alcance de este borrador: cómo entra el input del usuario al
sistema en primer lugar (¿un endpoint HTTP en `api.py`? ¿un loop de consola?
¿la futura pipeline de voz?) — este documento asume que *algo* le da al
Planner un `str`, no dice qué.

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
ya implementado y usado por los tres agentes reales):
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

**[REQUIERE DECISIÓN]**, con dos caminos obvios y ninguno decidido acá:

- **(a) Normalizar:** el Planner convierte todo internamente a una sola
  forma (¿`ActionResult`, ya que es la que más código real usa hoy?) antes
  de reportar — Tool→Agent adapter, mapeando `success` → `status`,
  `result` → `data`, sin `output` (o con `output=None`).
- **(b) Unión discriminada:** el Planner reporta `list[ActionResult | ToolResult]`
  tal cual, y quien consuma `PlanExecutedEvent`/la respuesta de `handle()`
  tiene que manejar ambos tipos.

Mi lectura (no vinculante, es una opinión de este borrador, no una
decisión): (a) es más simple para todo lo que consuma el resultado del
Planner después (Memory, la respuesta al usuario, un futuro Skill/Brain),
pero pierde información si `ToolResult.result` tiene una forma muy distinta
de lo que `ActionResult.data` esperaría. No lo resuelvo acá a propósito.

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
respuesta en lenguaje natural para el usuario, y eso probablemente vuelve a
pasar por `ILLMProvider.complete()` con otro prompt. **[REQUIERE DECISIÓN]**
si eso lo hace el propio Planner o un componente separado (el "Brain" que
menciona `docs/01_ARCHITECTURE.md` en el flujo, que tampoco existe como
código todavía).

---

## 5. Resumen de todo lo marcado [REQUIERE DECISIÓN]

Para que mañana sea fácil de escanear sin releer todo el documento:

1. Cómo se representa `session_id`/contexto de conversación en `IMemory` (¿campo nuevo en `MemoryItem`, o convención en `metadata`?).
2. Prompting plano vs. algo más robusto para que el LLM devuelva una intención estructurada.
3. Prioridad Tool-sobre-Agent cuando ambos cubren la misma acción — propuesta acá, no confirmada en ningún contrato.
4. Unificar el nombre `requires_confirmation`/`requires_authorization` en los contratos, o que el Planner absorba la diferencia.
5. Qué pasa si el usuario no confirma una acción destructiva — mecanismo de interacción completo, sin definir.
6. Si un plan se aborta o sigue tras el fallo de un paso.
7. Quién/qué le da al Planner el `user_input` en primer lugar (falta el "front door" del sistema).
8. Normalizar `ActionResult`/`ToolResult` a una sola forma, o mantenerlos como unión.
9. Quién arma `response_text` — ¿el propio Planner, o un componente "Brain" separado que tampoco existe?

Ninguno de estos 9 puntos se decidió en este borrador a propósito — es
trabajo para revisar mañana, no improvisado en una sesión sin supervisión.

## Referencias
- `docs/01_ARCHITECTURE.md`
- `docs/contracts/IAgent.md`, `src/aries/contracts/agent.py`
- `docs/contracts/ITool.md`, `src/aries/contracts/tool.py`
- `docs/contracts/IMemory.md`, `src/aries/contracts/memory.py`
- `docs/audits/2026-07-24-diagnostico.md` (sección "Propuesta catálogo de eventos")
- `src/aries/core/kernel.py`, `src/aries/llm/ollama_provider.py` (patrones de DI y del único proveedor de IA real que existe hoy)
