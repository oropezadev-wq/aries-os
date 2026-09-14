# Especificación del Workflow Engine

---

## Propósito

Definir cómo se modelan, ejecutan, pausan, reanudan, validan y observan los workflows del sistema.

---

## Objetivos del engine

- Ejecución determinística con puntos de decisión controlados
- Soporte para tools y pasos automáticos
- Checkpoints persistentes
- Pausas por aprobación humana
- Reintentos seguros
- Inspección completa por parte del operador

---

## Conceptos

### `Workflow`

Definición lógica versionada de un proceso operativo.

### `Step`

Unidad ejecutable o evaluable dentro de un workflow. Tipos posibles:

| Tipo | Descripción |
|---|---|
| `message_response` | Envío de un mensaje al contacto |
| `collect_input` | Recolección de datos del contacto |
| `run_tool` | Ejecución de una tool registrada |
| `decision` | Punto de decisión condicional |
| `wait_for_event` | Espera de un evento externo |
| `handoff` | Derivación a operador humano |
| `approval_gate` | Punto de aprobación obligatoria |
| `end` | Finalización del workflow |

### `Edge`

Transición condicionada entre pasos de un workflow.

### `Execution`

Instancia activa o finalizada de un workflow.

### `Checkpoint`

Estado persistido que permite la reanudación segura de una execution.

---

## Estados de ejecución

| Estado | Descripción |
|---|---|
| `created` | Execution creada, aún no iniciada |
| `queued` | En cola para procesamiento |
| `running` | En ejecución activa |
| `waiting_input` | Esperando entrada del contacto |
| `waiting_approval` | Esperando aprobación humana |
| `waiting_external` | Esperando respuesta de sistema externo |
| `completed` | Finalizada exitosamente |
| `failed` | Finalizada con error |
| `cancelled` | Cancelada por operador o sistema |
| `expired` | Expirada por timeout |

---

## Ciclo de vida de una execution

1. Se crea la execution
2. Se resuelve la versión del workflow
3. Se inicializa el contexto
4. Se entra al primer step
5. Se ejecutan los steps según los edges definidos
6. Se persiste el resultado y el checkpoint por cada step
7. Se finaliza la execution o se pausa hasta nueva entrada

---

## Reglas de ejecución

- Cada step debe ser idempotente o declarar explícitamente su estrategia de idempotencia.
- Ningún step con efecto lateral puede ejecutarse sin validación previa.
- Todo step produce un `step_result` estructurado.
- Todo error produce un `execution_failure` persistido.

---

## Checkpoint mínimo

Cada checkpoint debe guardar los siguientes campos:

| Campo | Descripción |
|---|---|
| `execution_id` | Identificador de la execution |
| `workflow_version_id` | Versión del workflow en ejecución |
| `current_step_key` | Step actualmente en curso |
| `resolved_context` | Contexto resuelto hasta ese punto |
| `pending_inputs` | Entradas pendientes de recolectar |
| `pending_approval_id` | Approval pendiente, si aplica |
| `retry_count` | Número de reintentos realizados |
| `last_transition_at` | Timestamp de la última transición |
| `last_error` | Último error registrado, si aplica |

---

## Política de reintentos

### Reintentos automáticos permitidos en:

- Timeouts transitorios
- Fallas temporales de red
- Rate limits de sistemas externos

### No reintentar automáticamente en:

- Validación de negocio fallida
- Tool no autorizada
- Aprobación rechazada
- Schema de entrada inválido

---

## Approval gates

Un workflow puede declarar approval gates en cualquier step cuando:

- El riesgo de la acción es alto
- Existe efecto económico
- Hay impacto reputacional
- La acción es irreversible

---

## Human handoff

Cuando un workflow entra en modo handoff:

1. Se crea un `review_item` en la cola de revisión
2. Se genera un resumen del contexto para el operador humano
3. Se congela toda acción automática sensible
4. Se puede proponer una respuesta sugerida al operador

---

## Definición base de un workflow

Todo workflow debe incluir:

- `metadata` — información descriptiva del workflow
- `versión` — número de versión
- `trigger` — condición de activación
- `inputs` — campos requeridos para iniciar
- `steps` — pasos del proceso
- `edges` — transiciones entre pasos
- `policies` — políticas de comportamiento
- `allowed_tools` — tools autorizadas para este workflow
- `timeout_policy` — política de expiración
- `retry_policy` — política de reintentos

---

## Ejemplo conceptual

**Workflow:** `appointment_booking`

**Steps:**

1. `classify_intent` — Clasificación de la intención del contacto
2. `collect_required_fields` — Recolección de datos necesarios
3. `search_available_slots` — Búsqueda de horarios disponibles
4. `propose_slots` — Propuesta de opciones al contacto
5. `confirm_selection` — Confirmación de la selección
6. `create_appointment` — Creación del registro de la cita
7. `send_confirmation` — Envío de confirmación al contacto
8. `end` — Fin del workflow

---

## Criterios de engine listo para producción

- Trazabilidad completa por step
- Replay controlado de executions
- Inspección manual por operador
- Métricas por workflow
- Bloqueo seguro ante riesgo detectado
- Compatibilidad entre versiones de workflow