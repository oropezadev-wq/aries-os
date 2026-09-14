# Contratos de API

---

## Propósito

Definir los contratos mínimos de API para la versión v1 del sistema.

---

## Principios

- Versionado por prefijo de ruta (`/api/v1/`)
- Payloads tipados y validados
- Errores con formato consistente
- Autenticación explícita en todos los endpoints protegidos
- Contratos estables entre versiones

---

## Endpoints base sugeridos

### Auth
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
GET    /api/v1/auth/me

### Organizations
GET    /api/v1/organizations/current
PATCH  /api/v1/organizations/current

### Contacts
GET    /api/v1/contacts
POST   /api/v1/contacts
GET    /api/v1/contacts/{id}
PATCH  /api/v1/contacts/{id}

### Sessions
GET    /api/v1/sessions
GET    /api/v1/sessions/{id}
POST   /api/v1/sessions/{id}/takeover

### Messages
GET    /api/v1/sessions/{id}/messages
POST   /api/v1/messages/send

### Workflows
GET    /api/v1/workflows
POST   /api/v1/workflows
GET    /api/v1/workflows/{id}
POST   /api/v1/workflows/{id}/publish

### Executions
GET    /api/v1/executions
GET    /api/v1/executions/{id}
POST   /api/v1/executions/{id}/resume
POST   /api/v1/executions/{id}/cancel

### Tools
GET    /api/v1/tools
POST   /api/v1/tools/{id}/test
GET    /api/v1/tool-invocations/{id}

### Review
GET    /api/v1/review/items
POST   /api/v1/review/items/{id}/approve
POST   /api/v1/review/items/{id}/reject
POST   /api/v1/review/items/{id}/assign

### Knowledge
GET    /api/v1/knowledge-bases
POST   /api/v1/knowledge-bases
POST   /api/v1/documents/upload
POST   /api/v1/documents/{id}/reindex

---

## Contrato de error base

Toda respuesta de error debe seguir esta estructura:

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

## Reglas

- Toda respuesta debe incluir un `request_id` para trazabilidad.
- Los endpoints sensibles deben registrar entrada en el `audit_log`.
- Las operaciones con side effects deben aceptar `idempotency_key` cuando corresponda.