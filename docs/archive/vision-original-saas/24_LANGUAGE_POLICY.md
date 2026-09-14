# 24_LANGUAGE_POLICY.md

## Propósito

Definir la política oficial de idioma del proyecto para mantener consistencia entre documentación, código, frontend, operación, producto y trabajo asistido por IA.

Esta política existe para evitar:

- mezcla arbitraria de español e inglés
- traducciones que rompan consistencia técnica
- documentación confusa para operadores o clientes
- prompts ambiguos para IA
- divergencia entre lenguaje de negocio y lenguaje de implementación

---

## Principio rector

El proyecto usará un modelo de idioma híbrido y controlado:

- **inglés para el núcleo técnico**
- **español para producto, operación y experiencia humana**

La meta no es traducir todo, sino usar el idioma correcto según el contexto para reducir fricción y preservar precisión.

---

## Objetivos de esta política

1. Mantener coherencia técnica en código y arquitectura.
2. Hacer la documentación operativa comprensible para un público hispanohablante.
3. Facilitar el uso de IA sin romper contratos, entidades o vocabulario interno.
4. Alinear el sistema con un mercado peruano / LATAM mayoritariamente hispanohablante.
5. Evitar redacciones híbridas caóticas o inconsistentes.

---

## Regla general

### Se mantiene en inglés
Todo lo que forme parte del sistema técnico interno, del código o de contratos formales.

### Se escribe en español
Todo lo orientado a negocio, operación humana, explicación funcional, onboarding, soporte interno y experiencia de usuario para público hispanohablante.

---

## 1. Inglés obligatorio

Los siguientes elementos deben permanecer en inglés y no deben traducirse salvo decisión explícita registrada en el `11_DECISION_LOG.md`.

### 1.1 Código
- nombres de variables
- nombres de funciones
- nombres de clases
- nombres de módulos
- nombres de paquetes
- nombres de repositorios
- nombres de servicios internos
- nombres de componentes técnicos

### 1.2 Modelo de datos
- nombres de tablas
- nombres de columnas
- nombres de constraints
- nombres de índices
- nombres de claves foráneas
- nombres de enums técnicos

### 1.3 Contratos técnicos
- endpoints
- rutas API
- payloads JSON
- request schemas
- response schemas
- error codes
- event names
- command names
- integration field names

### 1.4 Entidades del dominio interno
Cuando una palabra funciona como nombre canónico de entidad del sistema, se mantiene en inglés. Ejemplos:

- `Organization`
- `User`
- `Contact`
- `ContactIdentity`
- `Session`
- `Message`
- `Workflow`
- `WorkflowVersion`
- `WorkflowStep`
- `WorkflowEdge`
- `Execution`
- `ExecutionStep`
- `Tool`
- `ToolInvocation`
- `Approval`
- `AuditLog`
- `KnowledgeBase`
- `Document`
- `DocumentChunk`
- `ReviewItem`
- `Event`

### 1.5 Estados y vocabulario técnico de runtime
Se mantienen en inglés términos como:

- `created`
- `queued`
- `running`
- `waiting_input`
- `waiting_approval`
- `waiting_external`
- `completed`
- `failed`
- `cancelled`
- `expired`

Y también:

- `workflow`
- `execution`
- `step`
- `tool`
- `tool invocation`
- `approval`
- `review item`
- `handoff`
- `tenant`
- `checkpoint`
- `payload`
- `endpoint`
- `schema`
- `feature flag`

### 1.6 Identificadores técnicos
No se traducen:

- `organization_id`
- `user_id`
- `contact_id`
- `session_id`
- `workflow_id`
- `execution_id`
- `request_id`
- `idempotency_key`
- `current_step_key`
- `raw_payload_json`
- `input_schema_json`
- `output_schema_json`

---

## 2. Español obligatorio

Los siguientes contenidos deben escribirse en español claro, profesional y natural.

