# Schema de Base de Datos

---

## Propósito

Documentar el esquema lógico inicial de la base de datos del sistema.

---

## Convenciones

- Primary key (`PK`) de tipo UUID en todas las tablas
- Timestamps en UTC
- `organization_id` obligatorio en todas las tablas tenant-scoped
- Soft delete únicamente donde tenga valor operativo claro
- Índices en claves externas y columnas de filtros frecuentes

---

## Tablas núcleo

---

### `organizations`

| Columna | Descripción |
|---|---|
| `id` | Primary key (UUID) |
| `slug` | Identificador legible por humanos |
| `name` | Nombre de la organización |
| `status` | Estado actual |
| `settings_json` | Configuración del tenant |
| `created_at` | Fecha de creación |
| `updated_at` | Fecha de última actualización |

---

### `users`

| Columna | Descripción |
|---|---|
| `id` | Primary key (UUID) |
| `email` | Correo electrónico |
| `name` | Nombre del usuario |
| `password_hash` | Hash de contraseña |
| `auth_provider` | Proveedor de autenticación |
| `status` | Estado actual |
| `created_at` | Fecha de creación |
| `updated_at` | Fecha de última actualización |

---

### `memberships`

| Columna | Descripción |
|---|---|
| `id` | Primary key (UUID) |
| `organization_id` | Referencia al tenant |
| `user_id` | Referencia al usuario |
| `role` | Rol dentro de la organización |
| `permissions_json` | Permisos específicos |
| `created_at` | Fecha de creación |

---

### `contacts`

| Columna | Descripción |
|---|---|
| `id` | Primary key (UUID) |
| `organization_id` | Referencia al tenant |
| `name` | Nombre del contacto |
| `phone` | Teléfono |
| `email` | Correo electrónico |
| `source` | Canal de origen |
| `lifecycle_stage` | Etapa del ciclo de vida |
| `lead_score` | Puntuación comercial |
| `metadata_json` | Atributos adicionales |
| `created_at` | Fecha de creación |
| `updated_at` | Fecha de última actualización |

---

### `contact_identities`

| Columna | Descripción |
|---|---|
| `id` | Primary key (UUID) |
| `organization_id` | Referencia al tenant |
| `contact_id` | Referencia al contacto |
| `channel` | Canal de comunicación |
| `external_id` | ID externo en el canal |
| `verified` | Indica si está verificado |
| `created_at` | Fecha de creación |

---

### `sessions`

| Columna | Descripción |
|---|---|
| `id` | Primary key (UUID) |
| `organization_id` | Referencia al tenant |
| `contact_id` | Referencia al contacto |
| `channel` | Canal activo |
| `status` | Estado de la sesión |
| `current_execution_id` | Execution en curso, si aplica |
| `last_message_at` | Timestamp del último mensaje |
| `created_at` | Fecha de creación |
| `updated_at` | Fecha de última actualización |

---

### `messages`

| Columna | Descripción |
|---|---|
| `id` | Primary key (UUID) |
| `organization_id` | Referencia al tenant |
| `session_id` | Referencia a la sesión |
| `direction` | Dirección: entrante o saliente |
| `sender_type` | Tipo de remitente |
| `content` | Contenido del mensaje |
| `content_type` | Tipo de contenido |
| `raw_payload_json` | Payload original del canal |
| `created_at` | Fecha de creación |

---

### `workflows`

| Columna | Descripción |
|---|---|
| `id` | Primary key (UUID) |
| `organization_id` | Referencia al tenant |
| `name` | Nombre del workflow |
| `vertical` | Vertical de negocio |
| `status` | Estado actual |
| `current_version_id` | Versión activa actual |
| `created_at` | Fecha de creación |
| `updated_at` | Fecha de última actualización |

---

### `workflow_versions`

| Columna | Descripción |
|---|---|
| `id` | Primary key (UUID) |
| `organization_id` | Referencia al tenant |
| `workflow_id` | Referencia al workflow |
| `version` | Número de versión |
| `definition_json` | Definición completa del workflow |
| `published_at` | Fecha de publicación |

---

### `executions`

| Columna | Descripción |
|---|---|
| `id` | Primary key (UUID) |
| `organization_id` | Referencia al tenant |
| `workflow_id` | Referencia al workflow |
| `workflow_version_id` | Versión del workflow en uso |
| `session_id` | Sesión asociada |
| `status` | Estado actual de la ejecución |
| `current_step_key` | Step actualmente en curso |
| `risk_level` | Nivel de riesgo evaluado |
| `requires_approval` | Indica si requiere aprobación humana |
| `checkpoint_json` | Estado persistido del checkpoint |
| `started_at` | Inicio de ejecución |
| `finished_at` | Fin de ejecución |

---

### `execution_steps`

