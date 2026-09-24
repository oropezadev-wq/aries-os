# Visión

## Una sola tesis, dos fases

Aries es una plataforma de **ejecución operativa gobernada por IA**: la
interacción (por voz, texto o un canal externo) dispara acciones reales
sobre agentes/herramientas, con confirmación humana obligatoria antes de
cualquier efecto irreversible, y trazabilidad de lo que se ejecutó.

Esa tesis no cambió con el pivote. Lo que cambió fue el orden de
validación: en vez de construir primero la plataforma multi-tenant
completa y recién ahí probarla con un cliente real, el proyecto decidió
construir primero un **asistente personal** — un caso de uso propio,
exigente, con hardware real (micrófono/parlante) y sin red de contención
de "es solo una demo" — para forzar que el motor central (Kernel,
Planner, agentes, EventBus, Voice, Routines, Message Bus) funcione de
verdad antes de generalizarlo y ofrecerlo a terceros.

**Fase 1 y Fase 2 no son visiones en competencia.** Son el mismo motor,
primero probado chico y difícil (un usuario, hardware real, sin red de
seguridad comercial), después generalizado grande y replicable (muchos
tenants, canales externos, sin que un desarrollador tenga que estar
mirando cada ejecución).

---

## Fase 1 — Asistente personal (dónde estamos hoy)

### Objetivo de esta fase

Probar en carne propia, con uso diario real, que el motor central
resuelve un caso de uso exigente: **un usuario, un proceso, hardware
real**. Sin multi-tenancy, sin canales externos, sin panel operativo — la
superficie mínima necesaria para que las decisiones de arquitectura del
motor se validen contra la realidad y no contra una demo.

### Qué existe hoy (real, no aspiracional)

- **Kernel** (`core/kernel.py`) — ciclo de vida (`initialize`/`run`/
  `shutdown`), housekeeping de memoria, carga de plugins y de rutinas,
  tick loop asíncrono con intervalos independientes por subsistema.
- **AgentManager + 4 agentes nativos** (`agents/`) — `FileSystemAgent`,
  `ProcessAgent`, `GitAgent`, `DatabaseAgent`, todos detrás del contrato
  `IAgent` (`docs/contracts/IAgent.md`), con `requires_confirmation()`
  como gate explícito antes de cualquier acción destructiva.
- **Sistema de plugins** (`plugins/`) — `IPlugin`/`PluginRegistry`, carga
  aislada (un plugin roto no tumba el Kernel ni bloquea a los demás), un
  plugin cargado queda dispatchable como cualquier `IAgent` nativo.
- **Planner + Brain** (`planner/`, `brain/`) — texto → LLM arma un plan de
  steps → `AgentManager.dispatch()` ejecuta cada uno → Brain arma la
  respuesta en lenguaje natural. Confirmación explícita (frase exacta)
  antes de ejecutar cualquier paso que la requiera.
- **EventBus interno** (`events/`, `contracts/event_bus.py`) — `IEventBus`
  tipado, in-process, para desacoplar quién genera un evento de quién
  reacciona a él dentro del mismo proceso.
- **Voice** (`voice/`) — wake word real sobre hardware real
  (`OpenWakeWordProvider`, con la validación de audio/WASAPI resuelta),
  STT (`FasterWhisperProvider`), TTS (`PiperProvider`), pipeline completo
  con confirmación por voz para acciones riesgosas
  (`docs/specs/Voice.spec.md`).
- **Routines** (`routines/`) — `RoutineManager` con cron real
  (`croniter`), estado de reintento que separa "cuándo le toca" de "si ya
  se confirmó publicada" (evita tanto la pérdida silenciosa como el
  reintento infinito), política de staleness para no ejecutar algo
  disparado hace horas (`docs/specs/Routines.spec.md`).
- **Message Bus** (`messaging/`, `contracts/message_bus.py`) —
  `IMessageBus` sobre Redis Streams para comunicación *entre procesos*
  (API ↔ VoicePipeline), entrega al menos una vez, con ack explícito
  después de actuar, no al leer (`docs/specs/MessageBus.spec.md`).

### Qué NO tiene esta fase (a propósito, no por olvido)

- Multi-tenancy — todo el runtime asume un solo usuario/proceso.
- Canales externos (WhatsApp, web chat, email) — la única interfaz activa
  es Voice + `POST /message` local.
- Workflow engine con checkpoints/estados resumibles — el Planner ejecuta
  un plan de una sola pasada; si el proceso muere a mitad, se pierde.
- Tool registry gobernado con policy de riesgo por rol/tenant.
- Panel operativo, billing, RBAC, auditoría multi-usuario.

### Criterio de éxito de la Fase 1

