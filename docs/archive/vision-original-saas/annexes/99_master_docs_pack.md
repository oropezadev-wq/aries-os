# Aries Master Docs Pack

> Documento maestro para inicializar la carpeta `docs/` completa del proyecto.
> Este pack está pensado para un producto SaaS multi-tenant de agentes operativos verticales con motor de workflows, tool execution controlado, memoria, observabilidad, aprobaciones humanas y despliegue escalable.

---

# Estructura objetivo

```text
docs/
├── 00_README.md
├── 01_PRODUCT_VISION.md
├── 02_MASTER_STATE.md
├── 03_SYSTEM_INVARIANTS.md
├── 04_ARCHITECTURE_AND_MODULE_MAP.md
├── 05_DOMAIN_MODEL.md
├── 06_WORKFLOW_ENGINE_SPEC.md
├── 07_TOOLING_AND_AGENT_POLICY.md
├── 08_SECURITY_AND_MULTI_TENANCY.md
├── 09_OBSERVABILITY_AND_EVALS.md
├── 10_ROADMAP_MASTER.md
├── 11_DECISION_LOG.md
├── 12_PILOT_EXECUTION_PLAN.md
├── 13_API_CONTRACTS.md
├── 14_DATABASE_SCHEMA.md
├── 15_DEPLOYMENT_AND_ENVIRONMENTS.md
├── specs/
├── adrs/
├── diagrams/
├── prompts/
└── annexes/
    └── 99_master_docs_pack.md
```

---

# docs/00_README.md

## Propósito

Esta carpeta contiene la documentación fuente de verdad del proyecto Aries.
Su objetivo es alinear producto, arquitectura, operación, seguridad y ejecución técnica para que humanos e IA trabajen sobre un marco coherente.

## Orden de lectura recomendado

1. `01_PRODUCT_VISION.md`
2. `02_MASTER_STATE.md`
3. `03_SYSTEM_INVARIANTS.md`
4. `04_ARCHITECTURE_AND_MODULE_MAP.md`
5. `05_DOMAIN_MODEL.md`
6. `06_WORKFLOW_ENGINE_SPEC.md`
7. `07_TOOLING_AND_AGENT_POLICY.md`
8. `08_SECURITY_AND_MULTI_TENANCY.md`
9. `09_OBSERVABILITY_AND_EVALS.md`
10. `10_ROADMAP_MASTER.md`
11. `11_DECISION_LOG.md`
12. `12_PILOT_EXECUTION_PLAN.md`
13. `13_API_CONTRACTS.md`
14. `14_DATABASE_SCHEMA.md`
15. `15_DEPLOYMENT_AND_ENVIRONMENTS.md`

## Jerarquía documental

En caso de conflicto, manda este orden:

1. `03_SYSTEM_INVARIANTS.md`
2. `11_DECISION_LOG.md`
3. `02_MASTER_STATE.md`
4. `04_ARCHITECTURE_AND_MODULE_MAP.md`
5. `10_ROADMAP_MASTER.md`
6. documentos restantes

## Reglas de uso con IA

* No pedir código sin antes fijar contexto con visión, estado maestro e invariantes.
* Toda propuesta nueva debe validarse contra los invariantes y el decision log.
* Ningún documento debe contradecir explícitamente un ADR o una decisión ya aprobada.
* Toda pieza generada por IA debe indicar módulo afectado, supuestos y riesgos.
* Si una tarea cambia arquitectura, seguridad, multi-tenancy o contratos, primero debe registrarse en `11_DECISION_LOG.md`.

## Convenciones

* Todo identificador técnico usa inglés consistente.
* Toda descripción funcional puede estar en español.
* Todas las entidades multi-tenant deben incluir `organization_id`.
* Todo componente crítico debe tener métricas, logs y trazabilidad.

## Objetivo operativo de esta carpeta

Esta carpeta existe para evitar:

* arquitectura incoherente
* decisiones reabiertas sin control
* prompts ambiguos
* duplicidad de lógica
* deuda técnica por improvisación
* diseño genérico sin verticalización

---

# docs/01_PRODUCT_VISION.md

## Nombre provisional del producto

Aries

## Tipo de producto

Plataforma SaaS multi-tenant de agentes operativos verticales.

## Tesis central

La mayoría de los asistentes de IA actuales conversan, pero no operan procesos de negocio con confiabilidad, trazabilidad, políticas de riesgo, memoria organizacional y supervisión humana.
Aries existe para convertir interacción conversacional en ejecución operativa gobernada.

## Problema que resuelve

Las organizaciones pequeñas y medianas pierden tiempo, ventas, citas, seguimiento y calidad operativa por depender de:

* atención manual repetitiva
* procesos dispersos en WhatsApp, hojas de cálculo y personas
* falta de trazabilidad
* respuestas inconsistentes
* ausencia de automatización con contexto

## Propuesta de valor

Aries permite a una organización:

* capturar solicitudes desde canales reales
* entender intención y contexto
* ejecutar workflows operativos definidos
* usar herramientas internas y externas bajo control
* derivar a humano cuando el riesgo lo exige
* medir resultados de negocio y calidad operativa

## Qué es el producto

* una plataforma de ejecución operativa asistida por IA
* un runtime de workflows con herramientas y memoria
* una capa multi-tenant segura
* un panel de operación y supervisión
* una base de conocimiento contextualizada por tenant
* un sistema medible y auditable

## Qué no es el producto

* un chatbot genérico
* una demo de agente autónomo sin control
* un asistente universal tipo "hace de todo"
* un sistema basado solo en prompts
* una colección desordenada de integraciones

## Cliente ideal inicial

Negocios con atención repetitiva, procesos semi-estructurados y valor alto por respuesta rápida.

Candidatos iniciales:

* clínicas dentales
* centros estéticos
* inmobiliarias
* educación privada
* talleres y servicios locales

## Usuario final vs usuario comprador

### Usuario final

Persona que escribe por WhatsApp, web chat o email buscando información, agendar, resolver, comprar o reprogramar.

### Usuario comprador

Dueño, gerente, administrador u operador que necesita:

* reducir carga operativa
* aumentar conversión
* disminuir no-shows
* centralizar atención
* obtener métricas

## Diferenciación estratégica

El diferencial no es "usar IA" sino combinar:

* verticalización por nicho
* ejecución real de procesos
* motor de workflows con checkpoints
* herramientas registradas y gobernadas
* human-in-the-loop
* telemetría y evaluaciones
* memoria semántica por tenant
* multi-tenancy desde diseño