| Columna | Descripción |
|---|---|
| `id` | Primary key (UUID) |
| `organization_id` | Referencia al tenant |
| `execution_id` | Referencia a la execution |
| `step_key` | Clave del paso |
| `status` | Estado del paso |
| `input_json` | Entrada del paso |
| `output_json` | Salida del paso |
| `started_at` | Inicio de ejecución del paso |
| `finished_at` | Fin de ejecución del paso |

---

### `tools`

| Columna | Descripción |
|---|---|
| `id` | Primary key (UUID) |
| `organization_scope` | Alcance de la tool |
| `name` | Nombre canónico |
| `version` | Versión |
| `category` | Categoría funcional |
| `input_schema_json` | Schema de entrada |
| `output_schema_json` | Schema de salida |
| `risk_level` | Nivel de riesgo asignado |
| `side_effect_level` | Nivel de efecto lateral |
| `active` | Indica si está activa |

---

### `tool_invocations`

| Columna | Descripción |
|---|---|
| `id` | Primary key (UUID) |
| `organization_id` | Referencia al tenant |
| `execution_id` | Execution que originó la invocación |
| `tool_id` | Tool invocada |
| `status` | Estado de la invocación |
| `input_json` | Entrada enviada |
| `output_json` | Salida recibida |
| `idempotency_key` | Clave de idempotencia |
| `duration_ms` | Duración en milisegundos |
| `created_at` | Fecha de creación |

---

### `approvals`

| Columna | Descripción |
|---|---|
| `id` | Primary key (UUID) |
| `organization_id` | Referencia al tenant |
| `execution_id` | Execution que requiere aprobación |
| `status` | Estado de la aprobación |
| `reason` | Motivo de la solicitud |
| `requested_by` | Quién solicitó la aprobación |
| `resolved_by` | Quién la resolvió |
| `created_at` | Fecha de creación |
| `resolved_at` | Fecha de resolución |

---

### `audit_logs`

| Columna | Descripción |
|---|---|
| `id` | Primary key (UUID) |
| `organization_id` | Referencia al tenant |
| `actor_type` | Tipo de actor que realizó la acción |
| `actor_id` | Identificador del actor |
| `action` | Acción realizada |
| `target_type` | Tipo de entidad afectada |
| `target_id` | Identificador de la entidad afectada |
| `details_json` | Detalle adicional de la acción |
| `created_at` | Fecha de creación |

---

### `knowledge_bases`

| Columna | Descripción |
|---|---|
| `id` | Primary key (UUID) |
| `organization_id` | Referencia al tenant |
| `name` | Nombre de la knowledge base |
| `status` | Estado actual |
| `created_at` | Fecha de creación |

---

### `documents`

| Columna | Descripción |
|---|---|
| `id` | Primary key (UUID) |
| `organization_id` | Referencia al tenant |
| `knowledge_base_id` | Referencia a la knowledge base |
| `title` | Título del documento |
| `source_type` | Tipo de fuente |
| `mime_type` | Tipo MIME |
| `version` | Versión del documento |
| `metadata_json` | Metadata adicional |
| `created_at` | Fecha de creación |

---

### `document_chunks`

| Columna | Descripción |
|---|---|
| `id` | Primary key (UUID) |
| `organization_id` | Referencia al tenant |
| `document_id` | Referencia al documento |
| `chunk_index` | Índice del fragmento |
| `content` | Contenido del fragmento |
| `embedding_vector` | Vector de embedding (pgvector) |
| `metadata_json` | Metadata adicional |
| `created_at` | Fecha de creación |

---

### `review_items`

| Columna | Descripción |
|---|---|
| `id` | Primary key (UUID) |
| `organization_id` | Referencia al tenant |
| `execution_id` | Execution asociada |
| `priority` | Prioridad de atención |
| `reason` | Motivo de la revisión |
| `status` | Estado actual |
| `assigned_to` | Operador asignado |
| `created_at` | Fecha de creación |
| `resolved_at` | Fecha de resolución |

---

### `events`

| Columna | Descripción |
|---|---|
| `id` | Primary key (UUID) |
| `organization_id` | Referencia al tenant |
| `event_name` | Nombre del evento |
| `event_type` | Tipo de evento |
| `payload_json` | Payload del evento |
| `emitted_at` | Timestamp de emisión |

---

## Índices sugeridos

| Índice | Propósito |
|---|---|
| `contacts(organization_id, phone)` | Búsqueda de contacto por teléfono dentro del tenant |
| `contact_identities(organization_id, channel, external_id)` | Resolución de identidad entrante por canal |
| `sessions(organization_id, contact_id, status)` | Consulta de sesiones activas por contacto |
| `messages(organization_id, session_id, created_at)` | Historial de mensajes por sesión |
| `executions(organization_id, status, current_step_key)` | Monitoreo de executions activas |
| `tool_invocations(organization_id, tool_id, created_at)` | Auditoría de uso de tools por tenant |
| `review_items(organization_id, status, priority)` | Cola de revisión priorizada por tenant |
| `document_chunks.embedding_vector` | Índice vectorial para retrieval semántico (pgvector) |