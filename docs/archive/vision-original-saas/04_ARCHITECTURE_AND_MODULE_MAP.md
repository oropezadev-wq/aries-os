# Arquitectura y Mapa de Módulos

---

## Visión arquitectónica

Aries se diseña como una plataforma modular con núcleo monolítico evolutivo, preparada para event-driven execution y separación gradual de workloads.

---

## Estilo arquitectónico inicial

- Monolito modular
- APIs HTTP para entrada de mensajes y panel operativo
- Workers asincrónicos para procesamiento pesado
- Event backbone desacoplado a partir de la Fase 2/3

---

## Módulos core

### 1. `identity`

Responsable de:

- Usuarios (`users`)
- Organizaciones (`organizations`)
- Membresías (`memberships`)
- Roles
- Sesiones internas
- API keys

### 2. `channels`

Responsable de:

- Webhooks
- Recepción y envío de mensajes
- Normalización de payloads por canal
- Rate limiting de canal
- Mapping canal → contacto → sesión

### 3. `contacts`

Responsable de:

- Contactos externos
- Identidades por canal
- Metadata del contacto
- Valor comercial y atributos persistentes

### 4. `conversations`

Responsable de:

- Sesiones
- Mensajes
- Resúmenes de conversación
- Tags de interacción

### 5. `knowledge`

Responsable de:

- Knowledge bases por tenant
- Documentos
- Chunks
- Embeddings
- Retrieval logs

### 6. `workflows`

Responsable de:

- Definición de workflows
- Steps y edges
- Versiones
- Ejecución
- Checkpoints
- Errores
- Aprobaciones

### 7. `tools`

Responsable de:

- Registro de tools
- Permisos de tools
- Políticas de riesgo
- Invocaciones y resultados
- Límites de uso

### 8. `agents`

Responsable de:

- Router
- Context builder
- Planner
- Validator
- Handoff summarizer

### 9. `review`

Responsable de:

- Review queue
- Aprobaciones
- Takeover humano
- Notas internas
- Asignaciones

### 10. `analytics`

Responsable de:

- Eventos
- Métricas operativas
- Costos
- KPIs de negocio
- Eval runs

### 11. `billing`

Responsable de:

- Planes
- Límites
- Suscripciones
- Uso
- Facturación futura

### 12. `platform`

Responsable de:

- Feature flags
- Configuraciones globales
- Health checks
- Environment config
- Administración interna

---

## Relaciones entre módulos

- `channels` crea entradas hacia `conversations`.
- `conversations` alimenta a `agents` y `workflows`.
- `agents` consulta `knowledge`, `contacts`, `conversations` y `tools`.
- `workflows` coordina `tools`, `review` y `analytics`.
- `review` puede pausar o modificar `workflows`.
- `analytics` observa a todos los módulos.

---

## Flujo principal de alto nivel

1. Entra un mensaje al sistema
2. Se normaliza el payload
3. Se crea o vincula una sesión
4. Se persiste el mensaje
5. Se activa el router
6. Se construye el contexto
7. Se selecciona respuesta, workflow o tool
8. Se valida el riesgo
9. Se ejecuta la acción o se deriva a un humano
10. Se registra el outcome

---

## Límites arquitectónicos

- `agents` no persiste directamente fuera de sus puertos definidos.
- `channels` no decide lógica de negocio.
- `tools` no contiene política de producto; ejecuta bajo política externa.
- `knowledge` no altera el estado operacional.
- `analytics` no modifica workflows, salvo por mecanismos explícitos y aprobados.

---

## Estrategia de evolución

### v1 — Monolito modular con workers

Arquitectura inicial: monolito modular con workers asincrónicos para procesamiento pesado.

### v2 — Extracción de componentes calientes

Separación progresiva de:

- Workers de canal
- Retrieval jobs
- Execution workers
- Analytics pipelines

### v3 — Bus de eventos formal

Bus de eventos formal y separación de bounded contexts si el volumen lo exige.