**2 semanas seguidas de uso real diario** de Voice + Routines + al menos
2 agentes, sin ninguna falla grave en el medio.

- **Falla grave** = algo que impide usar el sistema (el wake word no
  responde, una rutina no se dispara, un agente rompe el proceso, Voice
  se cae y no se recupera sola). Un bug cosmético o un mensaje de log
  feo no cuenta como falla grave.
- **Una caída del equipo por hardware** (apagado o reinicio espontáneo
  del host) **no cuenta como falla grave si Aries se recupera solo**: al
  volver a iniciar sesión el stack arranca sin intervención (supervisor +
  Task Scheduler). Se anota igual en `PROGRESS.md` con su nota, pero no
  resetea el contador. Si Aries no vuelve solo, sí es falla grave.
- **Contador pausado (desde 2026-09-20):** mientras Task Scheduler siga
  desregistrado por el problema eléctrico del equipo, el contador de 2
  semanas no avanza ni se resetea. Sin arranque automático no se puede
  validar la regla anterior (que Aries se recupera solo), y contar días
  de uso manual dejaría llegar al día 14 sin haber probado nunca el
  arranque desatendido real. Los días de uso manual se anotan en
  `PROGRESS.md` como observación y no suman.
- **El contador arranca (desde el día 1) recién cuando se cumplan todas
  estas condiciones:** (1) se consiguió el regulador/UPS; (2) la tarea de
  Task Scheduler está registrada de nuevo; (3) hay una **wake word que
  detecte la voz del usuario de forma confiable, con audio de captura
  verificado como sano** (sin compuerta ni filtrado de Windows). Se
  define por resultado y no por solución: no se da por cerrado que haga
  falta un modelo propio hasta descartar que `hey_jarvis` falle por
  audio degradado (ver `PROGRESS.md`, revisión del diagnóstico de Voice
  del 2026-09-20).
- **(a) Una falla grave resetea el contador a cero.** No se descuenta
  solo el día en que ocurrió — las 2 semanas tienen que ser consecutivas
  y limpias, y vuelven a empezar de cero después de cada falla grave.
- **(b) El seguimiento se registra con una línea por día en
  `PROGRESS.md`.** Un criterio que nadie mide no sirve — sin ese
  registro diario explícito, "2 semanas sin fallas" no es verificable,
  es una impresión.

### Etapa siguiente dentro de la Fase 1 (no en paralelo, no es Fase 2)

Una vez cumplido el criterio de éxito de arriba — **no antes** —, y
todavía dentro de la misma Fase 1 (esto no es generalización
multi-tenant; sigue siendo el mismo asistente personal de un solo
usuario), se suman dos capacidades nuevas, **al mismo tiempo, sin orden
de prioridad entre ellas**:

- **Navegación por internet** — un agente de browsing nuevo, mismo
  patrón `IAgent` que los 4 agentes nativos existentes.
- **Control de dispositivos smart home**, integrando **Home Assistant**
  como backend.