## Principios de producto

1. El chat es interfaz, no producto.
2. La ejecución confiable vale más que la conversación bonita.
3. Toda autonomía tiene límites claros.
4. El humano siempre puede intervenir.
5. Cada tenant tiene configuración, memoria y políticas propias.
6. Lo que no se mide no mejora.
7. La verticalización gana a la generalidad.

## Capacidades núcleo

* recepción omnicanal
* clasificación de intención
* recuperación de contexto
* ejecución de workflows
* llamada a tools
* aprobaciones humanas
* panel operativo
* knowledge base por tenant
* auditoría y observabilidad
* analytics y evals

## Estrategia de monetización

Modelo mixto:

* setup inicial
* suscripción mensual
* cobro por uso o volumen
* módulos premium
* soporte y SLA

## Norte a 12-24 meses

Convertirse en una plataforma donde cada vertical tenga:

* playbooks operativos reutilizables
* workflows configurables
* métricas de negocio incorporadas
* despliegue rápido por tenant
* operación semiautónoma segura

---

# docs/02_MASTER_STATE.md

## Estado general del proyecto

Estado actual: diseño fundacional.

## Fase actual

Fase 0 - Definición de producto, arquitectura, invariantes y documentación maestra.

## Qué existe hoy

* visión inicial del producto
* stack candidato de alto nivel
* hipótesis de arquitectura multi-tenant
* lineamientos de workflow engine, tools, observabilidad y seguridad
* pack documental base

## Qué no existe aún

* código productivo
* infra de staging
* dashboard funcional
* runtime implementado
* integración real con canales
* facturación
* evals automáticas productivas

## Supuestos vigentes

* el lenguaje principal del backend será Python
* la capa API inicial será FastAPI
* la base principal será PostgreSQL
* se usará `pgvector` para retrieval inicial
* habrá canal inicial principal tipo WhatsApp y canal secundario web chat
* el sistema será multi-tenant desde el diseño de entidades
* el primer vertical se elegirá antes de construir el piloto

## Decisiones aprobadas hasta ahora

* no se construirá un "JARVIS general"
* el producto será una plataforma verticalizada
* no se arrancará con microservicios extremos
* la arquitectura deberá poder evolucionar a event-driven
* toda autonomía sensible tendrá aprobación o validación

## Riesgos identificados

* sobreingeniería temprana
* intentar abarcar demasiados verticales
* costo alto por inferencia sin routing de modelos
* dependencia excesiva del LLM para decisiones críticas
* falta de validación comercial temprana

## Restricciones operativas

* el diseño debe ser compatible con un equipo pequeño
* el MVP debe poder desplegarse sin Kubernetes obligatorio
* el sistema debe mantener trazabilidad completa
* la seguridad y el aislamiento tenant no pueden postergarse

## Objetivo inmediato

Completar documentación fundacional y traducirla en:

* esquema base de BD
* contratos API mínimos
* estructura de repositorio
* primer workflow vertical
* primer lote de herramientas registradas

## Criterios de salida de esta fase

Se considera cerrada la fase actual cuando existan:

* documentación aprobada
* vertical piloto elegido
* arquitectura v1 congelada
* backlog priorizado de implementación
* decision log inicial

---

# docs/03_SYSTEM_INVARIANTS.md

## Propósito

Este documento define restricciones duras del sistema. No son sugerencias. Son reglas obligatorias.

## Invariantes de negocio y arquitectura

### I-001 Multi-tenancy obligatorio

Todo recurso persistente del dominio operacional debe estar vinculado a un `organization_id`.

### I-002 El chat no es la fuente de verdad

El estado operacional vive en entidades del dominio, no en texto libre de conversación.

### I-003 Tool execution gobernado

Ningún agente ni workflow puede ejecutar una tool no registrada en el tool registry.

### I-004 Auditabilidad total

Toda acción con efecto lateral debe generar un `audit_log` y una `tool_invocation` cuando aplique.

### I-005 Riesgo controlado

Toda acción de alto riesgo requiere validación automática reforzada y/o aprobación humana.

### I-006 Checkpoint obligatorio

Toda ejecución de workflow debe guardar checkpoints suficientes para reanudar, inspeccionar o abortar con seguridad.

### I-007 Separación entre razonamiento y ejecución

El LLM puede sugerir decisiones, pero la capa de control del sistema autoriza y ejecuta.

### I-008 Contratos explícitos

Toda tool, endpoint y evento debe tener contrato de entrada y salida definido.

### I-009 Idempotencia en acciones sensibles

Crear citas, enviar mensajes, cobrar, generar tickets o actualizar estados externos debe soportar idempotencia.

### I-010 Human override permanente

Siempre debe existir capacidad de takeover humano y override controlado.

### I-011 Observabilidad mínima obligatoria

Todo componente crítico debe emitir logs estructurados, métricas y trazas.

### I-012 Seguridad por defecto

Acceso mínimo, secretos cifrados y permisos explícitos en integraciones.

### I-013 Evolución compatible

Toda nueva versión debe respetar migraciones, backward compatibility razonable o estrategia clara de transición.

### I-014 Configuración separada del código

Reglas por tenant, prompts, políticas y catálogos no deben hardcodearse cuando pertenezcan al dominio configurable.

### I-015 Verticalización explícita

La lógica específica de un vertical no debe contaminar sin control los módulos core.

### I-016 Ninguna memoria sin política

Toda memoria debe indicar origen, duración, alcance, sensibilidad y reglas de uso.

### I-017 Recuperación contextual validada

El contexto recuperado no debe asumirse como verdad absoluta; debe pasar por filtros de relevancia y política.

### I-018 Fallar de forma segura

Cuando el sistema no tenga suficiente contexto o confianza, debe pedir aclaración, derivar o detener acción.

### I-019 Toda excepción relevante se registra

Errores de tools, timeouts, caídas de integración y decisiones bloqueadas deben persistirse.

### I-020 Diseño para métricas de negocio

El sistema no solo mide eventos técnicos; debe medir outcomes operativos y comerciales.

## Invariantes de implementación

* No mezclar lógica de tenant con lógica global sin separación clara.
* No depender del historial completo de chat para reconstruir estado.
* No exponer secretos en logs.
* No ejecutar efectos laterales directamente desde la capa HTTP sin control de dominio.
* No permitir que un LLM construya SQL libre para producción sin capa controlada.
* No aceptar payloads sin validación tipada.