### 2.1 Documentación de producto
- visión del producto
- propuesta de valor
- diferenciación
- mercado objetivo
- plan piloto
- roadmap de negocio
- criterios de éxito
- narrativa de monetización

### 2.2 Documentación operativa
- manuales de uso
- runbooks operativos
- playbooks
- procedimientos internos
- onboarding de clientes
- onboarding de operadores
- flujos de soporte
- políticas de uso

### 2.3 Frontend visible para humanos
Cuando el usuario objetivo sea hispanohablante:

- labels
- botones
- formularios
- estados visibles
- mensajes informativos
- mensajes de error visibles
- instrucciones
- paneles de operación
- dashboards operativos
- textos de ayuda

### 2.4 Comunicación comercial y de soporte
- demos
- propuestas
- landing copy
- FAQs para clientes
- documentación externa
- correos y materiales de venta
- contenido de capacitación

---

## 3. Política híbrida para documentación técnica

La documentación técnica puede y debe usar español en las explicaciones, pero conservar inglés en los identificadores y términos internos del sistema.

### Ejemplo correcto
> Toda `Execution` debe guardar un `checkpoint_json` al finalizar cada `step`.

### Ejemplo incorrecto
> Toda ejecución debe guardar un punto de control json al finalizar cada paso.

El ejemplo incorrecto rompe consistencia con entidades y campos del sistema.

---

## 4. Reglas por tipo de archivo

### 4.1 Archivos `docs/*.md`
#### Regla
- contenido explicativo: español
- términos técnicos internos: inglés
- nombres de archivos: inglés, salvo decisión contraria formal

#### Ejemplo
- `06_WORKFLOW_ENGINE_SPEC.md` puede estar redactado en español, pero debe conservar `Workflow`, `Execution`, `step`, `checkpoint`, `Approval`.

### 4.2 Archivos de código
#### Regla
Todo en inglés.

Incluye:
- nombres
- comentarios técnicos
- docstrings si forman parte del estándar del repositorio

### 4.3 Archivos de frontend
#### Regla
- código: inglés
- texto visible al usuario: español, si el mercado es hispanohablante

### 4.4 Archivos de API / contratos
#### Regla
- estructuras, keys, rutas y enums: inglés
- explicación alrededor: español

### 4.5 Archivos de base de datos
#### Regla
- tablas y campos: inglés
- explicación del esquema: español

---

## 5. Glosario operativo de traducción controlada

Esta sección define cómo tratar términos que pueden aparecer en ambos idiomas.

### Mantener como nombre técnico
- `Organization`
- `User`
- `Contact`
- `Session`
- `Workflow`
- `Execution`
- `Tool`
- `ToolInvocation`
- `Approval`
- `ReviewItem`
- `KnowledgeBase`
- `Event`

### Traducir solo en contexto explicativo
- organization → organización, solo cuando no se refiere a la entidad `Organization`
- user → usuario, solo cuando no se refiere a la entidad `User`
- contact → contacto, solo cuando no se refiere a la entidad `Contact`
- session → sesión, solo cuando no se refiere a la entidad `Session`
- event → evento, solo cuando no se refiere a la entidad `Event`
- outcome → resultado, si es explicación general

### Mantener siempre en inglés por consistencia interna
- workflow
- execution
- tool
- handoff
- checkpoint
- payload
- endpoint
- schema
- feature flag
- review item
- approval gate
- tenant
- retry
- fallback
- rollout
- rollback

---

## 6. Reglas para IA y traducción asistida

Cualquier IA usada para redactar, traducir o refactorizar documentación debe seguir estas reglas:

1. No traducir nombres de entidades del dominio.
2. No traducir nombres de archivos.
3. No traducir código, JSON, rutas API, eventos ni schemas.
4. No traducir estados de máquinas de estado.
5. No inventar equivalentes en español para términos técnicos ya fijados.
6. Traducir solo el texto narrativo, operativo o explicativo.
7. Si una traducción puede romper consistencia, conservar el término original.
8. Si hay ambigüedad, priorizar precisión técnica sobre naturalidad lingüística.
9. No cambiar la estructura del documento salvo instrucción explícita.
10. No resumir ni omitir contenido durante traducciones.

