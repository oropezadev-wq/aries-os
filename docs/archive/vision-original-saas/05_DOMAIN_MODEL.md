# Modelo de Dominio

---

## Entidades núcleo

---

### `Organization`

Representa un tenant del sistema.

| Atributo | Descripción |
|---|---|
| `id` | Identificador único |
| `slug` | Identificador legible por humanos |
| `name` | Nombre de la organización |
| `status` | Estado actual |
| `created_at` | Fecha de creación |
| `settings_json` | Configuración específica del tenant |

---

### `User`

Usuario interno del sistema.

| Atributo | Descripción |
|---|---|
| `id` | Identificador único |
| `email` | Correo electrónico |
| `name` | Nombre del usuario |
| `auth_provider` | Proveedor de autenticación |
| `status` | Estado actual |

---

### `Membership`

Vincula un `User` con una `Organization`.

| Atributo | Descripción |
|---|---|
| `id` | Identificador único |
| `organization_id` | Referencia a la organización |
| `user_id` | Referencia al usuario |
| `role` | Rol dentro de la organización |
| `permissions_json` | Permisos específicos |

---

### `Contact`

Persona externa que interactúa con la organización.

| Atributo | Descripción |
|---|---|
| `id` | Identificador único |
| `organization_id` | Referencia al tenant |
| `name` | Nombre del contacto |
| `phone` | Teléfono |
| `email` | Correo electrónico |
| `source` | Canal de origen |
| `metadata_json` | Atributos adicionales |
| `lead_score` | Puntuación comercial |
| `lifecycle_stage` | Etapa del ciclo de vida |

---

### `ContactIdentity`

Identificador del contacto por canal.

| Atributo | Descripción |
|---|---|
| `id` | Identificador único |
| `contact_id` | Referencia al contacto |
| `channel` | Canal de comunicación |
| `external_id` | ID externo en el canal |
| `verified` | Indica si está verificado |

---

### `Session`

Unidad conversacional y contextual activa.

| Atributo | Descripción |
|---|---|
| `id` | Identificador único |
| `organization_id` | Referencia al tenant |
| `contact_id` | Referencia al contacto |
| `channel` | Canal activo |
| `status` | Estado de la sesión |
| `current_execution_id` | Execution en curso, si aplica |
| `last_message_at` | Timestamp del último mensaje |

---

### `Message`

Evento textual o multimedia dentro de una sesión.

| Atributo | Descripción |
|---|---|
| `id` | Identificador único |
| `organization_id` | Referencia al tenant |
| `session_id` | Referencia a la sesión |
| `direction` | Dirección: entrante o saliente |
| `sender_type` | Tipo de remitente |
| `content` | Contenido del mensaje |
| `content_type` | Tipo de contenido |
| `raw_payload_json` | Payload original del canal |

---

### `Workflow`

Plantilla lógica de un proceso operativo.

| Atributo | Descripción |
|---|---|
| `id` | Identificador único |
| `organization_id` | Referencia al tenant |
| `name` | Nombre del workflow |
| `vertical` | Vertical de negocio asociada |
| `status` | Estado del workflow |
| `current_version_id` | Versión activa actual |

---

### `WorkflowVersion`

Versión inmutable de un workflow.

| Atributo | Descripción |
|---|---|
| `id` | Identificador único |
| `workflow_id` | Referencia al workflow |
| `version` | Número de versión |
| `definition_json` | Definición completa del workflow |
| `published_at` | Fecha de publicación |

---

### `WorkflowStep`

Paso dentro de una versión de workflow.

| Atributo | Descripción |
|---|---|
| `id` | Identificador único |
| `workflow_version_id` | Referencia a la versión |
| `key` | Clave única del paso |
| `type` | Tipo de paso |
| `config_json` | Configuración del paso |
| `risk_level` | Nivel de riesgo asociado |

---

### `WorkflowEdge`

Transición entre pasos de un workflow.

| Atributo | Descripción |
|---|---|
| `id` | Identificador único |
| `workflow_version_id` | Referencia a la versión |
| `source_step_key` | Paso de origen |
| `target_step_key` | Paso de destino |
| `condition_json` | Condición de transición |

---

### `Execution`

Instancia en ejecución de un workflow.

| Atributo | Descripción |
|---|---|
| `id` | Identificador único |
| `organization_id` | Referencia al tenant |
| `workflow_id` | Referencia al workflow |
| `workflow_version_id` | Versión del workflow en uso |
| `session_id` | Sesión asociada |
| `status` | Estado actual de la ejecución |
| `current_step_key` | Paso actualmente en curso |
| `risk_level` | Nivel de riesgo evaluado |
| `requires_approval` | Indica si requiere aprobación humana |
| `checkpoint_json` | Estado persistido del checkpoint |

---

### `ExecutionStep`

