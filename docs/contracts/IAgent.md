# Contrato: IAgent

## Responsabilidad
Define cómo ejecutar acciones en sistemas específicos.

## Agentes Esperados
- **WindowsAgent**: Controlar Windows, archivos, procesos
- **DockerAgent**: Gestionar contenedores y imágenes
- **GitAgent**: Operaciones Git (commit, push, pull)
- **EmailAgent**: Enviar y recibir emails
- **BrowserAgent**: Navegación web
- **FileSystemAgent**: Operaciones con archivos
- **ProcessAgent**: Ejecutar comandos y scripts
- **HomeAssistantAgent**: Integración domotica
- **DatabaseAgent**: Consultas y operaciones SQL

## Métodos Requeridos

### async execute(action, **kwargs) → ActionResult
Ejecuta una acción específica.

**Ejemplo:**
```python
# WindowsAgent
result = await agent.execute("open_file", path="C:\\documento.txt")

# DockerAgent
result = await agent.execute("run_container", image="nginx", ports=[80])
```

**Retorna:** ActionResult con:
- `status`: PENDING, RUNNING, SUCCESS, FAILED, CANCELLED
- `output`: Resultado textual
- `error`: Mensaje de error si falló
- `data`: Datos estructurados (JSON-compatible)
- `execution_time_ms`: Tiempo de ejecución

**Nunca debe propagar excepciones.** Cualquier error durante la ejecución (permisos, recurso no encontrado, timeout, etc.) se captura dentro de `execute()` y se retorna como `ActionResult(status=FAILED, error=<mensaje>)`; `execute()` nunca deja escapar una excepción sin capturar hacia quien lo llama.

### get_capabilities() → list[str]
Lista acciones disponibles.

**Ejemplo (WindowsAgent):**
```
["open_file", "close_file", "list_directory", "delete_file", 
 "create_directory", "run_process", "get_system_info"]
```

### requires_confirmation(action, command=None, **kwargs) → bool
Verifica si una acción requiere confirmación.

Acciones destructivas o peligrosas deben retornar `True`.

Una implementación puede aceptar un kwarg opcional `command: str | None`
además de `action`, para evaluar el contenido concreto de la acción (por
ejemplo, si el string de un `run_command` contiene un comando destructivo
conocido como `rm`, `del`, `format`, etc.) en vez de decidir solo por el
nombre de la acción. Debe ser retrocompatible: `requires_confirmation(action)`
sin `command` sigue siendo una llamada válida (ver `ProcessAgent`, que usa
esto para `run_command`).

### async is_available() → bool
Verifica que el agente puede funcionar.

Ej: Windows agent verifica SO, Docker agent verifica daemon.

### get_agent_name() → str
Retorna el nombre único del agente.