---

## 7. Reglas de redacción

### 7.1 Español deseado
El español del proyecto debe ser:

- claro
- directo
- profesional
- neutro
- entendible en Perú y LATAM
- sin adornos innecesarios
- sin traducción literal torpe del inglés

### 7.2 Qué evitar
- Spanglish innecesario
- sinónimos distintos para el mismo concepto
- cambiar un término técnico en cada documento
- traducir contratos o identificadores
- redacción demasiado localista si afecta claridad regional

### 7.3 Preferencias
Usar frases como:
- “el sistema”
- “la organización”
- “el operador”
- “el tenant”
- “el workflow”
- “la execution”
solo si esa mezcla preserva precisión

Cuando esa mezcla suene extraña, reescribir alrededor sin traducir la entidad técnica.

Ejemplo:
- Mejor: “La `Execution` pasa a estado `waiting_approval` cuando la acción requiere validación humana.”
- Peor: “La ejecución pasa a estado espera de aprobación...”

---

## 8. Política del frontend

### 8.1 Para usuario final hispanohablante
Todo texto visible debe estar en español, incluyendo:

- mensajes de bienvenida
- mensajes de error visibles
- formularios
- instrucciones
- botones
- estados de interacción
- avisos operativos

### 8.2 Para operadores internos hispanohablantes
El panel debe estar principalmente en español, pero puede conservar términos técnicos clave cuando sea útil para trazabilidad con backend.

Ejemplos aceptables:
- “Estado de `Execution`”
- “Review queue”
- “Reanudar workflow”
- “Tomar control manual”

### 8.3 Para administración técnica
Puede mantenerse más híbrido si el usuario esperado es técnico.

---

## 9. Política para demos, ventas y documentación externa

Todo material orientado a:
- clientes
- prospectos
- socios
- equipos no técnicos
- capacitación comercial

debe priorizar español casi completo, salvo nombres del producto o términos técnicos inevitables.

El objetivo externo no es exponer el vocabulario interno del sistema, sino comunicar valor con claridad.

---

## 10. Política para prompts

### Prompts para implementación técnica
- pueden estar en español
- deben conservar términos internos en inglés
- deben referenciar nombres reales de entidades y módulos

### Prompts para contenido comercial u operativo
- deben estar en español
- deben evitar exceso de terminología técnica

### Regla general
Todo prompt debe respetar esta política de idioma antes de proponer cambios.

---

## 11. Criterios para aceptar una traducción

Una traducción o conversión de idioma se considera válida solo si cumple todo lo siguiente:

1. No rompe consistencia con el resto del sistema.
2. No altera nombres técnicos.
3. No cambia semántica.
4. No introduce ambigüedad nueva.
5. Mantiene intactos ejemplos técnicos.
6. Suena natural para humanos hispanohablantes.
7. Sigue siendo útil para implementación y operación.

---

## 12. Casos que requieren decisión explícita

Se debe registrar decisión en `11_DECISION_LOG.md` si se quiere cambiar cualquiera de estos:

- traducir nombres de archivos
- traducir nombres de entidades del dominio
- traducir estados del engine
- traducir nombres de eventos
- traducir nombres de tools
- traducir nombres de tablas o campos
- cambiar idioma base del frontend técnico
- cambiar idioma oficial del repositorio

---

## 13. Resumen operativo

### Regla corta
- **backend y contratos: inglés**
- **producto, operación y UX humana: español**
- **docs: español con términos técnicos internos en inglés**

### Regla práctica
Si algo debe coincidir con código, DB, eventos o API, se queda en inglés.  
Si algo lo va a leer, operar, vender o entender una persona hispanohablante, va en español.

---

## 14. Estado de esta política

Estado: vigente  
Alcance: todo el proyecto  
Aplicación: obligatoria para documentación, prompts, frontend y trabajo con IA