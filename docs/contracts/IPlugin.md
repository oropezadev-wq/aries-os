# Contrato: IPlugin

## Responsabilidad
Define cómo agregar funcionalidad nueva sin modificar el kernel.

## Principios
1. **Aislamiento:** Plugin no accede a internals del kernel
2. **Independencia:** Plugin puede descargarse en runtime
3. **Compatibilidad:** Cambios en plugin no rompen kernel
4. **Versionado:** Cada plugin tiene versión independiente
5. **Hookeable:** Plugin se conecta solo por eventos

## Métodos Requeridos

### get_metadata() → PluginMetadata
Retorna información del plugin:
- **name:** Nombre único (lowercase, sin espacios)
- **version:** Versión semántica (ej: "1.0.0")
- **author:** Creador del plugin
- **description:** Descripción de funcionalidad
- **requires:** Dependencias (otros plugins o paquetes pip)
- **entry_point:** Ruta del módulo principal

### async initialize(context) → bool
Se ejecuta cuando se carga el plugin.

**Context proporciona:**
- `logger`: Logger estructurado
- `event_bus`: Bus de eventos para comunicar
- `di_container`: Contenedor de inyección
- `settings`: Configuración global

**Debe:**
- Validar dependencias
- Inicializar recursos
- Registrar hooks

Retorna True si éxito, False en error.

### async shutdown() → bool
Se ejecuta cuando se descarga el plugin.

**Debe:**
- Limpiar threads
- Cerrar conexiones
- Liberar archivos
- Guardar estado si es necesario

Retorna True si limpió exitosamente.

### register_hooks() → dict[str, Callable]
Registra manejadores de eventos.

**Eventos disponibles:**
- KERNEL_STARTING
- KERNEL_READY
- KERNEL_SHUTDOWN
- INTENT_DETECTED
- PLAN_CREATED
- PLAN_EXECUTED
- ACTION_STARTED
- ACTION_COMPLETED
- ACTION_FAILED
- MEMORY_STORED
- MEMORY_DELETED
- MEMORY_SEARCHED
- ERROR_OCCURRED
- PLUGIN_LOADED
- PLUGIN_UNLOADED

### get_capabilities() → list[str]
Lista acciones nuevas que el plugin proporciona.

Estas se registran en el sistema y pueden ser usadas por el planner.

Ejemplo (Music Plugin):
```
["play", "pause", "next", "previous", "volume_up", "volume_down"]
```

### is_compatible(kernel_version) → bool
Valida compatibilidad con la versión actual del kernel.

Retorna True si el plugin puede ejecutarse sin romper el sistema.
