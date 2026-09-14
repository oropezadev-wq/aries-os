# 17_END_TO_END_FLOWS.md

## Propósito
Describir flujos completos del sistema para conectar todos los módulos.

---

## Flujo 1: Mensaje entrante → respuesta

1. Usuario envía mensaje (WhatsApp/web)
2. Webhook recibe evento
3. Se valida payload
4. Se identifica Organization
5. Se busca o crea Contact
6. Se busca o crea Session
7. Se guarda Message
8. Router clasifica intención
9. Context Builder construye contexto
10. Planner decide acción
11. Puede:
   - responder directamente
   - iniciar workflow
   - ejecutar tool
   - pedir aprobación
12. Validator revisa
13. Se genera respuesta
14. Se envía mensaje
15. Se registra evento y métricas

---

## Flujo 2: Workflow con tool

1. Execution inicia
2. Step actual = run_tool
3. Planner selecciona tool
4. Se valida policy
5. Se crea ToolInvocation
6. Se ejecuta tool
7. Se guarda resultado
8. Validator revisa
9. Execution continúa

---

## Flujo 3: Approval humano

1. Step detecta riesgo alto
2. Se crea Approval
3. Se crea ReviewItem
4. Execution pasa a waiting_approval
5. Humano revisa
6. Aprueba o rechaza
7. Execution continúa o se cancela

---

## Flujo 4: Handoff humano

1. Sistema detecta ambigüedad o límite
2. Se crea ReviewItem
3. Se genera resumen automático
4. Humano toma control
5. Se registra acción humana

---

## Flujo 5: Retrieval de conocimiento

1. Context Builder recibe consulta
2. Se generan embeddings
3. Se busca en Knowledge Base
4. Se recuperan chunks relevantes
5. Se agregan al contexto
6. Planner usa esta información