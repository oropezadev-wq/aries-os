# Decision Log

---

## Formato de registro

Cada decisión debe registrar los siguientes campos:

| Campo | Descripción |
|---|---|
| **ID** | Identificador único de la decisión |
| **Fecha** | Fecha de aprobación o registro |
| **Estado** | Estado actual (`aprobado`, `en revisión`, `rechazado`) |
| **Contexto** | Situación que motivó la decisión |
| **Decisión** | Resolución adoptada |
| **Alternativas consideradas** | Opciones evaluadas y descartadas |
| **Consecuencias** | Impacto esperado de la decisión |

---

## Decisiones registradas

---

### D-001

**Fecha:** Por definir
**Estado:** Aprobado

**Contexto:** Se requiere una base sólida y escalable sin incurrir en sobreingeniería en las etapas tempranas del producto.

**Decisión:** Iniciar con monolito modular en lugar de microservicios completos.

**Alternativas consideradas:**
- Microservicios desde el día 1
- Arquitectura serverless fragmentada

**Consecuencias:** Mayor simplicidad operativa, menor costo inicial y evolución gradual hacia una arquitectura distribuida cuando el volumen lo justifique.

---

### D-002

**Fecha:** Por definir
**Estado:** Aprobado

**Contexto:** El producto requiere confianza operacional y diferenciación sostenible en el mercado.

**Decisión:** Construir una plataforma verticalizada de agentes operativos, en lugar de un asistente generalista.

**Alternativas consideradas:**
- Asistente de propósito general

**Consecuencias:** Mayor foco comercial y construcción de ventaja competitiva (moat) por nicho de mercado.

---

### D-003

**Fecha:** Por definir
**Estado:** Aprobado

**Contexto:** Se necesita una base de datos operacional confiable, con soporte robusto para multi-tenancy y transacciones.

**Decisión:** Usar PostgreSQL como base de datos operacional principal.

**Alternativas consideradas:** No documentadas en esta versión.

**Consecuencias:** Consistencia, madurez operativa y compatibilidad con pgvector para retrieval semántico.

---

### D-004

**Fecha:** Por definir
**Estado:** Aprobado

**Contexto:** El sistema requiere capacidades de retrieval semántico desde etapas tempranas sin introducir complejidad operativa adicional.

**Decisión:** Usar pgvector para retrieval inicial en lugar de incorporar una vector DB separada desde el inicio.

**Alternativas consideradas:**
- Base de datos vectorial dedicada (Pinecone, Weaviate, etc.)

**Consecuencias:** Menor complejidad de infraestructura en la Fase 1; migración posible en fases posteriores si el volumen lo exige.

---

### D-005

**Fecha:** Por definir
**Estado:** Aprobado

**Contexto:** El sistema ejecuta acciones con efecto real sobre clientes, agendas y datos sensibles.

**Decisión:** Toda acción de alto riesgo tendrá approval gate o validación reforzada antes de ejecutarse.

**Alternativas consideradas:**
- Ejecución automática con revisión posterior

**Consecuencias:** Mayor seguridad operativa y confianza del usuario comprador; posible latencia adicional en flujos críticos.

---

### D-006

**Fecha:** Por definir
**Estado:** Aprobado

**Contexto:** El sistema es multi-tenant desde el diseño y el aislamiento de datos entre organizaciones es un invariante del sistema.

**Decisión:** Toda entidad operacional crítica debe incluir el campo `organization_id`.

**Alternativas consideradas:**
- Aislamiento por schema de base de datos

**Consecuencias:** Aislamiento garantizado por diseño; simplicidad en consultas con filtro obligatorio por tenant.

---

### D-007

**Fecha:** Por definir
**Estado:** Aprobado

**Contexto:** La lógica específica de cada vertical puede contaminar los módulos core si no existe separación explícita.

**Decisión:** Separar explícitamente los modules core de la lógica vertical en la arquitectura del sistema.

**Alternativas consideradas:**
- Lógica vertical embebida directamente en módulos core

**Consecuencias:** Mayor mantenibilidad, posibilidad de incorporar nuevos verticales sin afectar el núcleo del sistema.