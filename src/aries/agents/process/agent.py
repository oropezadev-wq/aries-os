"""ProcessAgent: agente IAgent para ejecutar comandos, scripts y gestionar
procesos del sistema operativo, usando solo `subprocess`/`os` de stdlib.

Alcance deliberado: procesos y comandos del SO. No toca archivos como tal
(eso es FileSystemAgent) ni control de Windows más allá de procesos (eso
sería WindowsAgent, no implementado — ver docs/contracts/IAgent.md).

Notas de diseño (decisiones tomadas sin bloquear, documentadas aquí en vez
de en PROGRESS.md para que vivan junto al código):

- `run_command` usa `shlex.split(command)` + `shell=False`, igual que
  `run_script` — **no** invoca un shell real. Esto cierra el vector de
  inyección de comandos (`;`, `&&`, `|`, etc. dejan de tener significado
  especial: se pasan como argv literal al programa, no como operadores de
  shell) a costa de perder funcionalidad real de shell: pipes, redirects
  (`>`, `<`), expansión de variables (`%VAR%`), y **comandos internos de
  cmd.exe que no son ejecutables reales** (`dir`, `cd`, `echo`, `type`,
  `copy`, `del`, `set`, etc. no tienen un `.exe` propio en Windows — solo
  existen dentro de cmd.exe). Cualquier caso de uso legítimo que dependa de
  esto queda sin soportar; ver PROGRESS.md para el detalle y la decisión
  pendiente (no tomada acá) de si vale la pena soportarlo de otra forma.
- `shlex.split()` en modo POSIX (el default) trata `\\` como carácter de
  escape fuera de comillas, corrompiendo rutas Windows sin comillas
  (`C:\\Windows\\System32\\app.exe` → `C:WindowsSystem32app.exe`). Por eso
  `_split_command()` usa `shlex.split(command, posix=False)`, que preserva
  las barras invertidas — pero ese modo deja las comillas de agrupación
  como caracteres literales en cada token, así que `_split_command()` las
  quita a mano después de tokenizar (ver su docstring). Verificado
  empíricamente: rutas con y sin comillas, con y sin espacios.
- `requires_confirmation()` heurísticamente marca patrones destructivos
  conocidos en `run_command`, pero **no es un sandbox ni una garantía de
  seguridad** — sigue siendo responsabilidad de quien llama pedir
  confirmación antes de ejecutar.
- `run_script` usa `shell=False` con una lista de argv explícita
  (intérprete + ruta + args), porque ahí sí controlamos cada elemento del
  comando.
- Con `shell=False`, un comando/ejecutable inexistente SÍ levanta
  `FileNotFoundError` de Python de forma directa (a diferencia del extinto
  comportamiento con `shell=True`, donde cmd.exe lo reportaba con
  `exit_code != 0` sin lanzar excepción) — `run_command` ahora se comporta
  igual que `run_script` en este sentido: `ActionResult(status=FAILED)`
  para un comando/ejecutable que no existe, en vez de `SUCCESS` con
  `exit_code` distinto de cero.
- `os.kill(pid, signal.SIGTERM)` sí funciona en Windows (CPython lo mapea a
  `TerminateProcess`), pero para un PID inexistente levanta un `OSError`
  genérico (`WinError 87`), no `ProcessLookupError` — por eso `kill_process`
  y `get_process_info` verifican existencia primero vía `tasklist` y
  levantan `ProcessLookupError` ellos mismos, en vez de confiar en el error
  crudo del SO.
- `list_processes`/`get_process_info`/la verificación de existencia de
  `kill_process` dependen de `tasklist`, una utilidad de consola exclusiva
  de Windows. `run_command`/`run_script`/`kill_process` en sí son más
  agnósticos de SO (subprocess/os.kill existen en POSIX también), pero esas
  dos capacidades atan este agente a Windows tal como está.
- Ese acoplamiento a Windows está aislado detrás de `_list_processes_windows()`
  y `_get_process_info_windows()` (este último también lo reutiliza
  `_kill_process` para su chequeo de existencia, en vez de duplicar la
  llamada a `tasklist`). Los handlers del agente (`_list_processes`,
  `_get_process_info`, `_kill_process`) no saben que son Windows-específicos
  — solo llaman a esos métodos. El único chequeo de `platform.system()` vive
  en `_require_windows()`, invocado desde esos dos métodos; para soportar
  otro SO en el futuro, el punto de extensión es agregar
  `_list_processes_<so>()`/`_get_process_info_<so>()` y despachar ahí, no
  agregar chequeos de SO sueltos en cada handler. Por ahora, cualquier SO
  que no sea Windows levanta `NotImplementedError` desde ese único punto —
  Linux/Mac no están implementados todavía.
"""

