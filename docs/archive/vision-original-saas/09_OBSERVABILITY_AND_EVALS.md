# Observabilidad y Evals

---

## Propósito

Definir cómo el sistema será medido, inspeccionado y mejorado de forma continua.

---

## Observabilidad mínima

Todo componente crítico debe emitir:

- Logs estructurados
- Métricas
- Trazas

---

## Señales requeridas

### Logs

Cada log debe incluir como mínimo:

| Campo | Descripción |
|---|---|
| `timestamp` | Marca de tiempo del evento |
| `level` | Nivel de severidad |
| `service` | Servicio que emite el log |
| `module` | Módulo interno del servicio |
| `organization_id` | Tenant asociado, si aplica |
| `session_id` / `execution_id` | Contexto operativo, si aplica |
| `correlation_id` | Identificador de correlación entre servicios |
| `event_name` | Nombre del evento registrado |

### Métricas

Deben medirse:

- Requests por endpoint
- Latencia p50 / p95 / p99
- Errores por servicio
- Throughput
- Queue lag
- Tool success rate
- Workflow completion rate
- Approval rate
- Handoff rate
- Token y costo de inferencia por uso

### Trazas

Las trazas deben permitir seguir una ejecución completa desde:

1. Entrada del mensaje
2. Routing
3. Retrieval de contexto
4. Decisión del agente
5. Tool call
6. Validación
7. Respuesta al contacto

---

## KPIs de producto

| KPI | Descripción |
|---|---|
| Tiempo medio de primera respuesta | Velocidad de atención al contacto |
| Tasa de resolución automática | Porcentaje resuelto sin intervención humana |
| Tasa de handoff humano | Porcentaje derivado a operador |
| Leads capturados | Contactos nuevos registrados |
| Citas creadas | Agendamientos generados |
| Citas confirmadas | Agendamientos confirmados por el contacto |
| No-show reduction | Reducción de ausencias a citas |
| Conversión por canal | Tasa de conversión según canal de entrada |
| Costo IA por outcome | Costo de inferencia por resultado operativo |

---

## Evals

### Objetivos

- Evitar regresiones entre versiones
- Medir calidad de ejecución por workflow
- Validar prompts y policies
- Comparar versiones de workflow o modelo

### Tipos de eval

| Tipo | Descripción |
|---|---|
| `offline eval` | Evaluación sobre casos históricos sin afectar producción |
| `regression eval` | Detección de degradaciones respecto a versión anterior |
| `shadow eval` | Ejecución paralela silenciosa para comparar comportamiento |
| `canary eval` | Despliegue gradual con monitoreo controlado |
| `manual review eval` | Revisión humana de casos seleccionados |

### Casos de prueba por workflow

Cada workflow debe tener casos de prueba que cubran:

| Caso | Descripción |
|---|---|
| `happy path` | Flujo completo sin inconvenientes |
| `missing data` | Datos requeridos ausentes o incompletos |
| `ambiguous input` | Entrada ambigua o difícil de clasificar |
| `conflict with policy` | Acción que viola una policy activa |
| `external tool failure` | Falla de una integración o tool externa |
| `high risk action` | Acción que requiere aprobación o validación adicional |

### Métricas de eval

| Métrica | Descripción |
|---|---|
| `intent classification accuracy` | Precisión en la clasificación de intención |
| `tool selection correctness` | Corrección en la selección de tools |
| `policy compliance rate` | Tasa de cumplimiento de policies |
| `output completeness` | Completitud de la respuesta generada |
| `hallucination avoidance` | Capacidad de evitar información fabricada |
| `human review acceptance rate` | Tasa de aceptación en revisión humana |

---

## Regla de release

No promover a producción si se cumple alguna de las siguientes condiciones:

- Cae la tasa de cumplimiento de policy por debajo del umbral
- Aumentan los errores críticos respecto a la versión anterior
- Cae la precisión por debajo del umbral aprobado
- Aumenta de forma significativa el costo por outcome