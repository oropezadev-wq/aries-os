# Seguridad y Multi-Tenancy

---

## Propósito

Establecer el modelo de aislamiento, autenticación, autorización y seguridad operativa del sistema.

---

## Principio rector

**Seguridad por defecto y mínimo privilegio.**

---

## Aislamiento por tenant

- Todo dato operacional pertenece a una organización (`organization`).
- Todas las consultas deben filtrar por `organization_id`.
- Las tablas críticas contarán con mecanismos de aislamiento reforzado.
- Ningún proceso puede mezclar datos de dos tenants en un mismo contexto operativo.

---

## Roles internos del sistema

| Rol | Descripción |
|---|---|
| `owner` | Propietario de la organización |
| `admin` | Administrador con acceso completo |
| `operator` | Operador de atención y gestión |
| `reviewer` | Revisor de casos y aprobaciones |
| `analyst` | Analista de datos y métricas |
| `developer_internal` | Desarrollador interno de la plataforma |

---

## Controles de acceso

- RBAC para el panel operativo y las APIs
- Permisos explícitos por módulo
- Scopes definidos por integración
- Separación entre acceso humano e invocación de sistema

---

## Gestión de secretos

- Secretos cifrados en reposo
- Rotación de secretos posible en cualquier momento
- Acceso restringido por servicio
- Nunca registrar en logs tokens, keys ni payloads sensibles completos

---

## Seguridad de tools

- Tool registry con whitelist de tools autorizadas
- Validación de input por schema antes de ejecutar
- Rate limits por tenant y por tool
- Approvals obligatorias según nivel de riesgo
- Idempotency keys para acciones sensibles
- Logs de invocación completos

---

## Seguridad de integraciones

- Credenciales almacenadas por tenant, nunca compartidas
- Scopes mínimos necesarios por integración
- Estado de health monitoreado por integración
- Posibilidad de desactivar una integración comprometida de forma inmediata

---

## Seguridad de datos

### Clasificación sugerida

| Nivel | Descripción |
|---|---|
| **Pública** | Información sin restricción de acceso |
| **Interna** | Información de uso interno del sistema |
| **Sensible operacional** | Datos operativos con acceso controlado |
| **Sensible personal** | Datos personales del contacto o usuario |
| **Crítica** | Datos financieros, credenciales o compromisos irreversibles |

### Reglas para datos sensibles

- Enmascarado en el panel operativo cuando corresponda
- Minimización de datos sensibles en prompts enviados al LLM
- No persistir más información de la estrictamente necesaria
- Reglas de retención definidas por categoría de dato

---

## Eventos de seguridad que deben registrarse

Los siguientes eventos deben quedar registrados en el `audit_log`:

- `login` — inicio de sesión
- `logout` — cierre de sesión
- Cambio de rol de usuario
- Alta o baja de integración
- Fallo repetido de autenticación
- Approval crítica resuelta
- Override humano ejecutado
- Acceso denegado por permisos insuficientes

---

## Gestión de incidentes y respuesta

Ante un incidente de seguridad, el protocolo es:

1. Aislar el tenant o la integración afectada
2. Congelar las actions críticas si corresponde
3. Preservar los logs existentes sin alteraciones
4. Registrar el incidente con detalle
5. Ejecutar el protocolo de comunicación y remediación definido