from __future__ import annotations

import asyncio
import csv
import io
import os
import platform
import re
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from structlog.stdlib import BoundLogger

from ...contracts.agent import ActionResult, ActionStatus, IAgent
from ...logging import get_logger

_HandlerResult = tuple[str, dict[str, Any]]

DEFAULT_TIMEOUT_SECONDS = 30.0

_DESTRUCTIVE_COMMAND_NAMES: frozenset[str] = frozenset(
    {"rm", "del", "erase", "format", "rd", "rmdir", "diskpart", "shutdown", "mkfs", "dd"}
)
_SHELL_SEPARATORS = re.compile(r"[;&|]+")

_INTERPRETERS_BY_SUFFIX: dict[str, list[str]] = {
    ".py": [sys.executable],
    ".ps1": ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"],
    ".sh": ["bash"],
}


class ProcessAgent(IAgent):
    """Agente que ejecuta comandos/scripts y gestiona procesos del SO."""

    def __init__(self) -> None:
        self.logger: BoundLogger = get_logger(self.__class__.__name__)
        self._handlers: dict[str, Callable[..., Awaitable[_HandlerResult]]] = {
            "run_command": self._run_command,
            "run_script": self._run_script,
            "kill_process": self._kill_process,
            "list_processes": self._list_processes,
            "get_process_info": self._get_process_info,
        }

    def get_agent_name(self) -> str:
        return "process"

    def get_capabilities(self) -> list[str]:
        return [
            "run_command",
            "run_script",
            "kill_process",
            "list_processes",
            "get_process_info",
        ]

    def requires_confirmation(self, action: str, command: str | None = None, **_: Any) -> bool:
        if action == "kill_process":
            return True
        if action == "run_command" and command is not None:
            return self._looks_destructive(command)
        return False

    async def is_available(self) -> bool:
        return True

    async def execute(self, action: str, **kwargs: Any) -> ActionResult:
        handler = self._handlers.get(action)

        if handler is None:
            return ActionResult(
                status=ActionStatus.FAILED,
                error=f"Acción desconocida para ProcessAgent: '{action}'",
            )

        target = kwargs.get("path") or kwargs.get("command") or kwargs.get("pid", "")
        start = time.perf_counter()

        try:
            output, data = await handler(**kwargs)
        except FileNotFoundError:
            return self._failed(f"No existe el archivo, script o ejecutable: {target}", start)
        except IsADirectoryError:
            return self._failed(f"La ruta es un directorio, no un script: {target}", start)
        except ProcessLookupError:
            return self._failed(f"No existe ningún proceso con PID {target}", start)
        except PermissionError:
            return self._failed(f"Permiso denegado para '{action}' sobre {target}", start)
        except subprocess.TimeoutExpired:
            timeout = kwargs.get("timeout", DEFAULT_TIMEOUT_SECONDS)
            return self._failed(f"'{action}' excedió el timeout de {timeout}s: {target}", start)
        except ValueError as error:
            return self._failed(f"Comando mal formado para '{action}': {error}", start)
        except TypeError as error:
            return self._failed(f"Parámetros inválidos para '{action}': {error}", start)
        except NotImplementedError as error:
            return self._failed(str(error), start)
        except OSError as error:
            return self._failed(f"Error del sistema al ejecutar '{action}': {error}", start)

        execution_time_ms = (time.perf_counter() - start) * 1000
        self.logger.info("Acción de proceso completada", action=action, target=target)
        return ActionResult(
            status=ActionStatus.SUCCESS,
            output=output,
            data=data,
            execution_time_ms=execution_time_ms,
        )

    def _failed(self, error: str, start: float) -> ActionResult:
        execution_time_ms = (time.perf_counter() - start) * 1000
        self.logger.warning("Acción de proceso falló", error=error)
        return ActionResult(
            status=ActionStatus.FAILED,
            error=error,
            execution_time_ms=execution_time_ms,
        )

    @staticmethod
    def _looks_destructive(command: str) -> bool:
        """Heurística de mejor esfuerzo, NO un control de seguridad real.

        Revisa el primer token de cada segmento separado por `;`/`&`/`|`
        contra una lista corta de comandos conocidos como destructivos.
        No detecta ofuscación, alias, ni comandos encadenados de formas
        más exóticas que separadores de shell comunes.

        Nota: desde que `_run_command` usa `shell=False`, estos separadores
        ya no encadenan comandos de verdad en la ejecución (se pasan como
        argv literal, no se interpretan) — pero el análisis multi-segmento
        se mantiene igual porque sigue siendo una heurística de texto válida
        sobre el string que el caller piensa ejecutar, independiente de
        cómo `execute()` termine invocándolo.
        """
        for segment in _SHELL_SEPARATORS.split(command):
            segment = segment.strip().strip("\"'")
            if not segment:
                continue
            first_token = segment.split(maxsplit=1)[0]
            name = Path(first_token).stem.lower().strip("\"'")
            if name in _DESTRUCTIVE_COMMAND_NAMES:
                return True
        return False

    @staticmethod
    def _split_command(command: str) -> list[str]:
        """Tokeniza `command` preservando barras invertidas de rutas Windows.

        `shlex.split(command)` en modo POSIX (el default) trata `\\` como
        carácter de escape fuera de comillas, corrompiendo rutas Windows sin
        comillas (`C:\\Windows\\System32\\app.exe` → `C:WindowsSystem32app.exe`,
        verificado empíricamente). `posix=False` preserva las barras
        invertidas, pero como efecto secundario deja las comillas de
        agrupación como caracteres **literales** dentro de cada token en vez
        de removerlas — sin este paso extra, un comando con argumentos entre
        comillas (el caso común: rutas con espacios, o `-c "código"`) se
        rompería con `FileNotFoundError` porque las comillas pasarían a
        formar parte del nombre de archivo/argumento. Por eso se quitan acá
        a mano, un par de comillas por token, después de tokenizar.

        Reglas de quoting soportadas (verificadas empíricamente, no solo
        inferidas de la documentación de `shlex`):

        - **Un par de comillas por token, y deben abrir el token.** Si un
          token entero está rodeado por `"..."` o `'...'`, ese par se quita.
          Ejemplo soportado: `'"C:\\ruta con espacios\\app.exe" --flag'` →
          `['C:\\ruta con espacios\\app.exe', '--flag']`.
        - **Backslash es siempre literal, adentro y afuera de comillas.**
          Nunca escapa nada — ni una comilla, ni otro backslash, ni un
          espacio. Es justamente lo que permite que rutas Windows con `\\`
          sobrevivan intactas.
        - **No hay soporte de comillas escapadas.** No existe forma de
          incluir una comilla literal dentro de un token entre comillas (no
          hay equivalente a `\\"` de bash). Intentarlo produce tokenización
          impredecible, no un error controlado: `'"a\\"b"'` se parte en
          `['a\\"', 'b"']` en vez de en un solo token con una comilla
          adentro — verificado, no asumido.
        - **No hay soporte de comillas anidadas o mixtas dentro de un
          mismo token**, ni de concatenación estilo shell de segmentos
          quoted+unquoted pegados (`"foo"bar` no da `foobar` como en un
          shell real). Una comilla que aparece después de caracteres no
          separados por espacio dentro de lo que sería un solo token
          produce un corte de tokens inesperado en el espacio que
          nominalmente estaría "adentro" de esas comillas — ejemplo
          verificado: `'foo"bar baz"qux'` → `['foo"bar', 'baz"qux']`, no
          `['foobar bazqux']`.

        En resumen: para uso confiable, encerrar entre comillas una ruta o
        argumento completo (comillas al principio y al final del token,
        nada más), y nunca mezclar tipos de comillas ni intentar escapar
        una comilla con backslash.
        """
        tokens = shlex.split(command, posix=False)
        cleaned: list[str] = []
        for token in tokens:
            if len(token) >= 2 and token[0] == token[-1] and token[0] in ("\"", "'"):
                token = token[1:-1]
            cleaned.append(token)
        return cleaned

    async def _run_command(
        self,
        command: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        cwd: str | None = None,
        **_: Any,
    ) -> _HandlerResult:
        """Ejecuta `command` con `shell=False` (ver docstring del módulo).

        `command` se tokeniza con `_split_command()` — ver ahí las reglas
        de quoting soportadas (un par de comillas por token, backslash
        siempre literal, sin comillas escapadas ni anidadas).
        """
        args = self._split_command(command)
        if not args:
            raise ValueError("comando vacío")

        completed = await asyncio.to_thread(
            subprocess.run,
            args,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        data = {
            "command": command,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        return completed.stdout, data

    async def _run_script(
        self,
        path: str,
        args: list[str] | None = None,
        interpreter: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        cwd: str | None = None,
        **_: Any,
    ) -> _HandlerResult:
        script_path = Path(path)
        if not script_path.exists():
            raise FileNotFoundError(path)
        if script_path.is_dir():
            raise IsADirectoryError(path)

        extra_args = list(args) if args else []
        if interpreter:
            command = [interpreter, str(script_path), *extra_args]
        else:
            prefix = _INTERPRETERS_BY_SUFFIX.get(script_path.suffix.lower(), [])
            command = [*prefix, str(script_path), *extra_args]

        completed = await asyncio.to_thread(
            subprocess.run,
            command,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        data = {
            "path": str(script_path),
            "command": command,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        return completed.stdout, data

    async def _kill_process(self, pid: int, **_: Any) -> _HandlerResult:
        if not isinstance(pid, int) or isinstance(pid, bool):
            raise TypeError("pid debe ser un entero")

        info = await self._get_process_info_windows(pid)
        if info is None:
            raise ProcessLookupError(pid)

        await asyncio.to_thread(os.kill, pid, signal.SIGTERM)
        return f"Proceso {pid} terminado", {"pid": pid}

    async def _list_processes(self, **_: Any) -> _HandlerResult:
        processes = await self._list_processes_windows()
        return f"{len(processes)} proceso(s) en ejecución", {
            "processes": processes,
            "count": len(processes),
        }

    async def _get_process_info(self, pid: int, **_: Any) -> _HandlerResult:
        if not isinstance(pid, int) or isinstance(pid, bool):
            raise TypeError("pid debe ser un entero")

        info = await self._get_process_info_windows(pid)
        if info is None:
            raise ProcessLookupError(pid)

        return f"Proceso {pid}: {info['name']}", info

    # --- Puntos de extensión específicos de SO -----------------------------
    # Los handlers de arriba (`_list_processes`, `_get_process_info`,
    # `_kill_process`) no saben que estas llamadas son Windows-específicas;
    # solo conocen esta interfaz. Agregar soporte para otro SO significa
    # sumar un `_list_processes_<so>()`/`_get_process_info_<so>()` propio y
    # despachar en `_require_windows()` (renombrándolo), no tocar los
    # handlers ni repetir el chequeo de `platform.system()` en otro lado.

    async def _list_processes_windows(self) -> list[dict[str, Any]]:
        self._require_windows()
        return await asyncio.to_thread(self._tasklist)

    async def _get_process_info_windows(self, pid: int) -> dict[str, Any] | None:
        self._require_windows()
        processes = await asyncio.to_thread(self._tasklist, ["/FI", f"PID eq {pid}"])
        return processes[0] if processes else None

    @staticmethod
    def _require_windows() -> None:
        current = platform.system()
        if current != "Windows":
            raise NotImplementedError(
                "ProcessAgent.list_processes/get_process_info/kill_process solo están "
                f"implementados para Windows por ahora (SO detectado: {current})."
            )

    @staticmethod
    def _tasklist(extra_args: list[str] | None = None) -> list[dict[str, Any]]:
        args = ["tasklist", "/FO", "CSV", "/NH", *(extra_args or [])]
        completed = subprocess.run(args, capture_output=True, text=True, timeout=10, check=False)
        if completed.returncode != 0:
            raise OSError(completed.stderr.strip() or "tasklist devolvió un código de error")

        reader = csv.reader(io.StringIO(completed.stdout))
        processes: list[dict[str, Any]] = []
        for row in reader:
            if len(row) < 5:
                # `tasklist` imprime un mensaje informativo en texto plano
                # (no CSV) cuando no hay coincidencias — se ignora esa fila.
                continue
            name, pid_str, session_name, session_number, mem_usage = row[:5]
            try:
                pid = int(pid_str)
            except ValueError:
                continue
            processes.append(
                {
                    "pid": pid,
                    "name": name,
                    "session_name": session_name,
                    "session_number": session_number,
                    "mem_usage": mem_usage,
                }
            )
        return processes
