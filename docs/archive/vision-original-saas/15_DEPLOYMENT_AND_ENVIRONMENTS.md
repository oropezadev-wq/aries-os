## Propósito
Definir cómo se despliega el sistema y cómo se organizan los entornos.

---

## Entornos

### local
Entorno de desarrollo individual.

### dev
Entorno compartido para desarrollo.

### staging
Preproducción con configuración similar a producción.

### production
Entorno real para tenants.

---

## Principios de despliegue

- infraestructura reproducible
- configuración separada por entorno
- migraciones controladas
- observabilidad habilitada
- capacidad de rollback

---

## Componentes mínimos

Cada entorno serio debe tener:

- API (FastAPI)
- Base de datos (PostgreSQL)
- Cache (Redis)
- Workers
- Object storage (si aplica)
- Sistema de logs, métricas y trazas

---

## CI/CD mínimo

Pipeline sugerido:

1. lint
2. tests
3. build de imagen
4. migraciones controladas
5. deploy a staging
6. pruebas básicas (smoke tests)
7. promoción a producción

---

## Variables de entorno

Variables mínimas:

- APP_ENV
- DATABASE_URL
- REDIS_URL
- SECRET_KEY
- LLM_PROVIDER
- LLM_API_KEY
- EMBEDDING_PROVIDER
- CHANNEL_WEBHOOK_SECRET
- OTEL_EXPORTER_ENDPOINT

---

## Backups y recuperación

- backups automáticos de base de datos
- política de retención definida
- pruebas de restauración periódicas
- documentación del proceso de recuperación

---

## Escalabilidad

Solo introducir mayor complejidad cuando exista:

- alta carga real
- necesidad de separación de servicios
- requisitos de resiliencia
- equipo capaz de operar la infraestructura

---

## Reglas

- no desplegar cambios sin migraciones controladas
- no modificar producción sin trazabilidad
- todo cambio debe ser auditable
- evitar configuraciones manuales fuera del código