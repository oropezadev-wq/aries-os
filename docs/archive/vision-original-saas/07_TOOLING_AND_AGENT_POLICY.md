# Política de Tooling y Agentes

---

## Propósito

Definir cómo funcionan los agentes del sistema y bajo qué reglas utilizan tools.

---

## Política general

Los agentes no son actores soberanos. Son componentes de decisión asistida dentro de un runtime controlado.

---

## Roles de agentes

### `Router Agent`

Clasifica la intención del contacto y enruta hacia el workflow o respuesta correspondiente.

### `Context Builder Agent`

Construye el contexto relevante para el caso en curso, combinando historial, memoria y datos del dominio.

### `Planner Agent`

Decide la siguiente acción dentro del marco de opciones permitidas por el workflow y la policy activa.

### `Validator Agent`

Verifica formato, coherencia, cumplimiento de policy y nivel de riesgo antes de ejecutar una acción.

### `Handoff Summarizer Agent`

Prepara un contexto claro y estructurado para la revisión humana cuando se produce un handoff.

---

## Política de agentes

- Un agente no puede ejecutar código arbitrario.
- Un agente solo opera dentro del scope del caso actual.
- Un agente solo puede usar tools permitidas por la policy y el workflow activo.
- Toda llamada a una tool debe quedar registrada.
- Un agente no puede cambiar permisos ni políticas del sistema.

---

## Definición de tool

Una tool es una capacidad ejecutable versionada, con contrato explícito y política de riesgo asociada.

---

## Metadatos mínimos de una tool

| Campo | Descripción |
|---|---|
| `name` | Nombre canónico de la tool |
| `version` | Versión de la tool |
| `category` | Categoría funcional |
| `description` | Descripción del propósito |
| `input_schema` | Schema de entrada |
| `output_schema` | Schema de salida |
| `risk_level` | Nivel de riesgo asignado |
| `side_effect_level` | Nivel de efecto lateral |
| `requires_approval` | Indica si requiere aprobación humana |
| `allowed_roles` | Roles autorizados para invocarla |
| `timeout_ms` | Tiempo máximo de ejecución en milisegundos |
| `idempotent` | Indica si la tool es idempotente |

---

## Categorías de tools

### System tools
Operaciones internas del sistema:
- `send_message`
- `create_note`
- `tag_contact`
- `create_task`

### Domain tools
Operaciones específicas del vertical de negocio:
- `find_available_slot`
- `register_patient`
- `create_property_visit`
- `calculate_quote`

### Integration tools
Integraciones con sistemas externos:
- `google_calendar_create_event`
- `crm_upsert_contact`
- `sheets_append_row`
- `payment_link_create`

### Analytics tools
Herramientas de análisis operativo:
- `generate_daily_summary`
- `detect_drop_off_pattern`

---

## Política de riesgo

| Nivel | Descripción |
|---|---|
| **Bajo** | Lectura o acción reversible sin impacto externo significativo |
| **Medio** | Acción externa limitada o actualización no crítica |
| **Alto** | Acción con efecto operativo directo sobre el cliente o la agenda |
| **Crítico** | Cobros, compromisos sensibles, cambios irreversibles o datos altamente sensibles |

### Reglas de ejecución por nivel de riesgo

- **Bajo:** Ejecución automática con logging.
- **Medio:** Ejecución automática con validación estricta.
- **Alto:** Puede requerir approval gate según la policy del tenant.
- **Crítico:** Aprobación humana obligatoria, salvo regla explícita y auditada.

---

## Política de selección de tools

La selección de tools para cada acción se basa en:

- Workflow activo
- Policy del tenant
- Rol del agente o usuario
- Contexto disponible en la sesión
- Nivel de riesgo de la acción
- Disponibilidad de la integración

---

## Prohibiciones explícitas

- Tool chaining libre sin límites de alcance o profundidad
- Ejecución de SQL arbitrario desde agentes
- Acceso a credenciales desde prompts
- Tool discovery no controlado en runtime productivo

---

## Criterios para aprobar una nueva tool

Para que una nueva tool pueda incorporarse al sistema, debe cumplir:

1. Contrato de entrada y salida definido
2. Política de riesgo asignada
3. Owner responsable identificado
4. Tests mínimos implementados
5. Observabilidad mínima garantizada
6. Estrategia de rollback o compensación, cuando aplique