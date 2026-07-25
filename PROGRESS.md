# Aries OS — Progreso

> Fuente de verdad del estado del proyecto. Se actualiza al TERMINAR cada tarea, no al empezarla.
> Antes de cualquier tarea nueva, leer este archivo primero.

## Estado actual (fecha de hoy)
| Fase | Estado |
| --- | --- |
| v0.1 Blueprint | completa |
| v0.2 Foundation | completa |
| v0.3 Kernel | parcial |
| v0.4 Planner | no iniciada |
| v0.5 Plugins | 0% real, solo contrato |
| v0.6 Memory | parcial |
| Agents | parcial (2 agentes: FileSystemAgent, ProcessAgent) |
| v0.7 Voice | no iniciada |
| v1.0 MVP | no iniciada |

## Baseline conocido
- `pytest` tiene 2 fallos intermitentes esperados (no son regresiones nuevas): `tests/unit/test_kernel.py::test_kernel_publishes_initialized_event` y `::test_kernel_publishes_shutdown_event` — detalle en "Qué NO existe todavía".

## Qué existe implementado (código real, no contratos)
- `src/aries/core/kernel.py`: kernel básico con initialize/run/shutdown y estado local.
- `src/aries/config/settings.py`: configuración de aplicación con Pydantic Settings y .env loading.
- `src/aries/logging/__init__.py`: inicializa structlog con renderer y logger.
- `src/aries/api.py`: FastAPI app mínima con endpoint `/health`.
- `src/aries/exceptions/__init__.py`: excepciones personalizadas definidas.
- `src/aries/types.py`: alias de tipos comunes.
- `src/aries/memory/in_memory.py`: implementación de IMemory en memoria local.
- `src/aries/llm/ollama_provider.py`: proveedor Ollama con AsyncClient, complete, embed e is_available.
- `src/aries/core/kernel.py`: kernel inyecta IMemory e ILLMProvider y valida disponibilidad de LLM al iniciar.
- `src/aries/__main__.py`: construcción de Kernel con InMemoryStore y OllamaProvider usando async context manager.
- `tests/unit/test_kernel.py`: tests de kernel con fake ILLMProvider y disponibilidad configurable.
- `tests/unit/test_config.py`: tests de carga de configuración y overrides de env.
- `src/aries/contracts/memory.py` y `src/aries/memory/in_memory.py`: se agregó el campo `expires_at` a `MemoryItem` y un parámetro opcional `expires_at` a `store()`; `clear_expired()` ahora borra de verdad los items vencidos (antes era un no-op permanente). `core/kernel.py` ahora usa `self.memory.store(...)` en `initialize()` para guardar un item tipo `context` — primer uso real de Memory en el flujo del kernel. Detalle completo en `docs/audits/2026-07-24-diagnostico.md`.
- Se corrigió un import circular preexistente entre `src/aries/contracts/event_bus.py` y `src/aries/events/__init__.py` que impedía `import aries` por completo (bloqueaba correr cualquier test). Fix mínimo de orden de imports, sin cambios de lógica de negocio en `events/`. Ver addendum en `docs/audits/2026-07-24-diagnostico.md`.
- `src/aries/agents/filesystem/agent.py`: **primer `IAgent` concreto del proyecto.** `FileSystemAgent` implementa `execute`/`get_capabilities`/`requires_confirmation`/`is_available`/`get_agent_name` con `pathlib` puro (sin dependencias nuevas). Capacidades: `open_file`/`read_file` (alias), `list_directory`, `create_directory`, `delete_file` (única acción con `requires_confirmation() == True`), `create_file`/`write_file` (alias; `create_file` no sobrescribe por defecto, `write_file` sí). `execute()` atrapa `FileNotFoundError`/`PermissionError`/`FileExistsError`/`IsADirectoryError`/`NotADirectoryError`/`OSError` y los devuelve como `ActionResult(status=FAILED, error=...)` en vez de dejarlos propagar — esto ya quedó resuelto formalmente en `docs/contracts/IAgent.md` y en el docstring de `contracts/agent.py::execute()` (antes decían `Raises: PermissionError`, ahora dicen explícitamente que nunca se propagan excepciones). 35 tests en `tests/unit/test_filesystem_agent.py`, incluyendo archivo/directorio inexistente y permiso denegado (archivos de solo lectura vía `os.chmod`, y lectura de un directorio como archivo — en Windows eso levanta `PermissionError`, no `IsADirectoryError`).
- `src/aries/agents/process/agent.py`: **segundo `IAgent` concreto.** `ProcessAgent` ejecuta comandos/scripts y gestiona procesos con `subprocess`/`os`/`signal` puros (sin `psutil`, que no está en `pyproject.toml` — se resolvió `list_processes`/`get_process_info` parseando la salida CSV de `tasklist`, utilidad de consola exclusiva de Windows). Capacidades: `run_command` (**shell=False**, tokeniza el string de comando con `shlex.split()` — ver corrección de seguridad abajo —, captura stdout/stderr/exit_code, timeout configurable, default `DEFAULT_TIMEOUT_SECONDS = 30.0`), `run_script` (shell=False, argv explícito; intérprete inferido por extensión — `.py`→`sys.executable`, `.ps1`→PowerShell con `-ExecutionPolicy Bypass`, `.sh`→`bash` — o explícito vía kwarg `interpreter`), `kill_process` (`os.kill(pid, SIGTERM)`, que en Windows sí mapea a `TerminateProcess`), `list_processes`, `get_process_info`. `requires_confirmation()` extiende la firma del contrato con un kwarg opcional `command: str | None = None` (retrocompatible, y ya documentado formalmente en `docs/contracts/IAgent.md`) para poder evaluar el contenido del comando: devuelve `True` siempre para `kill_process`, y para `run_command` solo si el primer token de algún segmento del comando (separado por `;`/`&`/`|`) coincide con una lista corta de nombres destructivos conocidos (`rm`, `del`, `format`, etc.) — heurística de mejor esfuerzo, no un sandbox. `os.kill` sobre un PID inexistente en Windows lanza `OSError` genérico (`WinError 87`), no `ProcessLookupError`, por eso `kill_process`/`get_process_info` verifican existencia vía `tasklist` primero y levantan `ProcessLookupError` ellos mismos. 41 tests en `tests/unit/test_process_agent.py`, incluyendo timeout (`run_command` y `run_script`), comando/script/PID inexistente, comillas mal formadas, comando vacío, permiso denegado en `kill_process` simulado con `monkeypatch` (deliberadamente no se testeó matando un PID protegido real del sistema), una prueba de regresión de seguridad que confirma que `&&` ya no encadena un segundo comando, y una prueba de regresión que confirma que una ruta Windows sin comillas ya no se corrompe.
- **Corrección de seguridad en `run_command`:** originalmente usaba `shell=True` con el string de comando tal cual. Se cambió a tokenizar con `shlex` + `shell=False`, cerrando el vector de inyección de comandos (`;`, `&&`, `|` dejan de ser operadores de shell y se pasan como argv literal — hay un test de regresión que lo confirma). **Costo funcional real, no una elección mía:** se pierde soporte para pipes, redirects (`>`/`<`), expansión de variables (`%VAR%`).
- **Aislamiento Windows-específico en `ProcessAgent`:** `list_processes`/`get_process_info`/la verificación de existencia de `kill_process` quedaron detrás de `_list_processes_windows()`/`_get_process_info_windows()`, con un único punto de detección de SO (`_require_windows()`, vía `platform.system()`). Los handlers públicos no saben que son Windows-específicos. Linux/Mac levantan `NotImplementedError` desde ese único punto — no implementados todavía, ver `execute()` que ahora también atrapa `NotImplementedError` y lo retorna como `ActionResult(FAILED)`, consistente con "nunca propagar excepciones".
- **Corrección del tokenizador de `run_command` (`shlex.split(..., posix=False)` + limpieza manual de comillas, en `_split_command()`):** `shlex.split()` en modo POSIX (el default) trata `\` como carácter de escape, corrompiendo rutas Windows **sin comillas** (`C:\Windows\System32\app.exe` → `C:WindowsSystem32app.exe`, verificado empíricamente). `posix=False` preserva las barras invertidas, pero como efecto secundario deja las comillas de agrupación como caracteres literales en el token — así que `_split_command()` las remueve a mano después de tokenizar. Con esto, tanto rutas sin comillas como argumentos entre comillas (`-c "código"`) funcionan correctamente; hay test para ambos casos.
- **Decisión sobre comandos internos de cmd.exe — cerrada, no queda pendiente:** `dir`, `cd`, `echo`, `type`, `copy`, `del`, `set`, `cls`, etc. no tienen `.exe` propio en Windows (solo existen dentro de un shell), así que `run_command(command="dir")` falla con `ActionResult(FAILED)` — y **se deja así a propósito**, no se agrega un prefijo automático `["cmd", "/c", ...]` que reintroduzca superficie de shell. Razón: esa funcionalidad ya existe donde corresponde — listar/crear/borrar archivos es `FileSystemAgent` (`list_directory`, `delete_file`, etc.), y cambiar de directorio para un comando es el parámetro `cwd` que `run_command`/`run_script` ya aceptan. `ProcessAgent` es deliberadamente solo para ejecutables reales, no para reimplementar un shell.

## Qué NO existe todavía (pendiente real)
- Existen dos `IAgent` concretos (`FileSystemAgent`, `ProcessAgent`). El resto de los agentes documentados en `docs/contracts/IAgent.md` (WindowsAgent, DockerAgent, GitAgent, EmailAgent, BrowserAgent, HomeAssistantAgent, DatabaseAgent) sigue sin implementar. `agents/base.py` y `agents/manager.py` siguen vacíos — no hay registro/orquestación de agentes todavía, y nada en `core/kernel.py` invoca a ningún agente (siguen sin cablear al flujo real, igual que Memory antes de la tarea que la conectó).
- No hay ninguna clase concreta que implemente `IPlugin`.
- No hay ninguna clase concreta que implemente `ITool`.
- `src/aries/core/kernel.py` no integra memoria, agentes, plugins ni planner reales, solo usa sleeps como stub.
- No hay persistencia de memoria.
- No hay planner ni ejecución de tools definidos en el código.
- No hay implementación de subsistema de voz.
- `src/aries/events/`: existe implementación de Event Bus con tests (motor sólido, ya revisado en `docs/audits/2026-07-24-diagnostico.md`), pero solo define 2 eventos de dominio (`KernelInitializedEvent`, `KernelShutdownEvent`) de los ~14 que `docs/contracts/IPlugin.md` da por hechos (`INTENT_DETECTED`, `PLAN_CREATED`, `ACTION_*`, `MEMORY_*`, `PLUGIN_*`).
- `src/aries/plugins/`: `installer.py`, `loader.py`, `manifest.py`, `registry.py` están vacíos (0 bytes) — no hay ninguna implementación, solo el contrato `IPlugin`.
- `tests/unit/test_kernel.py::test_kernel_publishes_initialized_event` y `::test_kernel_publishes_shutdown_event` son preexistentes y **flaky** (no causado por el trabajo de hoy, y se hizo visible recién ahora porque antes ni siquiera se podía correr `pytest` por el import circular): comparan un `BaseEvent` publicado por el kernel contra una instancia nueva creada en el test, por igualdad. Como `BaseEvent.timestamp` se genera con `datetime.now(UTC)` en cada instancia, la igualdad depende de que ambos timestamps coincidan al microsegundo — casi nunca se cumple, y cuál de los dos tests falla varía de corrida en corrida. Pendiente de decidir (excluir `timestamp` de la igualdad de `BaseEvent`, o cambiar el test para comparar solo `event_type`) — fuera de alcance de la tarea de `memory/` de hoy.
- `src/aries/container/`: eliminado, no forma parte del path de ejecución actual.

## Próximo paso recomendado
Definir el catálogo de eventos de dominio que exige `docs/contracts/IPlugin.md` (`INTENT_DETECTED`, `PLAN_CREATED`, `ACTION_*`, `MEMORY_*`, `PLUGIN_*`), ya que tanto `plugins/` como el resto de la integración de `memory/` con el Event Bus dependen de que esos eventos existan.

## Reglas para mantener este archivo
- Actualizar la tabla y "Qué existe implementado" al cerrar cada tarea, una línea por módulo
- Nunca borrar fases completadas, solo agregar filas nuevas
- "Próximo paso recomendado" siempre debe tener una sola tarea, nunca varias opciones