---

# docs/04_ARCHITECTURE_AND_MODULE_MAP.md

## Visión arquitectónica

Aries se diseña como una plataforma modular con núcleo monolítico evolutivo, preparada para event-driven execution y separación gradual de workloads.

## Estilo arquitectónico inicial

* monolito modular
* APIs HTTP para entrada y panel
* workers asincrónicos para procesamiento pesado
* event backbone desacoplado a partir de la fase 2/3

## Módulos core

### 1. `identity`

Responsable de:

* users
* organizations
* memberships
* roles
* sesiones internas
* API keys

### 2. `channels`

Responsable de:

* webhooks
* recepción y envío de mensajes
* normalización de payloads por canal
* rate limiting de canal
* mapping canal-contacto-sesión

### 3. `contacts`

Responsable de:

* contactos externos
* identidades por canal
* metadata del contacto
* valor comercial y atributos persistentes

### 4. `conversations`

Responsable de:

* sesiones
* mensajes
* resúmenes de conversación
* tags de interacción

### 5. `knowledge`

Responsable de:

* knowledge bases por tenant
* documentos
* chunks
* embeddings
* retrieval logs

### 6. `workflows`

Responsable de:

* definición de workflows
* steps
* edges
* versiones
* ejecución
* checkpoints
* errores
* aprobaciones

### 7. `tools`

Responsable de:

* registro de tools
* permisos de tools
* políticas de riesgo
* invocaciones
* resultados
* límites de uso

### 8. `agents`

Responsable de:

* router
* context builder
* planner
* validator
* handoff summarizer

### 9. `review`

Responsable de:

* review queue
* aprobaciones
* takeover humano
* notas internas
* asignaciones

### 10. `analytics`

Responsable de:

* eventos
* métricas operativas
* costos
* KPIs de negocio
* eval runs

### 11. `billing`

Responsable de:

* planes
* límites
* suscripciones
* uso
* facturación futura

### 12. `platform`

Responsable de:

* feature flags
* configs globales
* health checks
* environment config
* administración interna

## Relaciones entre módulos

* `channels` crea entradas hacia `conversations`.
* `conversations` alimenta a `agents` y `workflows`.
* `agents` consulta `knowledge`, `contacts`, `conversations` y `tools`.
* `workflows` coordina `tools`, `review`, `analytics`.
* `review` puede pausar o modificar `workflows`.
* `analytics` observa a todos los módulos.

## Flujo principal de alto nivel

1. entra mensaje
2. se normaliza
3. se crea o vincula sesión
4. se persiste mensaje
5. se activa router
6. se construye contexto
7. se selecciona respuesta, workflow o tool
8. se valida riesgo
9. se ejecuta o se deriva
10. se registra outcome

## Límites arquitectónicos

* `agents` no persiste directamente fuera de sus puertos definidos.
* `channels` no decide lógica de negocio.
* `tools` no contiene política de producto; ejecuta bajo política externa.
* `knowledge` no altera estado operacional.
* `analytics` no modifica workflows, salvo mecanismos explícitos aprobados.

## Estrategia de evolución

### v1

Monolito modular con workers.

### v2

Extracción de componentes calientes:

* workers de canal
* retrieval jobs
* execution workers
* analytics pipelines

### v3

Bus de eventos formal y separación de bounded contexts si el volumen lo exige.

---

# docs/05_DOMAIN_MODEL.md

## Entidades núcleo

### Organization

Representa un tenant.

Atributos clave:

* id
* slug
* name
* status
* created_at
* settings_json

### User

Usuario interno del sistema.

Atributos clave:

* id
* email
* name
* auth_provider
* status

### Membership

Vincula user con organization.

Atributos:

* id
* organization_id
* user_id
* role
* permissions_json

### Contact

Persona externa que interactúa con la organización.

Atributos:

* id
* organization_id
* name
* phone
* email
* source
* metadata_json
* lead_score
* lifecycle_stage

### ContactIdentity

Identificador del contacto por canal.

Atributos:

* id
* contact_id
* channel
* external_id
* verified

### Session

Unidad conversacional/contextual activa.

Atributos:

* id
* organization_id
* contact_id
* channel
* status
* current_execution_id
* last_message_at

### Message

Evento textual o multimedia dentro de una sesión.

Atributos:

* id
* organization_id
* session_id
* direction
* sender_type
* content
* content_type
* raw_payload_json

### Workflow

Plantilla lógica de proceso.

Atributos:

* id
* organization_id
* name
* vertical
* status
* current_version_id

### WorkflowVersion

Versión inmutable del workflow.

Atributos:

* id
* workflow_id
* version
* definition_json
* published_at

### WorkflowStep

Paso dentro de una versión.

Atributos:

* id
* workflow_version_id
* key
* type
* config_json
* risk_level

### WorkflowEdge

Transición entre pasos.

Atributos:

* id
* workflow_version_id
* source_step_key
* target_step_key
* condition_json

### Execution

Instancia corriendo de un workflow.

Atributos:

* id
* organization_id
* workflow_id
* workflow_version_id
* session_id
* status
* current_step_key
* risk_level
* requires_approval
* checkpoint_json

### ExecutionStep

Registro de cada paso ejecutado.

Atributos:

* id
* execution_id
* step_key
* status
* input_json
* output_json
* started_at
* finished_at

### Tool

Capacidad ejecutable registrada.

Atributos:

* id
* organization_scope
* name
* version
* category
* input_schema_json
* output_schema_json
* side_effect_level

### ToolInvocation

Uso real de una tool.

Atributos:

* id
* organization_id
* execution_id
* tool_id
* status
* input_json
* output_json
* idempotency_key

### Approval

Aprobación humana requerida.

Atributos:

* id
* organization_id
* execution_id
* status
* requested_by
* resolved_by
* reason

### AuditLog

Rastro de seguridad y operación.

Atributos:

* id
* organization_id
* actor_type
* actor_id
* action
* target_type
* target_id
* details_json

### KnowledgeBase

Conjunto documental por tenant.

Atributos:

* id
* organization_id
* name
* status

### Document

Documento fuente.

Atributos:

* id
* knowledge_base_id
* title
* source_type
* mime_type
* version

### DocumentChunk

Fragmento indexado.

Atributos:

* id
* document_id
* chunk_index
* content
* embedding_vector
* metadata_json

### ReviewItem

Trabajo pendiente de revisión humana.

