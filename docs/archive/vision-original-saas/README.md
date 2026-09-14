# Visión original — plataforma SaaS multi-tenant (archivado)

> Carpeta movida tal cual (sin editar ni un solo documento interno) desde
> `documentacion_inicial/` en la raíz del repo, por indicación explícita del
> usuario: *"Ya subí la documentación original del proyecto (la primera
> visión, antes del pivote hacia asistente personal)... archivala en
> docs/archive/vision-original-saas/, manteniendo la estructura de carpetas
> interna tal cual está"*. Mismo criterio que
> `docs/archive/2026-09-12-historial-implementacion.md`: material histórico
> real, no descartado, pero ya no es la fuente de verdad activa del
> proyecto — esa es hoy `docs/VISION.md`.

## Qué es esto

Los ~24 documentos numerados (00 a 24) más `adrs/`, `annexes/`, `diagrams/`,
`prompts/` y `specs/` son la documentación fuente de verdad **original** de
Aries: una plataforma SaaS multi-tenant de agentes operativos verticales
(atención por WhatsApp/web/email, workflows con checkpoints, tool registry
gobernado, human-in-the-loop, multi-tenancy desde el diseño — ver
`01_PRODUCT_VISION.md` y los 7 ADRs en `adrs/`).

Esa visión no se abandonó — se pospuso. El proyecto pivotó primero a
construir un asistente personal de escritorio tipo Jarvis (Kernel, agentes
nativos, Planner, Voice, Routines, Message Bus — todo lo que existe hoy en
`src/aries/`) para validar el motor central con un caso de uso real y
exigente antes de generalizarlo y venderlo como plataforma. `docs/VISION.md`
documenta esto explícitamente como dos fases del mismo proyecto, no como
visiones en competencia.

## Cómo usar este archivo

- **No es la fuente de verdad activa.** Para el estado y las decisiones de
  arquitectura vigentes, ver `docs/VISION.md`, `docs/contracts/` y
  `docs/specs/`.
- **Sigue siendo relevante como diseño de referencia para la Fase 2**
  (generalización a plataforma SaaS). Antes de diseñar multi-tenancy, el
  workflow engine con checkpoints, el tool registry gobernado o la
  ingestión de canales externos, conviene releer `01_PRODUCT_VISION.md`,
  los ADRs en `adrs/`, `04_ARCHITECTURE_AND_MODULE_MAP.md`,
  `06_WORKFLOW_ENGINE_SPEC.md`, `07_TOOLING_AND_AGENT_POLICY.md`,
  `08_SECURITY_AND_MULTI_TENANCY.md` y `10_ROADMAP_MASTER.md` — mucho de
  ese pensamiento sigue siendo válido, aunque el código real hoy no lo
  implemente todavía.
- Varios documentos de `specs/` y algunos ADRs son deliberadamente
  esqueléticos (una oración por sección) — quedaron así en el original, no
  es un error de esta migración.
