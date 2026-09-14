# Invariantes del Sistema

---

## Propósito

Este documento define las restricciones duras del sistema. No son sugerencias. Son reglas obligatorias que ninguna decisión de diseño, implementación o configuración puede violar.

---

## Invariantes de negocio y arquitectura

### I-001 — Multi-tenancy obligatorio

Todo recurso persistente del dominio operacional debe estar vinculado a un `organization_id`.

### I-002 — El chat no es la fuente de verdad

El estado operacional vive en entidades del dominio, no en texto libre de conversación.

### I-003 — Tool execution gobernado

Ningún agente ni workflow puede ejecutar una tool que no esté registrada en el tool registry.

### I-004 — Auditabilidad total

Toda acción con efecto lateral debe generar un registro en `audit_log` y una `tool_invocation` cuando corresponda.

### I-005 — Riesgo controlado

Toda acción de alto riesgo requiere validación automática reforzada y/o aprobación humana.

### I-006 — Checkpoint obligatorio

Toda ejecución de workflow debe guardar checkpoints suficientes para poder reanudar, inspeccionar o abortar con seguridad.

### I-007 — Separación entre razonamiento y ejecución

El LLM puede sugerir decisiones, pero la capa de control del sistema es quien autoriza y ejecuta.

### I-008 — Contratos explícitos

Toda tool, endpoint y evento debe tener un contrato de entrada y salida definido.

### I-009 — Idempotencia en acciones sensibles

La creación de citas, el envío de mensajes, los cobros, la generación de tickets y la actualización de estados externos deben soportar idempotencia.

### I-010 — Human override permanente

Siempre debe existir la capacidad de takeover humano y override controlado sobre cualquier proceso en ejecución.

### I-011 — Observabilidad mínima obligatoria

Todo componente crítico debe emitir logs estructurados, métricas y trazas.

### I-012 — Seguridad por defecto

Acceso mínimo, secretos cifrados y permisos explícitos en todas las integraciones.

### I-013 — Evolución compatible

Toda nueva versión debe respetar migraciones, mantener backward compatibility razonable o contar con una estrategia clara de transición.

### I-014 — Configuración separada del código

Las reglas por tenant, prompts, políticas y catálogos no deben hardcodearse cuando pertenezcan al dominio configurable.

### I-015 — Verticalización explícita

La lógica específica de un vertical no debe contaminar sin control los módulos core del sistema.

### I-016 — Ninguna memoria sin política

Toda memoria debe indicar origen, duración, alcance, sensibilidad y reglas de uso.

### I-017 — Recuperación contextual validada

El contexto recuperado no debe asumirse como verdad absoluta; debe pasar por filtros de relevancia y política antes de usarse.

### I-018 — Fallar de forma segura

Cuando el sistema no tenga suficiente contexto o confianza, debe pedir aclaración, derivar a un humano o detener la acción.

### I-019 — Toda excepción relevante se registra

Los errores de tools, timeouts, caídas de integración y decisiones bloqueadas deben persistirse.

### I-020 — Diseño para métricas de negocio

El sistema no solo mide eventos técnicos; debe medir outcomes operativos y comerciales.

---

## Invariantes de implementación

- No mezclar lógica de tenant con lógica global sin separación clara.
- No depender del historial completo de chat para reconstruir el estado operacional.
- No exponer secretos en logs.
- No ejecutar efectos laterales directamente desde la capa HTTP sin control de dominio.
- No permitir que un LLM construya SQL libre para producción sin una capa controlada.
- No aceptar payloads sin validación tipada.