Atributos:

* id
* organization_id
* execution_id
* priority
* reason
* status
* assigned_to

### Event

Evento analítico o de plataforma.

Atributos:

* id
* organization_id
* event_name
* event_type
* payload_json
* emitted_at

## Relaciones principales

* Organization 1:N Membership
* Organization 1:N Contact
* Contact 1:N Session
* Session 1:N Message
* Workflow 1:N WorkflowVersion
* WorkflowVersion 1:N WorkflowStep
* WorkflowVersion 1:N WorkflowEdge
* Workflow 1:N Execution
* Execution 1:N ExecutionStep
* Tool 1:N ToolInvocation
* Execution 1:N ToolInvocation
* Execution 1:N Approval
* Organization 1:N AuditLog
* KnowledgeBase 1:N Document
* Document 1:N DocumentChunk

---

# docs/06_WORKFLOW_ENGINE_SPEC.md

## Propósito

Definir cómo se modelan, ejecutan, pausan, reanudan, validan y observan los workflows del sistema.

## Objetivos del engine

* ejecución determinística con puntos de decisión controlados
* soporte para tools y pasos automáticos
* checkpoints persistentes
* pausas por aprobación humana
* reintentos seguros
* inspección completa por operador

## Conceptos

### Workflow

Definición lógica versionada de un proceso.

### Step

Unidad ejecutable o evaluable.
Tipos posibles:

* `message_response`
* `collect_input`
* `run_tool`
* `decision`
* `wait_for_event`
* `handoff`
* `approval_gate`
* `end`

### Edge

Transición condicionada entre pasos.

### Execution

Instancia activa o finalizada de un workflow.

### Checkpoint

Estado persistido que permite reanudación.

## Estados de ejecución

* `created`
* `queued`
* `running`
* `waiting_input`
* `waiting_approval`
* `waiting_external`
* `completed`
* `failed`
* `cancelled`
* `expired`

## Ciclo de vida

1. se crea execution
2. se resuelve versión de workflow
3. se inicializa contexto
4. se entra a primer step
5. se ejecutan steps según edges
6. se persiste resultado y checkpoint por step
7. se finaliza o se pausa

## Reglas de ejecución

* Cada step debe ser idempotente o declarar estrategia de idempotencia.
* Ningún step con efecto lateral puede ejecutarse sin validación previa.
* Todo step produce un `step_result` estructurado.
* Todo error produce `execution_failure` persistido.

## Checkpoint mínimo

Cada checkpoint debe guardar:

* execution_id
* workflow_version_id
* current_step_key
* resolved_context
* pending_inputs
* pending_approval_id
* retry_count
* last_transition_at
* last_error

## Retries

### Reintentos automáticos permitidos en

* timeouts transitorios
* fallas temporales de red
* rate limits externos

### No reintentar automáticamente en

* validación de negocio fallida
* tool no autorizada
* aprobación rechazada
* esquema inválido

## Approval gates

Un workflow puede declarar gates en cualquier step si:

* el riesgo es alto
* hay efecto económico
* hay impacto reputacional
* hay cambio irreversible

## Human handoff

Cuando un workflow entra en handoff:

* se crea `review_item`
* se resume contexto para humano
* se congela acción automática sensible
* puede proponerse respuesta sugerida

## Definición base de workflow

Debe incluir:

* metadata
* versión
* trigger
* inputs requeridos
* steps
* edges
* policies
* allowed_tools
* timeout policy
* retry policy

## Ejemplo conceptual

Workflow: `appointment_booking`

Steps:

1. classify_intent
2. collect_required_fields
3. search_available_slots
4. propose_slots
5. confirm_selection
6. create_appointment
7. send_confirmation
8. end

## Criterios de engine listo para producción

* trazabilidad por step
* replay controlado
* inspección manual
* métricas por workflow
* bloqueo seguro por riesgo
* compatibilidad con versiones

---

# docs/07_TOOLING_AND_AGENT_POLICY.md

## Propósito

Definir cómo funcionan los agentes del sistema y bajo qué reglas usan tools.

## Política general

Los agentes no son actores soberanos. Son componentes de decisión asistida dentro de un runtime controlado.

## Roles de agentes

### Router Agent

Clasifica intención y enruta.

### Context Builder Agent

Construye contexto relevante para el caso actual.

### Planner Agent

Decide siguiente acción dentro del marco permitido.

### Validator Agent

Verifica formato, coherencia, policy compliance y riesgo.

### Handoff Summarizer Agent

Prepara contexto claro para revisión humana.

## Política de agentes

* un agente no puede ejecutar código arbitrario
* un agente solo opera dentro del scope del caso actual
* un agente solo puede usar tools permitidas por policy y workflow
* toda llamada a tool debe quedar registrada
* un agente no cambia permisos ni políticas del sistema

## Definición de tool

Una tool es una capacidad ejecutable versionada, con contrato explícito y política asociada.

## Metadatos mínimos de tool

* `name`
* `version`
* `category`
* `description`
* `input_schema`
* `output_schema`
* `risk_level`
* `side_effect_level`
* `requires_approval`
* `allowed_roles`
* `timeout_ms`
* `idempotent`

## Categorías de tools

### System tools

* send_message
* create_note
* tag_contact
* create_task

### Domain tools

* find_available_slot
* register_patient
* create_property_visit
* calculate_quote

### Integration tools

* google_calendar_create_event
* crm_upsert_contact
* sheets_append_row
* payment_link_create

### Analytics tools

* generate_daily_summary
* detect_drop_off_pattern

## Política de riesgo

### Bajo

Lectura o acción reversible sin impacto externo fuerte.

### Medio

Acción externa limitada o actualización no crítica.

### Alto

Acción con efecto operativo directo sobre cliente o agenda.

### Crítico

Cobros, compromisos sensibles, cambios irreversibles, datos altamente sensibles.

## Reglas por riesgo

* Bajo: ejecución automática con logging.
* Medio: ejecución automática con validación estricta.
* Alto: puede requerir approval gate según tenant/policy.
* Crítico: approval humana obligatoria salvo regla explícita y auditada.

## Política de selección de tools

La selección de tools se basa en:

* workflow actual
* tenant policy
* role
* contexto disponible
* nivel de riesgo
* disponibilidad de integración

## Prohibiciones explícitas

* tool chaining libre sin límites
* ejecución de SQL arbitrario
* acceso a credenciales desde prompts
* tool discovery no controlado en runtime productivo

