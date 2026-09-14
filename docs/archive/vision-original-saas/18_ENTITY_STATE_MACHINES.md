# 18_ENTITY_STATE_MACHINES.md

## Propósito
Definir estados válidos y transiciones permitidas.

---

## Execution

Estados:
- created
- running
- waiting_input
- waiting_approval
- completed
- failed
- cancelled

Transiciones válidas:
- created → running
- running → waiting_input
- running → waiting_approval
- running → completed
- running → failed
- waiting_approval → running
- waiting_approval → cancelled

---

## Approval

Estados:
- pending
- approved
- rejected

Transiciones:
- pending → approved
- pending → rejected

---

## Session

Estados:
- active
- idle
- closed

---

## Tool Invocation

Estados:
- pending
- running
- success
- failed

---

## Review Item

Estados:
- open
- assigned
- resolved
- closed

---

## Reglas

- No se permiten transiciones fuera de las definidas
- Toda transición debe registrarse
- Estados inconsistentes deben bloquear ejecución