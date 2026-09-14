# Propósito

Esta carpeta contiene la documentación fuente de verdad del proyecto Aries. Su objetivo es alinear producto, arquitectura, operación, seguridad y ejecución técnica para que humanos e IA trabajen sobre un marco coherente.

---

## Orden de lectura recomendado

1. `01_PRODUCT_VISION.md`
2. `02_MASTER_STATE.md`
3. `03_SYSTEM_INVARIANTS.md`
4. `04_ARCHITECTURE_AND_MODULE_MAP.md`
5. `05_DOMAIN_MODEL.md`
6. `06_WORKFLOW_ENGINE_SPEC.md`
7. `07_TOOLING_AND_AGENT_POLICY.md`
8. `08_SECURITY_AND_MULTI_TENANCY.md`
9. `09_OBSERVABILITY_AND_EVALS.md`
10. `10_ROADMAP_MASTER.md`
11. `11_DECISION_LOG.md`
12. `12_PILOT_EXECUTION_PLAN.md`
13. `13_API_CONTRACTS.md`
14. `14_DATABASE_SCHEMA.md`
15. `15_DEPLOYMENT_AND_ENVIRONMENTS.md`

---

## Jerarquía documental

En caso de conflicto entre documentos, prevalece el siguiente orden de autoridad:

1. `03_SYSTEM_INVARIANTS.md`
2. `11_DECISION_LOG.md`
3. `02_MASTER_STATE.md`
4. `04_ARCHITECTURE_AND_MODULE_MAP.md`
5. `10_ROADMAP_MASTER.md`
6. Documentos restantes

---

## Reglas de uso con IA

- No solicitar código sin antes fijar contexto con la visión de producto, el estado maestro y los invariantes del sistema.
- Toda propuesta nueva debe validarse contra los invariantes y el decision log.
- Ningún documento debe contradecir explícitamente un ADR o una decisión ya aprobada.
- Toda pieza generada por IA debe indicar el módulo afectado, los supuestos asumidos y los riesgos identificados.
- Si una tarea implica cambios en arquitectura, seguridad, multi-tenancy o contratos de API, debe registrarse primero en `11_DECISION_LOG.md`.

---

## Convenciones

- Todo identificador técnico utiliza inglés consistente.
- Toda descripción funcional puede redactarse en español.
- Todas las entidades multi-tenant deben incluir el campo `organization_id`.
- Todo componente crítico debe contar con métricas, logs y trazabilidad.

---

## Objetivo operativo de esta carpeta

Esta carpeta existe para evitar:

- Arquitectura incoherente entre módulos
- Decisiones reabiertas sin control ni registro
- Prompts ambiguos o sin contexto suficiente
- Duplicidad de lógica entre componentes
- Deuda técnica por improvisación
- Diseño genérico sin verticalización al dominio del negocio