## Criterios para aprobar una nueva tool

* contrato definido
* política de riesgo asignada
* owner responsable
* tests mínimos
* observabilidad mínima
* rollback o compensación si aplica

---

# docs/08_SECURITY_AND_MULTI_TENANCY.md

## Propósito

Establecer el modelo de aislamiento, autenticación, autorización y seguridad operativa del sistema.

## Principio rector

Seguridad por defecto y mínimo privilegio.

## Aislamiento tenant

* todo dato operacional pertenece a una `organization`
* consultas deben filtrar por `organization_id`
* tablas críticas tendrán mecanismos de aislamiento reforzado
* ningún proceso puede mezclar datos de dos tenants en un mismo contexto operativo

## Roles internos sugeridos

* owner
* admin
* operator
* reviewer
* analyst
* developer_internal

## Controles de acceso

* RBAC para panel y APIs
* permisos explícitos por módulo
* scopes por integración
* separación entre acceso humano e invocación de sistema

## Gestión de secretos

* secretos cifrados en reposo
* rotación posible
* acceso restringido por servicio
* jamás loggear tokens, keys o payloads sensibles completos

## Seguridad de tools

* tool registry con whitelist
* validación de input por esquema
* rate limits por tenant y tool
* approvals por riesgo
* idempotency keys
* logs de invocación

## Seguridad de integraciones

* credenciales por tenant
* scopes mínimos
* estado de health por integración
* posibilidad de desactivar integración comprometida

## Seguridad de datos

Clasificación sugerida:

* pública
* interna
* sensible operacional
* sensible personal
* crítica

## Reglas de datos sensibles

* enmascarado en panel si corresponde
* minimización en prompts
* no persistir más de lo necesario
* reglas de retención definidas por categoría

## Eventos de seguridad que deben loggearse

* login
* logout
* cambio de rol
* alta/baja de integración
* fallo repetido de autenticación
* approval crítica
* override humano
* acceso denegado

## Incidentes y respuesta

Ante incidente de seguridad:

1. aislar tenant o integración afectada
2. congelar actions críticas si aplica
3. preservar logs
4. registrar incidente
5. ejecutar protocolo de comunicación y remediación

---

# docs/09_OBSERVABILITY_AND_EVALS.md

## Propósito

Definir cómo el sistema será medido, inspeccionado y mejorado.

## Observabilidad mínima

Todo componente crítico debe emitir:

* logs estructurados
* métricas
* trazas

## Señales requeridas

### Logs

Deben incluir como mínimo:

* timestamp
* level
* service
* module
* organization_id si aplica
* session_id o execution_id si aplica
* correlation_id
* event_name

### Métricas

Medir:

* requests por endpoint
* latencia p50/p95/p99
* errores por servicio
* throughput
* queue lag
* tool success rate
* workflow completion rate
* approval rate
* handoff rate
* token/cost usage

### Trazas

Deben permitir seguir una ejecución desde:

* entrada de mensaje
* routing
* retrieval
* decisión
* tool call
* validación
* respuesta

## KPIs de producto

* tiempo medio de primera respuesta
* tasa de resolución automática
* tasa de handoff humano
* leads capturados
* citas creadas
* citas confirmadas
* no-show reduction
* conversión por canal
* costo IA por outcome

## Evals

### Objetivos

* evitar regresiones
* medir calidad por workflow
* validar prompts y policies
* comparar versiones

### Tipos de eval

* offline eval
* regression eval
* shadow eval
* canary eval
* manual review eval

### Casos de prueba por workflow

Cada workflow debe tener:

* happy path
* missing data
* ambiguous input
* conflict with policy
* external tool failure
* high risk action

### Métricas de eval

* intent classification accuracy
* tool selection correctness
* policy compliance rate
* output completeness
* hallucination avoidance
* human review acceptance rate

## Regla de release

No promover a producción si:

* cae la tasa de cumplimiento de policy
* suben errores críticos
* cae la precisión por debajo del umbral aprobado
* aumenta demasiado el costo por outcome

---

# docs/10_ROADMAP_MASTER.md

## Fase 0 - Fundaciones

Objetivos:

* documentación maestra
* invariantes aprobados
* vertical piloto elegido
* backlog inicial

## Fase 1 - Core platform

Entregables:

* auth y organizations
* contacts, sessions, messages
* workflows base
* tool registry
* audit logs
* panel básico

## Fase 2 - Context and memory

Entregables:

* knowledge bases
* document ingestion
* chunking
* retrieval
* summaries

## Fase 3 - Controlled execution

Entregables:

* execution engine v1
* approvals
* handoff humano
* retry policies
* observabilidad básica

## Fase 4 - Vertical pilot

Entregables:

* primer vertical productizado
* canal principal integrado
* 3 a 5 workflows clave
* métricas de negocio

## Fase 5 - SaaS hardening

Entregables:

* billing base
* límites de uso
* feature flags
* multi-tenant hardening
* dashboards de analytics

## Fase 6 - Scale and optimization

Entregables:

* event backbone maduro
* model routing
* evaluaciones automatizadas
* mejora de costos
* soporte multi-vertical controlado

## Criterios de priorización

Ordenar por:

1. impacto comercial
2. reducción de riesgo
3. habilitación de arquitectura futura
4. velocidad de validación

## Qué no entra al inicio

* voz avanzada
* agentes completamente autónomos
* fine-tuning prematuro
* demasiados verticales a la vez
* microservicios sin necesidad demostrada

---

# docs/11_DECISION_LOG.md

## Formato

Cada decisión debe registrar:

* ID
* fecha
* estado
* contexto
* decisión
* alternativas consideradas
* consecuencias

## Decisiones iniciales

### D-001

Fecha: por definir
Estado: aprobado

Contexto:
Se requiere una base sólida y escalable sin sobreingeniería.

Decisión:
Iniciar con monolito modular en lugar de microservicios completos.

Alternativas:

* microservicios desde el día 1
* serverless fragmentado

Consecuencias:
Mayor simplicidad operativa, menor costo inicial, evolución gradual.

### D-002

Fecha: por definir
Estado: aprobado

Contexto:
El producto requiere confianza operacional y diferenciación.

Decisión:
Construir plataforma verticalizada de agentes operativos, no asistente generalista.

Consecuencias:
Mayor foco comercial y moat por nicho.

### D-003

Fecha: por definir
Estado: aprobado

Decisión:
Usar PostgreSQL como base operacional principal.

