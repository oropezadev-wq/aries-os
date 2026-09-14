# 20_EVENT_AND_CONTRACT_PATTERNS.md

## Propósito
Definir cómo se comunican los módulos del sistema y cómo se estructuran los datos intercambiados.

---

## Evento base

Todos los eventos del sistema deben seguir este formato:

```json
{
  "event_name": "string",
  "organization_id": "uuid",
  "timestamp": "datetime",
  "payload": {}
}
```

---

## Eventos principales

- message.received
- message.sent
- execution.started
- execution.completed
- execution.failed
- tool.invoked
- tool.completed
- tool.failed
- approval.requested
- approval.resolved
- review.created
- review.resolved

---

## Contrato de Tool

### Input

```json
{
  "tool_name": "string",
  "input": {}
}
```

### Output

```json
{
  "status": "success | failed",
  "data": {},
  "error": {
    "code": "string",
    "message": "string"
  }
}
```

---

## Contrato de API (Error)

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

---

## Contrato de Workflow Step Result

```json
{
  "step_key": "string",
  "status": "success | failed | waiting",
  "output": {},
  "error": {}
}
```

---

## Reglas generales

- Todo evento debe incluir `organization_id`
- Todo contrato debe tener estructura explícita
- Todo error debe ser estructurado
- Todos los eventos deben ser auditables
- No usar texto libre como contrato principal
- No permitir ambigüedad en tipos

---

## Idempotencia

Operaciones críticas:

- creación de citas
- envío de mensajes
- ejecución de tools
- creación de tickets

Uso:

```json
{
  "idempotency_key": "string"
}
```

---

## Versionado

- contratos versionables
- cambios breaking deben:
  - documentarse
  - registrarse en `11_DECISION_LOG.md`
  - tener estrategia de transición

---

## Eventos vs comandos

Evento:
- describe algo que ya ocurrió

Comando:
- solicita una acción

Ejemplo:

Evento:
- message.received

Comando:
- send_message