Registro de cada paso ejecutado dentro de una execution.

| Atributo | Descripción |
|---|---|
| `id` | Identificador único |
| `execution_id` | Referencia a la execution |
| `step_key` | Clave del paso |
| `status` | Estado del paso |
| `input_json` | Entrada del paso |
| `output_json` | Salida del paso |
| `started_at` | Inicio de ejecución |
| `finished_at` | Fin de ejecución |

---

### `Tool`

Capacidad ejecutable registrada en el sistema.

| Atributo | Descripción |
|---|---|
| `id` | Identificador único |
| `organization_scope` | Alcance de la tool |
| `name` | Nombre canónico |
| `version` | Versión |
| `category` | Categoría funcional |
| `input_schema_json` | Schema de entrada |
| `output_schema_json` | Schema de salida |
| `side_effect_level` | Nivel de efecto lateral |

---

### `ToolInvocation`

Registro de uso real de una tool.

| Atributo | Descripción |
|---|---|
| `id` | Identificador único |
| `organization_id` | Referencia al tenant |
| `execution_id` | Execution que originó la invocación |
| `tool_id` | Tool invocada |
| `status` | Estado de la invocación |
| `input_json` | Entrada enviada |
| `output_json` | Salida recibida |
| `idempotency_key` | Clave de idempotencia |

---

### `Approval`

Aprobación humana requerida por una execution.

| Atributo | Descripción |
|---|---|
| `id` | Identificador único |
| `organization_id` | Referencia al tenant |
| `execution_id` | Execution que requiere aprobación |
| `status` | Estado de la aprobación |
| `requested_by` | Quién solicitó la aprobación |
| `resolved_by` | Quién la resolvió |
| `reason` | Motivo de la solicitud |

---

### `AuditLog`

Rastro de seguridad y operación del sistema.

| Atributo | Descripción |
|---|---|
| `id` | Identificador único |
| `organization_id` | Referencia al tenant |
| `actor_type` | Tipo de actor que realizó la acción |
| `actor_id` | Identificador del actor |
| `action` | Acción realizada |
| `target_type` | Tipo de entidad afectada |
| `target_id` | Identificador de la entidad afectada |
| `details_json` | Detalle adicional de la acción |

---

### `KnowledgeBase`

Conjunto documental de un tenant.

| Atributo | Descripción |
|---|---|
| `id` | Identificador único |
| `organization_id` | Referencia al tenant |
| `name` | Nombre de la knowledge base |
| `status` | Estado actual |

---

### `Document`

Documento fuente dentro de una knowledge base.

| Atributo | Descripción |
|---|---|
| `id` | Identificador único |
| `knowledge_base_id` | Referencia a la knowledge base |
| `title` | Título del documento |
| `source_type` | Tipo de fuente |
| `mime_type` | Tipo MIME |
| `version` | Versión del documento |

---

### `DocumentChunk`

Fragmento indexado de un documento.

| Atributo | Descripción |
|---|---|
| `id` | Identificador único |
| `document_id` | Referencia al documento |
| `chunk_index` | Índice del fragmento |
| `content` | Contenido del fragmento |
| `embedding_vector` | Vector de embedding |
| `metadata_json` | Metadata adicional |

---

### `ReviewItem`

Trabajo pendiente de revisión humana.

| Atributo | Descripción |
|---|---|
| `id` | Identificador único |
| `organization_id` | Referencia al tenant |
| `execution_id` | Execution asociada |
| `priority` | Prioridad de atención |
| `reason` | Motivo de la revisión |
| `status` | Estado actual |
| `assigned_to` | Operador asignado |

---

### `Event`

Evento analítico o de plataforma.

| Atributo | Descripción |
|---|---|
| `id` | Identificador único |
| `organization_id` | Referencia al tenant |
| `event_name` | Nombre del evento |
| `event_type` | Tipo de evento |
| `payload_json` | Payload del evento |
| `emitted_at` | Timestamp de emisión |

---

## Relaciones principales

| Relación | Cardinalidad |
|---|---|
| `Organization` → `Membership` | 1:N |
| `Organization` → `Contact` | 1:N |
| `Contact` → `Session` | 1:N |
| `Session` → `Message` | 1:N |
| `Workflow` → `WorkflowVersion` | 1:N |
| `WorkflowVersion` → `WorkflowStep` | 1:N |
| `WorkflowVersion` → `WorkflowEdge` | 1:N |
| `Workflow` → `Execution` | 1:N |
| `Execution` → `ExecutionStep` | 1:N |
| `Tool` → `ToolInvocation` | 1:N |
| `Execution` → `ToolInvocation` | 1:N |
| `Execution` → `Approval` | 1:N |
| `Organization` → `AuditLog` | 1:N |
| `KnowledgeBase` → `Document` | 1:N |
| `Document` → `DocumentChunk` | 1:N |