### D-004

Fecha: por definir
Estado: aprobado

Decisión:
Usar `pgvector` para retrieval inicial en lugar de introducir una vector DB separada desde el inicio.

### D-005

Fecha: por definir
Estado: aprobado

Decisión:
Toda acción de alto riesgo tendrá approval gate o validación reforzada.

### D-006

Fecha: por definir
Estado: aprobado

Decisión:
Toda entidad operacional crítica tendrá `organization_id`.

### D-007

Fecha: por definir
Estado: aprobado

Decisión:
Separar explícitamente modules core de lógica vertical.

---

# docs/12_PILOT_EXECUTION_PLAN.md

## Objetivo

Definir el piloto inicial con alcance realista y medible.

## Vertical piloto

Pendiente de selección final.

Candidatos priorizados:

* clínica dental
* estética
* inmobiliaria

## Criterios para elegir vertical

* frecuencia alta de interacción
* valor económico claro
* proceso repetible
* dolor operativo evidente
* poca necesidad de integración compleja inicial

## Alcance del piloto

Debe resolver 3 a 5 workflows críticos del vertical elegido.

Ejemplo para clínica:

* captación de lead
* agendamiento/reagendamiento
* confirmación de cita
* respuesta FAQ básica
* handoff a humano

## Canal piloto

Canal principal sugerido: WhatsApp.
Canal secundario: web chat.

## Entregables del piloto

* 1 tenant piloto funcional
* panel interno mínimo
* knowledge base operativa
* workflows instrumentados
* métricas base

## Métricas de éxito del piloto

* tiempo medio de respuesta
* tasa de captura de datos correctos
* tasa de cita completada
* tasa de handoff
* satisfacción operativa interna
* reducción de trabajo manual

## Riesgos del piloto

* vertical mal elegido
* integración de canal compleja
* datos reales de baja calidad
* expectativas irreales de autonomía

## Criterios de cierre del piloto

* al menos un workflow produce valor claro
* la organización piloto quiere continuar
* se detectan mejoras concretas priorizadas
* hay evidencia para pricing o siguiente fase

---

# docs/13_API_CONTRACTS.md

## Propósito

Definir contratos mínimos de API para v1.

## Principios

* versionado por prefijo
* payloads tipados
* errores consistentes
* auth explícita
* contratos estables

## Endpoints base sugeridos

### Auth

* `POST /api/v1/auth/login`
* `POST /api/v1/auth/logout`
* `GET /api/v1/auth/me`

### Organizations

* `GET /api/v1/organizations/current`
* `PATCH /api/v1/organizations/current`

### Contacts

* `GET /api/v1/contacts`
* `POST /api/v1/contacts`
* `GET /api/v1/contacts/{id}`
* `PATCH /api/v1/contacts/{id}`

### Sessions

* `GET /api/v1/sessions`
* `GET /api/v1/sessions/{id}`
* `POST /api/v1/sessions/{id}/takeover`

### Messages

* `GET /api/v1/sessions/{id}/messages`
* `POST /api/v1/messages/send`

### Workflows

* `GET /api/v1/workflows`
* `POST /api/v1/workflows`
* `GET /api/v1/workflows/{id}`
* `POST /api/v1/workflows/{id}/publish`

### Executions

* `GET /api/v1/executions`
* `GET /api/v1/executions/{id}`
* `POST /api/v1/executions/{id}/resume`
* `POST /api/v1/executions/{id}/cancel`

### Tools

* `GET /api/v1/tools`
* `POST /api/v1/tools/{id}/test`
* `GET /api/v1/tool-invocations/{id}`

### Review

* `GET /api/v1/review/items`
* `POST /api/v1/review/items/{id}/approve`
* `POST /api/v1/review/items/{id}/reject`
* `POST /api/v1/review/items/{id}/assign`

### Knowledge

* `GET /api/v1/knowledge-bases`
* `POST /api/v1/knowledge-bases`
* `POST /api/v1/documents/upload`
* `POST /api/v1/documents/{id}/reindex`

## Contrato de error base

```json
{
  "error": {
    "code": "string",
    "message": "string",
    "details": {},
    "request_id": "string"
  }
}
```

## Reglas

* toda respuesta debe incluir `request_id`
* endpoints sensibles deben registrar audit log
* operaciones con side effects deben aceptar idempotency key cuando aplique

---

# docs/14_DATABASE_SCHEMA.md

## Propósito

Documentar el esquema lógico inicial de base de datos.

## Convenciones

* PK tipo UUID
* timestamps UTC
* `organization_id` obligatorio en tablas tenant-scoped
* soft delete solo donde tenga valor operativo
* índices en claves externas y filtros frecuentes

## Tablas núcleo

### organizations

* id
* slug
* name
* status
* settings_json
* created_at
* updated_at

### users

* id
* email
* name
* password_hash
* auth_provider
* status
* created_at
* updated_at

### memberships

* id
* organization_id
* user_id
* role
* permissions_json
* created_at

### contacts

* id
* organization_id
* name
* phone
* email
* source
* lifecycle_stage
* lead_score
* metadata_json
* created_at
* updated_at

### contact_identities

* id
* organization_id
* contact_id
* channel
* external_id
* verified
* created_at

### sessions

* id
* organization_id
* contact_id
* channel
* status
* current_execution_id
* last_message_at
* created_at
* updated_at

### messages

* id
* organization_id
* session_id
* direction
* sender_type
* content
* content_type
* raw_payload_json
* created_at

### workflows

* id
* organization_id
* name
* vertical
* status
* current_version_id
* created_at
* updated_at

### workflow_versions

* id
* organization_id
* workflow_id
* version
* definition_json
* published_at

### executions

* id
* organization_id
* workflow_id
* workflow_version_id
* session_id
* status
* current_step_key
* risk_level
* requires_approval
* checkpoint_json
* started_at
* finished_at

### execution_steps

* id
* organization_id
* execution_id
* step_key
* status
* input_json
* output_json
* started_at
* finished_at

### tools

* id
* organization_scope
* name
* version
* category
* input_schema_json
* output_schema_json
* risk_level
* side_effect_level
* active

### tool_invocations

* id
* organization_id
* execution_id
* tool_id
* status
* input_json
* output_json
* idempotency_key
* duration_ms
* created_at

### approvals

* id
* organization_id
* execution_id
* status
* reason
* requested_by
* resolved_by
* created_at
* resolved_at

### audit_logs