**Bloqueante explícito antes de sumar el agente de browsing (auditoría
de seguridad 2026-09-23, `docs/audits/2026-09-23-security-audit.md`,
hallazgo ALTO #2):** `ProcessAgent` no tiene whitelist de ejecutables —
hoy es un riesgo teórico, acotado por quién puede llegar al API
(`POST /message` sin autenticación es el hallazgo CRÍTICO #1 del mismo
audit, con su propio arreglo en curso). Un agente de browsing cambia
eso de raíz: un LLM eligiendo qué ejecutar con contenido web **no
confiable** de por medio (una página que el propio agente visitó) deja
de ser teórico y pasa a ser directamente explotable — el contenido de
una página puede intentar manipular el plan que arma el LLM. No se
empieza el agente de browsing sin resolver la whitelist de
`ProcessAgent` primero (o un diseño que la vuelva innecesaria).

**No se empieza ninguna de las dos hasta cumplir el criterio de éxito de
arriba.** No es una decisión de prioridad relativa entre ellas, ni
tampoco respecto a la Fase 2 — es una secuencia estricta: primero el
motor demuestra que aguanta 2 semanas reales de uso diario, recién
después se le suma superficie nueva.

#### Candidato post-criterio: AndroidAgent vía Google ARTEMIS (Apache-2.0)

Control de un celular Android real con instrucciones en lenguaje
natural. Se suma como tercero a la etapa post-criterio de Fase 1;
browsing y Home Assistant van primero y no se reemplazan.

**Bloqueado por dependencia externa:** ARTEMIS hoy exige un modelo con
visión en la nube. Decisión tomada: no se envían capturas del celular
personal a un tercero. Queda en espera del VLM local que figura en su
roadmap, sin fecha — puede no habilitarse nunca.

**Forma de integración decidida:** `IAgent` (`AndroidAgent`) consumiendo
el servidor HTTP vía `artemis-client`. No MCP (Aries no es cliente MCP),
no `ITool` (la acción es una instrucción en lenguaje natural, no un
schema puntual).

**Alcance inicial: solo lectura** (leer pantalla y reportar). El agente
acepta instrucciones genéricas desde el diseño; el límite de solo
lectura vive en una capa de permisos separada, no dentro del agente.
Concepto nuevo, no cubierto por `requires_confirmation`. Pendiente de
verificar: si ARTEMIS puede restringirse a acciones no destructivas de
su lado — sin eso, el límite es convención, no garantía.

**Otros puntos abiertos:** colisión de puerto 8000 con la API de Aries;
ADB/scrcpy/FFmpeg reintroducen binarios externos que Voice evitó a
propósito; latencia (30s a varios minutos por tarea) obliga a despacho
fire-and-forget con retorno por `MessageBus`.

---

## Fase 2 — Plataforma SaaS multi-tenant (visión de largo plazo)

### Tesis original, retomada, no reemplazada

`docs/archive/vision-original-saas/01_PRODUCT_VISION.md`: convertir la
interacción conversacional en ejecución operativa gobernada, para
negocios con atención repetitiva (clínicas, centros estéticos,
inmobiliarias, educación privada, talleres), vía canales reales
(WhatsApp, web chat, email), con workflows versionados, tool registry
gobernado, aprobación humana y multi-tenancy desde el diseño. El
diferencial sigue siendo verticalización + ejecución confiable, no "usar
IA" en abstracto.

### Qué se generaliza del motor de la Fase 1

En síntesis: el patrón de contratos explícitos (`IAgent`/`IPlugin`/
`IEventBus`/`IMessageBus`), el gate de confirmación humana, el propio
`IMessageBus` sobre Redis Streams como mecanismo de desacople entre
procesos/servicios, y la forma general del Planner (razonamiento vía
LLM, ejecución vía capa de control separada) sobreviven como base
directa, no como algo a rehacer desde cero. Ver `docs/adr/` para el
detalle de qué decisiones single-tenant vigentes habrá que revisar
puntualmente.

### Qué hay que construir de nuevo (no es una extensión, es trabajo nuevo)

- Multi-tenancy real en el modelo de datos y en el runtime
  (`organization_id` en todo, aislamiento reforzado — ver
  `docs/archive/vision-original-saas/08_SECURITY_AND_MULTI_TENANCY.md`).
- Workflow engine con checkpoints persistentes y estados resumibles
  (`waiting_input`/`waiting_approval`/`waiting_external`) — el Planner
  actual no tiene ningún concepto de "pausar y reanudar más tarde".
- Tool registry gobernado con `risk_level`/`allowed_roles`/rate limits
  por tenant, delante de lo que hoy es `AgentManager.dispatch()` sin
  ninguna capa de autorización.
- Ingestión de canales externos (webhooks, normalización de payload,
  firma) — superficie completamente nueva, no una extensión de Voice.
- RBAC, panel operativo, billing — no existe ningún concepto de usuario/
  rol/organización en el código hoy.

### Cuándo pasa esto a construirse

No antes de que la Fase 1 cumpla su criterio de éxito (y su etapa
siguiente, ver arriba). Este documento señala la dirección; no autoriza
a empezar Fase 2 todavía.

---

## Principios que sobreviven a las dos fases

1. El chat/voz es la interfaz, no el producto — lo que importa es la
   ejecución confiable de la acción real detrás.
2. Toda autonomía tiene límites explícitos; el humano siempre puede
   intervenir antes de una acción irreversible.
3. Ningún componente ejecuta una capacidad que no esté detrás de un
   contrato explícito, documentado antes de escribir el código
   (`docs/contracts/*.md` + `docs/specs/*.spec.md`, en ese orden).
4. Separación estricta entre razonamiento (LLM sugiere) y ejecución (la
   capa de control decide y ejecuta).
5. Nunca fallar en silencio: un componente que no puede completar una
   acción lo registra y lo declara, no lo asume.
6. La documentación guía el código, no al revés.

## Objetivos técnicos heredados

- Modularidad — cada subsistema (`voice`, `routines`, `messaging`,
  `agents`, `plugins`) es reemplazable detrás de su contrato.
- Escalabilidad — no en el sentido de "miles de usuarios" todavía, sino
  de "las decisiones de hoy no fuerzan una reescritura mañana" (motivo
  explícito detrás de decisiones como Redis Streams en vez de pub/sub).
- Bajo costo / offline-first donde tenga sentido (Fase 1: LLM local vía
  Ollama, STT/TTS locales) — deja de ser un requisito duro en Fase 2,
  donde el modelo de negocio puede justificar proveedores cloud.
