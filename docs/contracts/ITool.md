# Contrato: ITool

## Responsabilidad
Define acciones específicas ejecutables por el planner.

## Diferencia con Agent
- **Agent:** Ejecutor genérico de un sistema (ej: WindowsAgent)
- **Tool:** Acción específica ejecutable (ej: `send-email`)

Un Tool es más específico, tipado y schema-driven.
El planner usa Tools para ejecutar acciones concretas.

## Métodos Requeridos

### get_metadata() → dict
Retorna información de la herramienta.

Debe incluir:
- `name`: Nombre único (lowercase: "send-email")
- `description`: Qué hace
- `version`: Versión semántica
- `category`: Categoría (file, network, system, data, etc)
- `requires_authorization`: ¿Necesita confirmación?

### async execute(**kwargs) → dict[str, Any]
Ejecuta la herramienta.

Debe retornar dict con:
```python
{
    "success": True/False,
    "result": resultado_específico,
    "error": "error message si falló",
    "execution_time_ms": tiempo,
}
```

**Ejemplo:**
```python
result = await send_email_tool.execute(
    to="user@example.com",
    subject="Hola",
    body="Mensaje de prueba"
)
```

### get_actions() → list[str]
Lista acciones específicas que la herramienta proporciona.

Ejemplo (FileSystemTool):
```python
["read", "write", "delete", "list_directory", "create_directory"]
```

### is_available() → bool
Valida que la herramienta puede funcionar.

Verifica:
- Recursos disponibles
- Conectividad (si aplica)
- Servicios dependientes

### requires_confirmation(action: str) → bool
Verifica si una acción es peligrosa y requiere confirmación.

Retorna True para: `delete`, `format`, `uninstall`, `shutdown`, etc.

Mismo nombre de método que `IAgent.requires_confirmation` (`docs/contracts/IAgent.md`)
— unificado el 2026-07-25 para que el Planner no tenga que normalizar dos
nombres distintos para el mismo concepto (antes este método se llamaba
`requires_authorization`). Igual que en `IAgent`, una implementación puede
aceptar kwargs opcionales además de `action` para evaluar el contenido
concreto de la llamada.

### get_tool_name() → str
Identificador único de la herramienta.

Ejemplo: `"file-system"`, `"email-sender"`, `"web-scraper"`

## Tools Esperadas (Ejemplos)

### Sistema de Archivos
- **name:** `file-system`
  - Acciones: `read`, `write`, `delete`, `list_directory`, `create_directory`

### Red / Comunicación
- **name:** `email-sender`
  - Acciones: `send`, `draft`, `schedule`
- **name:** `web-scraper`
  - Acciones: `fetch`, `extract`, `parse`

### Datos
- **name:** `database-query`
  - Acciones: `query`, `insert`, `update`, `delete`
- **name:** `csv-parser`
  - Acciones: `parse`, `export`, `merge`

### Sistema
- **name:** `command-executor`
  - Acciones: `run`, `stop`, `get_output`
- **name:** `system-info`
  - Acciones: `get_info`, `get_processes`, `get_memory`

### Tareas
- **name:** `task-manager`
  - Acciones: `create`, `update`, `complete`
- **name:** `reminder-manager`
  - Acciones: `set`, `cancel`, `list`

## Flujo de Ejecución
```
1. Planner detecta intención
2. Busca Tool correspondiente
3. Obtiene metadata: get_metadata()
4. Valida disponibilidad: is_available()
5. Valida autorización: requires_confirmation()
6. Si requiere confirmación, pedir OK al usuario
7. Ejecutar: execute(**kwargs)
8. Retornar resultado
9. Disparar evento TOOL_EXECUTED
```

## Restricciones
- Parámetros siempre validados
- Nunca asumir permisos
- Siempre loguear ejecución
- Retornar estructura consistente
- Manejo de errores robusto

## Ejemplo de Tool
```python
class SendEmailTool(ITool):
    def get_metadata(self):
        return {
            "name": "send-email",
            "description": "Envía un correo electrónico usando SMTP",
            "version": "0.1.0",
            "category": "network",
            "requires_authorization": True,
        }

    async def execute(self, **kwargs):
        # enviar correo
        return {
            "success": True,
            "result": {"message_id": "123"},
            "error": None,
            "execution_time_ms": 312,
        }
```