* id
* organization_id
* actor_type
* actor_id
* action
* target_type
* target_id
* details_json
* created_at

### knowledge_bases

* id
* organization_id
* name
* status
* created_at

### documents

* id
* organization_id
* knowledge_base_id
* title
* source_type
* mime_type
* version
* metadata_json
* created_at

### document_chunks

* id
* organization_id
* document_id
* chunk_index
* content
* embedding_vector
* metadata_json
* created_at

### review_items

* id
* organization_id
* execution_id
* priority
* reason
* status
* assigned_to
* created_at
* resolved_at

### events

* id
* organization_id
* event_name
* event_type
* payload_json
* emitted_at

## Índices sugeridos

* `contacts(organization_id, phone)`
* `contact_identities(organization_id, channel, external_id)`
* `sessions(organization_id, contact_id, status)`
* `messages(organization_id, session_id, created_at)`
* `executions(organization_id, status, current_step_key)`
* `tool_invocations(organization_id, tool_id, created_at)`
* `review_items(organization_id, status, priority)`
* índice vectorial en `document_chunks.embedding_vector`

---

# docs/15_DEPLOYMENT_AND_ENVIRONMENTS.md

## Objetivo

Definir cómo se desplegará el sistema y qué entornos existirán.

## Entornos

### local

Desarrollo individual.

### dev

Entorno compartido de desarrollo.

### staging

Preproducción con configuración cercana a producción.

### production

Entorno estable para tenants reales.

## Principios de despliegue

* infraestructura reproducible
* configuración por entorno
* migraciones controladas
* observabilidad habilitada
* rollback razonable

## Componentes mínimos por entorno serio

* app API
* PostgreSQL
* Redis
* worker(s)
* object storage si hay archivos
* stack de logs/métricas/traces

## CI/CD mínimo

Pipeline sugerido:

1. lint
2. tests
3. build image
4. migraciones controladas
5. deploy a staging
6. smoke tests
7. promote a production

## Variables de entorno mínimas

* `APP_ENV`
* `DATABASE_URL`
* `REDIS_URL`
* `SECRET_KEY`
* `LLM_PROVIDER`
* `LLM_API_KEY`
* `EMBEDDING_PROVIDER`
* `CHANNEL_WEBHOOK_SECRET`
* `OTEL_EXPORTER_ENDPOINT`

## Backups y recuperación

* backups automáticos de BD
* retención definida
* restauración ensayada
* política de recuperación documentada

## Criterios para introducir más complejidad

Solo agregar componentes como event backbone formal, cluster avanzado o servicios separados si existe:

* necesidad real de throughput
* aislamiento de workloads
* resiliencia requerida por negocio
* equipo capaz de operarlo

---

# docs/annexes/99_master_docs_pack.md

## Propósito

Archivo consolidado del pack documental. Sirve como referencia rápida, exportación o contexto único para sesiones de diseño asistidas por IA.

## Uso recomendado

* copiar secciones relevantes a un prompt de trabajo
* revisar consistencia entre documentos
* bootstrap de nuevos miembros del proyecto

## Regla

Este archivo no reemplaza a los documentos fuente. Solo los agrupa.

---

# docs/specs/README.md

La carpeta `specs/` contiene especificaciones detalladas por módulo o funcionalidad.
Cada spec debe tener:

* propósito
* alcance
* dependencias
* entidades implicadas
* flujos
* errores esperados
* observabilidad
* criterios de aceptación

## Specs iniciales sugeridas

* `spec_auth_and_identity.md`
* `spec_contacts_and_sessions.md`
* `spec_channel_ingestion.md`
* `spec_workflow_runtime.md`
* `spec_tool_registry_and_invocation.md`
* `spec_review_queue.md`
* `spec_knowledge_ingestion_and_retrieval.md`
* `spec_analytics_and_events.md`

---

# docs/specs/spec_auth_and_identity.md

## Propósito

Gestionar autenticación, organizaciones, membresías y permisos.

## Alcance

* login/logout
* sesión interna
* perfil actual
* organizations
* memberships
* roles

## Criterios

* solo usuarios válidos acceden
* toda operación queda asociada a una organization activa
* roles restringen módulos

---

# docs/specs/spec_contacts_and_sessions.md

## Propósito

Definir contactos externos, identidades por canal, sesiones y mensajes.

## Flujos

* crear contacto
* vincular identidad externa
* abrir sesión
* persistir mensaje entrante/saliente
* resumir sesión

## Criterios

* no duplicar identidades por canal
* mantener coherencia entre sesión y contacto

---

# docs/specs/spec_channel_ingestion.md

## Propósito

Normalizar entrada de canales externos.

## Flujos

* recibir webhook
* validar firma
* normalizar payload
* persistir evento
* despachar procesamiento

---

# docs/specs/spec_workflow_runtime.md

## Propósito

Implementar el motor de ejecuciones.

## Criterios

* step tracing
* checkpointing
* retries seguros
* approval gates
* finalización confiable

---

# docs/specs/spec_tool_registry_and_invocation.md

## Propósito

Gestionar definición y ejecución de tools.

## Criterios

* tool registrada
* input validado
* output persistido
* audit log generado
* errores tipificados

---

# docs/specs/spec_review_queue.md

## Propósito

Gestionar revisión humana.

## Flujos

* crear review item
* asignar
* aprobar/rechazar
* takeover
* resolver

---

# docs/specs/spec_knowledge_ingestion_and_retrieval.md

## Propósito

Gestionar knowledge base, documentos, chunking y retrieval.

## Criterios

* documentos versionables
* chunks trazables a fuente
* retrieval auditable

---

# docs/specs/spec_analytics_and_events.md

## Propósito

Definir eventos del sistema y métricas derivadas.

## Criterios

* eventos consistentes
* correlación por execution/session
* costos y outcomes medibles

---

# docs/adrs/README.md

Los ADRs documentan decisiones de arquitectura con formato estable.

Formato sugerido:

* título
* estado
* contexto
* decisión
* consecuencias

## ADRs iniciales

* `ADR-001-monolith-modular.md`
* `ADR-002-postgresql-as-source-of-truth.md`
* `ADR-003-pgvector-initial-retrieval.md`
* `ADR-004-workflow-engine-with-checkpoints.md`
* `ADR-005-controlled-tool-execution.md`
* `ADR-006-human-in-the-loop.md`
* `ADR-007-multi-tenancy-first.md`

---

# docs/adrs/ADR-001-monolith-modular.md

