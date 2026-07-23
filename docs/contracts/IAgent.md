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

### get_capabilities() → list[str]
Lista acciones disponibles.

**Ejemplo (WindowsAgent):**
```
["open_file", "close_file", "list_directory", "delete_file", 
 "create_directory", "run_process", "get_system_info"]
```

### requires_confirmation(action) → bool
Verifica si una acción requiere confirmación.

Acciones destructivas o peligrosas deben retornar `True`.

### async is_available() → bool
Verifica que el agente puede funcionar.

Ej: Windows agent verifica SO, Docker agent verifica daemon.

### get_agent_name() → str
Retorna el nombre único del agente.
