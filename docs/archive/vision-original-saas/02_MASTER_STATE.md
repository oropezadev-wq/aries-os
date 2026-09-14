# Estado Maestro del Proyecto

---

## Estado general

**Estado actual:** Diseño fundacional.

---

## Fase actual

**Fase 0** — Definición de producto, arquitectura, invariantes y documentación maestra.

---

## Qué existe hoy

- Visión inicial del producto
- Stack candidato de alto nivel
- Hipótesis de arquitectura multi-tenant
- Lineamientos de workflow engine, tools, observabilidad y seguridad
- Pack documental base

---

## Qué no existe aún

- Código productivo
- Infraestructura de staging
- Dashboard funcional
- Runtime implementado
- Integración real con canales
- Facturación
- Evals automáticas en producción

---

## Supuestos vigentes

- El lenguaje principal del backend será Python
- La capa de API inicial será FastAPI
- La base de datos principal será PostgreSQL
- Se usará pgvector para retrieval inicial
- El canal inicial principal será tipo WhatsApp; el canal secundario, web chat
- El sistema será multi-tenant desde el diseño de entidades
- El primer vertical se elegirá antes de construir el piloto

---

## Decisiones aprobadas hasta ahora

- No se construirá un "JARVIS general"
- El producto será una plataforma verticalizada
- No se arrancará con microservicios extremos
- La arquitectura deberá poder evolucionar a event-driven
- Toda autonomía sensible requerirá aprobación o validación humana

---

## Riesgos identificados

- Sobreingeniería temprana
- Intentar abarcar demasiados verticales simultáneamente
- Costo alto por inferencia sin routing de modelos
- Dependencia excesiva del LLM para decisiones críticas
- Falta de validación comercial temprana

---

## Restricciones operativas

- El diseño debe ser compatible con un equipo pequeño
- El MVP debe poder desplegarse sin Kubernetes obligatorio
- El sistema debe mantener trazabilidad completa
- La seguridad y el aislamiento por tenant no pueden postergarse

---

## Objetivo inmediato

Completar la documentación fundacional y traducirla en:

- Esquema base de base de datos
- Contratos de API mínimos
- Estructura de repositorio
- Primer workflow vertical
- Primer lote de herramientas registradas

---

## Criterios de salida de esta fase

La fase actual se considera cerrada cuando existan:

- Documentación aprobada
- Vertical piloto elegido
- Arquitectura v1 congelada
- Backlog de implementación priorizado
- Decision log inicial completo