## Estado

Aprobado.

## Contexto

Se requiere velocidad de ejecución sin perder estructura.

## Decisión

Comenzar con monolito modular.

## Consecuencias

Menor complejidad operativa y mejor foco inicial.

---

# docs/adrs/ADR-002-postgresql-as-source-of-truth.md

## Estado

Aprobado.

## Decisión

PostgreSQL será la fuente principal de verdad operacional.

---

# docs/adrs/ADR-003-pgvector-initial-retrieval.md

## Estado

Aprobado.

## Decisión

Usar `pgvector` para retrieval inicial antes de introducir un motor vectorial separado.

---

# docs/adrs/ADR-004-workflow-engine-with-checkpoints.md

## Estado

Aprobado.

## Decisión

El core operativo usará un workflow engine con checkpointing persistente.

---

# docs/adrs/ADR-005-controlled-tool-execution.md

## Estado

Aprobado.

## Decisión

Toda tool debe estar registrada y gobernada por policy.

---

# docs/adrs/ADR-006-human-in-the-loop.md

## Estado

Aprobado.

## Decisión

Las acciones de alto riesgo tendrán intervención o aprobación humana.

---

# docs/adrs/ADR-007-multi-tenancy-first.md

## Estado

Aprobado.

## Decisión

Multi-tenancy desde diseño, no como parche posterior.

---

# docs/diagrams/README.md

La carpeta `diagrams/` almacena diagramas textuales o exportables.

## Diagramas iniciales recomendados

* `system_context.md`
* `module_map.md`
* `message_to_execution_sequence.md`
* `workflow_lifecycle.md`
* `review_and_approval_flow.md`
* `tenant_isolation_model.md`

---

# docs/diagrams/system_context.md

```text
User/Customer -> Channel -> API Layer -> Workflow Runtime -> Tools/Knowledge/Review -> Response
                                      -> Analytics/Logs/Audit
```

---

# docs/diagrams/module_map.md

```text
identity
channels
contacts
conversations
knowledge
workflows
tools
agents
review
analytics
billing
platform
```

---

# docs/diagrams/message_to_execution_sequence.md

```text
Incoming Message
  -> Webhook Validation
  -> Normalize Payload
  -> Find/Create Contact
  -> Find/Create Session
  -> Persist Message
  -> Route Intent
  -> Build Context
  -> Start/Resume Execution
  -> Validate Risk
  -> Run Tool or Reply
  -> Persist Outcome
  -> Send Response
```

---

# docs/diagrams/workflow_lifecycle.md

```text
created -> queued -> running -> waiting_input/waiting_approval/waiting_external -> completed/failed/cancelled
```

---

# docs/diagrams/review_and_approval_flow.md

```text
Execution detects high-risk action
  -> Create Approval/Review Item
  -> Assign Reviewer
  -> Approve or Reject
  -> Resume Execution or Cancel Path
```

---

# docs/diagrams/tenant_isolation_model.md

```text
Organization
  -> Users/Memberships
  -> Contacts/Sessions/Messages
  -> Workflows/Executions
  -> Knowledge Base/Documents
  -> Tool Invocations/Audit Logs
```

---

# docs/prompts/README.md

La carpeta `prompts/` contiene prompts reutilizables para trabajar con IA sin perder coherencia arquitectónica.

## Reglas

Todo prompt debe referenciar:

* módulo objetivo
* documentos fuente usados
* invariantes a respetar
* output esperado

## Prompts base sugeridos

* `prompt_generate_backend_module.md`
* `prompt_review_architecture_consistency.md`
* `prompt_design_database_migration.md`
* `prompt_create_workflow_definition.md`
* `prompt_generate_tool_contract.md`
* `prompt_security_review.md`
* `prompt_eval_test_cases.md`

---

# docs/prompts/prompt_generate_backend_module.md

## Uso

Diseñar o implementar un módulo backend sin romper arquitectura.

## Prompt

"Basado en `01_PRODUCT_VISION.md`, `02_MASTER_STATE.md`, `03_SYSTEM_INVARIANTS.md` y `04_ARCHITECTURE_AND_MODULE_MAP.md`, diseña el módulo [NOMBRE] en Python. Incluye responsabilidades, entidades, casos de uso, estructura de carpetas, servicios, repositorios, endpoints y tests mínimos. No rompas multi-tenancy, auditabilidad ni control de tools."

---

# docs/prompts/prompt_review_architecture_consistency.md

## Prompt

"Revisa esta propuesta contra `03_SYSTEM_INVARIANTS.md`, `04_ARCHITECTURE_AND_MODULE_MAP.md` y `11_DECISION_LOG.md`. Señala contradicciones, riesgos, deuda técnica y cambios necesarios para mantener coherencia."

---

# docs/prompts/prompt_design_database_migration.md

## Prompt

"Basado en `05_DOMAIN_MODEL.md` y `14_DATABASE_SCHEMA.md`, genera una migración SQL/Alembic para [CAMBIO]. Incluye índices, constraints, backward compatibility y notas de rollout."

---

# docs/prompts/prompt_create_workflow_definition.md

## Prompt

"Basado en `06_WORKFLOW_ENGINE_SPEC.md` y `12_PILOT_EXECUTION_PLAN.md`, diseña la definición de workflow para [CASO]. Devuelve trigger, steps, edges, inputs, outputs, riesgos, approvals y métricas."

---

# docs/prompts/prompt_generate_tool_contract.md

## Prompt

"Basado en `07_TOOLING_AND_AGENT_POLICY.md`, define una nueva tool llamada [NOMBRE]. Incluye propósito, input schema, output schema, risk level, side effects, idempotency, observabilidad y tests mínimos."

---

# docs/prompts/prompt_security_review.md

## Prompt

"Revisa este módulo usando `08_SECURITY_AND_MULTI_TENANCY.md`. Identifica riesgos de tenant leakage, permisos, secrets handling, logging sensible, idempotencia y approval gaps."

---

# docs/prompts/prompt_eval_test_cases.md

## Prompt

"Basado en `09_OBSERVABILITY_AND_EVALS.md`, genera una suite de casos de evaluación para el workflow [NOMBRE], incluyendo happy path, ambigüedad, fallo externo, policy violation y action de alto riesgo."

---

# Cierre

Este pack es la base documental completa inicial. Debe dividirse luego en archivos individuales dentro de la carpeta `docs/` y mantenerse vivo conforme avance el proyecto.
