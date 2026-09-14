# 21_FRONTEND_AND_OPERATOR_FLOWS.md

## Propósito
Definir cómo interactúan los operadores humanos con el sistema a través del frontend.

---

## Vistas principales

### Inbox / Sessions
- Lista de sesiones activas
- Filtros por estado (active, waiting_approval, etc.)
- Vista de conversación

### Execution View
- Estado del workflow
- Step actual
- Historial de steps

### Review Queue
- Lista de tareas pendientes
- Aprobaciones
- Rechazos

### Contacts
- Información del cliente
- Historial

### Analytics Dashboard
- KPIs
- métricas operativas

---

## Flujos principales

### Flujo operador básico
1. Ver sesión en inbox
2. Abrir conversación
3. Leer contexto
4. Tomar acción (responder / aprobar / takeover)

### Flujo de aprobación
1. Ver ReviewItem
2. Analizar contexto
3. Aprobar o rechazar
4. Execution continúa

### Flujo takeover
1. Operador toma control
2. IA se pausa
3. Operador responde manualmente
4. Se registra acción

---

## Estados UI

- loading
- empty
- error
- active
- waiting_approval
- completed

---

## Reglas

- UI refleja estado real del backend
- No permitir acciones inválidas
- Mostrar contexto completo antes de decisiones
